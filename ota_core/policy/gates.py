"""HITL (Human-in-the-Loop) gate primitives.

A gate is a proposed action that needs operator approval before the routine
proceeds. Routines `await gate.propose(...)` and the operator
acts via the dashboard's approval queue or a Slack action callback.

Three approval modes (per `ApprovalMode` in Contract C):

* `approve` — operator says "yes / no" on this specific proposal.
* `tune_and_approve` — operator edits a field of the proposal (subject, body,
  etc.) and then approves. The edited content is what runs.
* `approve_and_remember` — operator approves and authorizes the framework to
  auto-approve future proposals that match the gate's `similarity_function`
  output (within tolerance). Used by `email_triage` trust-promotion.

Gate state persists across restarts so the operator can resume after the
framework was down. Storage is SQLite via `ota_core.storage.database`. A
single `gates` table holds in-flight + completed gate instances per
routine_run.

The audit trail tracks: `gate.proposed`, `gate.approved`, `gate.rejected`,
`gate.modified_and_approved`, `gate.auto_approved_by_similarity`,
`gate.expired`.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from ota_core.audit import AuditSink
from ota_core.contracts.audit_event import Principal
from ota_core.contracts.routine_source import ApprovalMode
from ota_core.storage.database import Database
from ota_core.storage.schema import Migration, apply_pending

GateStatus = Literal[
    "pending",
    "approved",
    "rejected",
    "modified_and_approved",
    "auto_approved",
    "expired",
]


GATES_MIGRATION = Migration(
    name="gates_0_1_0",
    statements=(
        """
        CREATE TABLE IF NOT EXISTS gates (
            id TEXT PRIMARY KEY,
            routine_id TEXT NOT NULL,
            routine_run_id TEXT NOT NULL,
            gate_id TEXT NOT NULL,
            status TEXT NOT NULL,
            proposal_json TEXT NOT NULL,
            result_json TEXT,
            similarity_key TEXT,
            approval_mode TEXT,
            expires_at TEXT,
            created_at TEXT NOT NULL,
            decided_at TEXT
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_gates_status ON gates (status)",
        "CREATE INDEX IF NOT EXISTS idx_gates_routine ON gates (routine_id, status)",
        (
            "CREATE INDEX IF NOT EXISTS idx_gates_similarity "
            "ON gates (routine_id, gate_id, similarity_key, status)"
        ),
    ),
)


SimilarityFn = Callable[[dict[str, Any]], str]
"""Pure function: proposal payload → opaque similarity key.

Two proposals with the same key are considered "the same" for
`approve_and_remember` purposes. Keep this deterministic and side-effect-free.
"""


@dataclass(frozen=True)
class GateProposal:
    """The payload a routine submits to a gate.

    `kind` mirrors the gate's Contract-C `kind` (preview / confidence / diff /
    permission / budget / novelty); `payload` is the gate-specific body
    (e.g. `{"subject": ..., "body": ..., "to": ...}` for an email draft).
    `summary` is a one-line human description rendered in approval surfaces.
    """

    routine_id: str
    routine_run_id: str
    gate_id: str
    approval_modes: tuple[ApprovalMode, ...]
    kind: str | None
    summary: str
    payload: dict[str, Any]
    similarity_key: str | None = None
    expires_after_seconds: int | None = None


@dataclass(frozen=True)
class GateInstance:
    """A persisted gate proposal record."""

    id: str
    routine_id: str
    routine_run_id: str
    gate_id: str
    status: GateStatus
    proposal: dict[str, Any]
    result: dict[str, Any] | None
    similarity_key: str | None
    approval_mode: ApprovalMode | None
    expires_at: datetime | None
    created_at: datetime
    decided_at: datetime | None
    summary: str = ""
    kind: str | None = None


class GateError(Exception):
    pass


class GateNotFoundError(GateError):
    pass


class GateAlreadyDecidedError(GateError):
    pass


class GateRejected(GateError):
    """Raised inside `propose()` when the operator rejects the proposal."""

    def __init__(self, gate_id: str, reason: str | None = None) -> None:
        self.gate_id = gate_id
        self.reason = reason
        super().__init__(f"gate {gate_id!r} rejected" + (f": {reason}" if reason else ""))


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _row_to_instance(row: Any) -> GateInstance:
    return GateInstance(
        id=row["id"],
        routine_id=row["routine_id"],
        routine_run_id=row["routine_run_id"],
        gate_id=row["gate_id"],
        status=row["status"],
        proposal=json.loads(row["proposal_json"]),
        result=json.loads(row["result_json"]) if row["result_json"] else None,
        similarity_key=row["similarity_key"],
        approval_mode=row["approval_mode"] if row["approval_mode"] else None,
        expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
        created_at=datetime.fromisoformat(row["created_at"]),
        decided_at=datetime.fromisoformat(row["decided_at"]) if row["decided_at"] else None,
    )


