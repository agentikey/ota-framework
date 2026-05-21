"""Per-instance SQLite state for `email_triage`.

Tables:

* `processed_emails` — dedup. (email_id, content_hash) seen this run so we
  don't re-draft on adapter retry.
* `template_trust` — per-template (consecutive_unedited, total_sent,
  auto_send_enabled, demoted_at).
* `template_edits` — append-only log of operator edits. Used by trust demotion
  and by the /why interface.
* `triage_decisions` — append-only log of routine decisions (classified
  category, draft id, action taken, run_id) used by /why and drift.

Tables live in the framework's shared SQLite database under the
`email_triage_` prefix so multiple instances co-exist without colliding.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from ota_core.storage.database import Database
from ota_core.storage.schema import Migration, apply_pending

TriageAction = Literal["drafted", "auto_sent", "skipped", "approved", "rejected"]


EMAIL_TRIAGE_MIGRATION = Migration(
    name="email_triage_0_1_0",
    statements=(
        """
        CREATE TABLE IF NOT EXISTS email_triage_processed (
            email_id TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            processed_at TEXT NOT NULL,
            PRIMARY KEY (email_id, content_hash)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS email_triage_template_trust (
            template TEXT PRIMARY KEY,
            consecutive_unedited INTEGER NOT NULL DEFAULT 0,
            total_sent INTEGER NOT NULL DEFAULT 0,
            auto_send_enabled INTEGER NOT NULL DEFAULT 0,
            opt_in_auto_send INTEGER NOT NULL DEFAULT 0,
            demoted_at TEXT,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS email_triage_edits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template TEXT NOT NULL,
            email_id TEXT NOT NULL,
            edit_kind TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS email_triage_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            routine_run_id TEXT NOT NULL,
            email_id TEXT NOT NULL,
            category TEXT,
            template TEXT,
            action TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            decided_at TEXT NOT NULL
        )
        """,
        (
            "CREATE INDEX IF NOT EXISTS idx_triage_decisions_run "
            "ON email_triage_decisions (routine_run_id)"
        ),
        (
            "CREATE INDEX IF NOT EXISTS idx_triage_decisions_email "
            "ON email_triage_decisions (email_id)"
        ),
    ),
)


@dataclass(frozen=True)
class TemplateTrust:
    template: str
    consecutive_unedited: int
    total_sent: int
    auto_send_enabled: bool
    opt_in_auto_send: bool
    demoted_at: datetime | None
    updated_at: datetime


@dataclass(frozen=True)
class TriageDecisionRecord:
    id: int
    routine_run_id: str
    email_id: str
    category: str | None
    template: str | None
    action: TriageAction
    payload: dict[str, Any]
    decided_at: datetime


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _row_to_trust(row: Any) -> TemplateTrust:
    return TemplateTrust(
        template=row["template"],
        consecutive_unedited=row["consecutive_unedited"],
        total_sent=row["total_sent"],
        auto_send_enabled=bool(row["auto_send_enabled"]),
        opt_in_auto_send=bool(row["opt_in_auto_send"]),
        demoted_at=datetime.fromisoformat(row["demoted_at"]) if row["demoted_at"] else None,
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _row_to_decision(row: Any) -> TriageDecisionRecord:
    return TriageDecisionRecord(
        id=row["id"],
        routine_run_id=row["routine_run_id"],
        email_id=row["email_id"],
        category=row["category"],
        template=row["template"],
        action=row["action"],
        payload=json.loads(row["payload_json"]),
        decided_at=datetime.fromisoformat(row["decided_at"]),
    )


class EmailTriageState:
    """Per-instance state store. Sync API."""

    def __init__(self, database: Database, *, trust_threshold: int = 20) -> None:
        self._db = database
        self._trust_threshold = trust_threshold
        apply_pending(database, [EMAIL_TRIAGE_MIGRATION])

    @property
    def trust_threshold(self) -> int:
        return self._trust_threshold

    # ------------------------------------------------------------------
    # Dedup
    # ------------------------------------------------------------------

    def mark_processed(self, *, email_id: str, content_hash: str) -> bool:
        """Returns True if newly recorded; False if already seen."""
        conn = self._db.connect()
        try:
            with self._db.transaction() as tx:
                tx.execute(
                    """
                    INSERT INTO email_triage_processed
                        (email_id, content_hash, processed_at)
                    VALUES (?, ?, ?)
                    """,
                    (email_id, content_hash, _utc_now().isoformat()),
                )
            return True
        except Exception as exc:
            msg = str(exc)
            if "UNIQUE constraint" in msg or "PRIMARY KEY" in msg:
                return False
            raise
        finally:
            _ = conn

    def is_processed(self, *, email_id: str, content_hash: str) -> bool:
        conn = self._db.connect()
        row = conn.execute(
            """
            SELECT 1 FROM email_triage_processed
            WHERE email_id = ? AND content_hash = ?
            """,
            (email_id, content_hash),
        ).fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # Template trust
    # ------------------------------------------------------------------

    def _ensure_trust_row(self, template: str) -> None:
        conn = self._db.connect()
        existing = conn.execute(
            "SELECT 1 FROM email_triage_template_trust WHERE template = ?",
            (template,),
        ).fetchone()
        if existing is not None:
            return
        with self._db.transaction() as tx:
            tx.execute(
                """
                INSERT INTO email_triage_template_trust
                    (template, consecutive_unedited, total_sent, auto_send_enabled,
                     opt_in_auto_send, demoted_at, updated_at)
                VALUES (?, 0, 0, 0, 0, NULL, ?)
                """,
                (template, _utc_now().isoformat()),
            )

    def opt_in_auto_send(self, template: str, *, enabled: bool) -> TemplateTrust:
        self._ensure_trust_row(template)
        with self._db.transaction() as tx:
            tx.execute(
                """
                UPDATE email_triage_template_trust
                SET opt_in_auto_send = ?, updated_at = ?
                WHERE template = ?
                """,
                (1 if enabled else 0, _utc_now().isoformat(), template),
            )
        return self.trust(template)

    def record_unedited_approval(self, template: str) -> TemplateTrust:
        """Operator approved the draft as-is. Increment counter; promote if threshold met."""
        self._ensure_trust_row(template)
        current = self.trust(template)
        new_count = current.consecutive_unedited + 1
        promote = (
            current.opt_in_auto_send
            and not current.auto_send_enabled
            and new_count >= self._trust_threshold
        )
        with self._db.transaction() as tx:
            tx.execute(
                """
                UPDATE email_triage_template_trust
                SET consecutive_unedited = ?,
                    total_sent = total_sent + 1,
                    auto_send_enabled = ?,
                    updated_at = ?
                WHERE template = ?
                """,
                (
                    new_count,
                    1 if (current.auto_send_enabled or promote) else 0,
                    _utc_now().isoformat(),
                    template,
                ),
            )
        return self.trust(template)

    def record_edit(
        self, template: str, *, email_id: str, edit_kind: str = "tuned"
    ) -> TemplateTrust:
        """Operator edited the draft. Reset counter; demote if currently auto-sending."""
        self._ensure_trust_row(template)
        current = self.trust(template)
        demote = current.auto_send_enabled
        with self._db.transaction() as tx:
            tx.execute(
                """
                INSERT INTO email_triage_edits (template, email_id, edit_kind, recorded_at)
                VALUES (?, ?, ?, ?)
                """,
                (template, email_id, edit_kind, _utc_now().isoformat()),
            )
            tx.execute(
                """
                UPDATE email_triage_template_trust
                SET consecutive_unedited = 0,
                    auto_send_enabled = 0,
                    demoted_at = ?,
                    updated_at = ?
                WHERE template = ?
                """,
                (
                    _utc_now().isoformat()
                    if demote
                    else current.demoted_at.isoformat()
                    if current.demoted_at
                    else None,
                    _utc_now().isoformat(),
                    template,
                ),
            )
        return self.trust(template)

    def trust(self, template: str) -> TemplateTrust:
        self._ensure_trust_row(template)
        conn = self._db.connect()
        row = conn.execute(
            "SELECT * FROM email_triage_template_trust WHERE template = ?",
            (template,),
        ).fetchone()
        return _row_to_trust(row)

    def list_trust(self) -> list[TemplateTrust]:
        conn = self._db.connect()
        rows = conn.execute(
            "SELECT * FROM email_triage_template_trust ORDER BY template"
        ).fetchall()
        return [_row_to_trust(r) for r in rows]

    # ------------------------------------------------------------------
    # Decision log
    # ------------------------------------------------------------------

    def record_decision(
        self,
        *,
        routine_run_id: str,
        email_id: str,
        action: TriageAction,
        category: str | None,
        template: str | None,
        payload: dict[str, Any],
    ) -> TriageDecisionRecord:
        decided_at = _utc_now()
        with self._db.transaction() as tx:
            cursor = tx.execute(
                """
                INSERT INTO email_triage_decisions
                    (routine_run_id, email_id, category, template, action,
                     payload_json, decided_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    routine_run_id,
                    email_id,
                    category,
                    template,
                    action,
                    json.dumps(payload),
                    decided_at.isoformat(),
                ),
            )
            decision_id = cursor.lastrowid
        return TriageDecisionRecord(
            id=decision_id or 0,
            routine_run_id=routine_run_id,
            email_id=email_id,
            category=category,
            template=template,
            action=action,
            payload=payload,
            decided_at=decided_at,
        )

    def by_email_id(self, email_id: str) -> list[TriageDecisionRecord]:
        conn = self._db.connect()
        rows = conn.execute(
            """
            SELECT * FROM email_triage_decisions
            WHERE email_id = ?
            ORDER BY decided_at ASC
            """,
            (email_id,),
        ).fetchall()
        return [_row_to_decision(r) for r in rows]

    def by_routine_run(self, routine_run_id: str) -> list[TriageDecisionRecord]:
        conn = self._db.connect()
        rows = conn.execute(
            """
            SELECT * FROM email_triage_decisions
            WHERE routine_run_id = ?
            ORDER BY decided_at ASC
            """,
            (routine_run_id,),
        ).fetchall()
        return [_row_to_decision(r) for r in rows]

    def recent_decisions(
        self, *, within: timedelta, actions: Iterable[TriageAction] | None = None
    ) -> list[TriageDecisionRecord]:
        cutoff = _utc_now() - within
        params: tuple[Any, ...] = (cutoff.isoformat(),)
        sql = """
            SELECT * FROM email_triage_decisions
            WHERE decided_at >= ?
        """
        if actions is not None:
            placeholders = ", ".join("?" for _ in actions)
            sql += f" AND action IN ({placeholders})"
            params = params + tuple(actions)
        sql += " ORDER BY decided_at ASC"
        conn = self._db.connect()
        rows = conn.execute(sql, params).fetchall()
        return [_row_to_decision(r) for r in rows]
