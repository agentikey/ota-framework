from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from ota_core.audit import NullAuditSink
from ota_core.contracts.audit_event import DeploymentInfo, Principal, SourceInfo
from ota_core.policy import (
    GateAlreadyDecidedError,
    GateDecision,
    GateManager,
    GateNotFoundError,
    GateProposal,
    GateStore,
)
from ota_core.storage.database import Database


def _deployment() -> DeploymentInfo:
    return DeploymentInfo(id="d", mode="vps", edition="core", version="0.1.0")


def _source() -> SourceInfo:
    return SourceInfo(component="test", version="0.1.0")


def _principal() -> Principal:
    return Principal(id="op:test", type="operator", display_name="Test")


@pytest.fixture
def store(tmp_path: Path) -> GateStore:
    db = Database(tmp_path / "gates.db")
    return GateStore(db)


@pytest.fixture
def sink() -> NullAuditSink:
    return NullAuditSink(deployment=_deployment(), source=_source())


@pytest.fixture
def manager(store: GateStore, sink: NullAuditSink) -> GateManager:
    return GateManager(store=store, audit_sink=sink, principal=_principal())


def _proposal(**overrides: Any) -> GateProposal:
    base = {
        "routine_id": "ota.test",
        "routine_run_id": "rr-1",
        "gate_id": "draft_review",
        "approval_modes": ("approve", "tune_and_approve"),
        "kind": "preview",
        "summary": "Send email to bob@example.com",
        "payload": {"subject": "Hi", "body": "test", "to": "bob@example.com"},
    }
    base.update(overrides)
    return GateProposal(**base)  # type: ignore[arg-type]


def test_propose_persists_and_emits_proposed(manager: GateManager, sink: NullAuditSink) -> None:
    instance = manager.propose_for_review(_proposal())
    assert instance.status == "pending"
    assert instance.gate_id == "draft_review"
    assert instance.proposal["subject"] == "Hi"
    events = [e.event_type for e in sink.events]
    assert "gate.proposed" in events


def test_approve_emits_event_and_persists(
    manager: GateManager, sink: NullAuditSink, store: GateStore
) -> None:
    instance = manager.propose_for_review(_proposal())
    decided = manager.decide(
        instance.id,
        decision=GateDecision(status="approved", result_payload=instance.proposal),
        approval_mode="approve",
    )
    assert decided.status == "approved"
    events = [e.event_type for e in sink.events]
    assert "gate.approved" in events
    refetched = store.get(instance.id)
    assert refetched.status == "approved"


def test_reject_emits_event(manager: GateManager, sink: NullAuditSink) -> None:
    instance = manager.propose_for_review(_proposal())
    manager.decide(
        instance.id,
        decision=GateDecision(status="rejected", reason="off-topic"),
        approval_mode="approve",
    )
    events = [e.event_type for e in sink.events]
    assert "gate.rejected" in events


def test_modified_and_approved(manager: GateManager, sink: NullAuditSink) -> None:
    instance = manager.propose_for_review(_proposal())
    edited = dict(instance.proposal, subject="Edited subject")
    decided = manager.decide(
        instance.id,
        decision=GateDecision(status="modified_and_approved", result_payload=edited),
        approval_mode="tune_and_approve",
    )
    assert decided.status == "modified_and_approved"
    assert decided.result is not None
    assert decided.result["subject"] == "Edited subject"
    events = [e.event_type for e in sink.events]
    assert "gate.modified_and_approved" in events


def test_decide_twice_raises(manager: GateManager) -> None:
    instance = manager.propose_for_review(_proposal())
    manager.decide(instance.id, decision=GateDecision(status="approved"))
    with pytest.raises(GateAlreadyDecidedError):
        manager.decide(instance.id, decision=GateDecision(status="approved"))


def test_decide_missing_raises(manager: GateManager) -> None:
    with pytest.raises(GateNotFoundError):
        manager.decide("does-not-exist", decision=GateDecision(status="approved"))


def test_list_pending_filters_by_routine(manager: GateManager, store: GateStore) -> None:
    manager.propose_for_review(_proposal(routine_id="ota.a"))
    manager.propose_for_review(_proposal(routine_id="ota.b"))
    a = store.list_pending("ota.a")
    b = store.list_pending("ota.b")
    assert len(a) == 1
    assert len(b) == 1


def test_approve_and_remember_auto_approves_on_similarity_match(
    manager: GateManager,
    sink: NullAuditSink,
) -> None:
    def sim(payload: dict[str, Any]) -> str:
        return str(payload["to"])

    manager.register_similarity("draft_review", sim)
    first = manager.propose_for_review(
        _proposal(approval_modes=("approve", "approve_and_remember"))
    )
    manager.decide(
        first.id,
        decision=GateDecision(status="approved", result_payload=first.proposal),
        approval_mode="approve_and_remember",
    )
    second = manager.propose_for_review(
        _proposal(approval_modes=("approve", "approve_and_remember"))
    )
    assert second.status == "auto_approved"
    events = [e.event_type for e in sink.events]
    assert "gate.auto_approved_by_similarity" in events


def test_expire_due_marks_expired(manager: GateManager, sink: NullAuditSink) -> None:
    manager.propose_for_review(_proposal(expires_after_seconds=0))
    expired = manager.expire_due(now=datetime.now(UTC) + timedelta(seconds=1))
    assert len(expired) == 1
    assert expired[0].status == "expired"
    events = [e.event_type for e in sink.events]
    assert "gate.expired" in events