class GateStore:
    """Persistence layer for gate instances. Sync API (use `asyncio.to_thread`)."""

    def __init__(self, database: Database) -> None:
        self._db = database
        apply_pending(database, [GATES_MIGRATION])

    def insert(self, instance: GateInstance) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO gates (id, routine_id, routine_run_id, gate_id, status,
                                   proposal_json, result_json, similarity_key,
                                   approval_mode, expires_at, created_at, decided_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    instance.id,
                    instance.routine_id,
                    instance.routine_run_id,
                    instance.gate_id,
                    instance.status,
                    json.dumps(instance.proposal),
                    json.dumps(instance.result) if instance.result is not None else None,
                    instance.similarity_key,
                    instance.approval_mode,
                    instance.expires_at.isoformat() if instance.expires_at else None,
                    instance.created_at.isoformat(),
                    instance.decided_at.isoformat() if instance.decided_at else None,
                ),
            )

    def get(self, gate_pk: str) -> GateInstance:
        conn = self._db.connect()
        row = conn.execute("SELECT * FROM gates WHERE id = ?", (gate_pk,)).fetchone()
        if row is None:
            raise GateNotFoundError(gate_pk)
        return _row_to_instance(row)

    def list_pending(self, routine_id: str | None = None) -> list[GateInstance]:
        conn = self._db.connect()
        if routine_id is None:
            rows = conn.execute(
                "SELECT * FROM gates WHERE status = 'pending' ORDER BY created_at ASC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM gates WHERE status = 'pending' AND routine_id = ? "
                "ORDER BY created_at ASC",
                (routine_id,),
            ).fetchall()
        return [_row_to_instance(r) for r in rows]

    def list_recent(self, limit: int = 100) -> list[GateInstance]:
        conn = self._db.connect()
        rows = conn.execute(
            "SELECT * FROM gates ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_row_to_instance(r) for r in rows]

    def has_remembered_approval(
        self, *, routine_id: str, gate_id: str, similarity_key: str
    ) -> bool:
        conn = self._db.connect()
        row = conn.execute(
            """
            SELECT id FROM gates
            WHERE routine_id = ? AND gate_id = ?
              AND similarity_key = ?
              AND status IN ('approved', 'modified_and_approved', 'auto_approved')
            LIMIT 1
            """,
            (routine_id, gate_id, similarity_key),
        ).fetchone()
        return row is not None

    def update_decision(
        self,
        *,
        gate_pk: str,
        status: GateStatus,
        result: dict[str, Any] | None,
        decided_at: datetime,
    ) -> GateInstance:
        existing = self.get(gate_pk)
        if existing.status != "pending":
            raise GateAlreadyDecidedError(f"gate {gate_pk!r} already in status={existing.status}")
        with self._db.transaction() as conn:
            conn.execute(
                """
                UPDATE gates SET status = ?, result_json = ?, decided_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    json.dumps(result) if result is not None else None,
                    decided_at.isoformat(),
                    gate_pk,
                ),
            )
        return self.get(gate_pk)


@dataclass
class GateDecision:
    status: GateStatus
    result_payload: dict[str, Any] | None = None
    reason: str | None = None


class GateManager:
    """High-level gate API used by routines and the dashboard.

    Routines: `await manager.propose(...)` blocks until the gate is decided
    or expires. v0.1 only supports the **sync polling** wait pattern — the
    routine engine wraps the manager in `asyncio.to_thread` if it needs to
    avoid blocking the loop.

    Dashboard / Slack action callback: `manager.decide(gate_pk, ...)` updates
    persistent state and (in a follow-up release) signals any waiters.
    """

    def __init__(
        self,
        *,
        store: GateStore,
        audit_sink: AuditSink,
        principal: Principal,
        similarity_fns: dict[str, SimilarityFn] | None = None,
    ) -> None:
        self._store = store
        self._audit = audit_sink
        self._principal = principal
        self._similarity_fns = dict(similarity_fns or {})

    def register_similarity(self, gate_id: str, fn: SimilarityFn) -> None:
        self._similarity_fns[gate_id] = fn

    def propose_for_review(
        self,
        proposal: GateProposal,
    ) -> GateInstance:
        """Persist a proposal and emit `gate.proposed`. Returns the instance.

        Does not block. Callers either auto-approve (if a matching
        remembered approval exists) or wait for an external decision.
        Auto-approval is handled here when the gate carries an
        `approve_and_remember` mode and a similarity match is on file.
        """
        gate_pk = uuid.uuid4().hex
        now = _utc_now()
        expires_at = (
            now + timedelta(seconds=proposal.expires_after_seconds)
            if proposal.expires_after_seconds is not None
            else None
        )
        # Compute similarity key when registered fn exists
        sim_key = proposal.similarity_key
        if sim_key is None:
            fn = self._similarity_fns.get(proposal.gate_id)
            if fn is not None:
                sim_key = fn(proposal.payload)

        instance = GateInstance(
            id=gate_pk,
            routine_id=proposal.routine_id,
            routine_run_id=proposal.routine_run_id,
            gate_id=proposal.gate_id,
            status="pending",
            proposal=dict(proposal.payload, _summary=proposal.summary, _kind=proposal.kind),
            result=None,
            similarity_key=sim_key,
            approval_mode=None,
            expires_at=expires_at,
            created_at=now,
            decided_at=None,
            summary=proposal.summary,
            kind=proposal.kind,
        )
        self._store.insert(instance)
        self._audit.emit(
            event_type="gate.proposed",
            severity="info",
            principal=self._principal,
            payload={
                "gate_pk": gate_pk,
                "gate_id": proposal.gate_id,
                "approval_modes": list(proposal.approval_modes),
                "summary": proposal.summary,
                "similarity_key": sim_key,
            },
            routine_run_id=proposal.routine_run_id,
        )
        if (
            "approve_and_remember" in proposal.approval_modes
            and sim_key is not None
            and self._store.has_remembered_approval(
                routine_id=proposal.routine_id,
                gate_id=proposal.gate_id,
                similarity_key=sim_key,
            )
        ):
            return self._record_decision(
                gate_pk,
                status="auto_approved",
                result_payload=proposal.payload,
                approval_mode="approve_and_remember",
                event_type="gate.auto_approved_by_similarity",
            )
        return instance

    def decide(
        self,
        gate_pk: str,
        *,
        decision: GateDecision,
        approval_mode: ApprovalMode | None = None,
    ) -> GateInstance:
        event_type = {
            "approved": "gate.approved",
            "rejected": "gate.rejected",
            "modified_and_approved": "gate.modified_and_approved",
        }.get(decision.status)
        if event_type is None:
            raise GateError(
                f"decide() requires status in approved / rejected / modified_and_approved; "
                f"got {decision.status!r}"
            )
        return self._record_decision(
            gate_pk,
            status=decision.status,
            result_payload=decision.result_payload,
            approval_mode=approval_mode,
            event_type=event_type,
            reason=decision.reason,
        )

    def expire_due(self, now: datetime | None = None) -> list[GateInstance]:
        """Mark any pending gates whose deadline has passed as expired.

        Returns the newly-expired instances. The dashboard / scheduler hooks
        this in periodically; the routine engine surfaces an expiration
        through whichever wait API the routine uses.
        """
        now = now or _utc_now()
        expired: list[GateInstance] = []
        for instance in self._store.list_pending():
            if instance.expires_at is not None and instance.expires_at <= now:
                updated = self._record_decision(
                    instance.id,
                    status="expired",
                    result_payload=None,
                    approval_mode=None,
                    event_type="gate.expired",
                )
                expired.append(updated)
        return expired

    def _record_decision(
        self,
        gate_pk: str,
        *,
        status: GateStatus,
        result_payload: dict[str, Any] | None,
        approval_mode: ApprovalMode | None,
        event_type: str,
        reason: str | None = None,
    ) -> GateInstance:
        decided_at = _utc_now()
        # Persist decision (also captures approval_mode by overwriting the column)
        result_with_meta = dict(result_payload or {})
        if approval_mode is not None:
            result_with_meta["_approval_mode"] = approval_mode
        if reason is not None:
            result_with_meta["_reason"] = reason
        updated = self._store.update_decision(
            gate_pk=gate_pk,
            status=status,
            result=result_with_meta or None,
            decided_at=decided_at,
        )
        existing = self._store.get(gate_pk)
        payload = {
            "gate_pk": gate_pk,
            "gate_id": existing.gate_id,
            "status": status,
            "approval_mode": approval_mode,
            "reason": reason,
        }
        self._audit.emit(
            event_type=event_type,  # type: ignore[arg-type]
            severity="info",
            principal=self._principal,
            payload=payload,
            routine_run_id=existing.routine_run_id,
        )
        return updated


@dataclass
class GateRegistry:
    """Lightweight directory mapping `routine_id` → `GateManager` instance.

    The routine engine looks up the manager when running a routine; the
    dashboard looks up by `routine_id` to decide on a pending gate.
    """

    _by_routine: dict[str, GateManager] = field(default_factory=dict)

    def register(self, routine_id: str, manager: GateManager) -> None:
        self._by_routine[routine_id] = manager

    def get(self, routine_id: str) -> GateManager:
        if routine_id not in self._by_routine:
            raise GateError(f"no GateManager registered for routine {routine_id!r}")
        return self._by_routine[routine_id]

    def contains(self, routine_id: str) -> bool:
        return routine_id in self._by_routine
