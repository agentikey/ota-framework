from __future__ import annotations

from pathlib import Path

import pytest

from ota_core.audit import FileAuditReader, FileAuditSink
from ota_core.contracts.audit_event import DeploymentInfo, Principal, SourceInfo
from ota_core.storage.database import Database
from ota_routines.email_triage.helpers import (
    DriftConfig,
    DriftDetector,
    TrustPromotion,
    WhyLookup,
    content_hash,
)
from ota_routines.email_triage.state import EmailTriageState


def _deployment() -> DeploymentInfo:
    return DeploymentInfo(id="d", mode="vps", edition="core", version="0.1.0")


def _source() -> SourceInfo:
    return SourceInfo(component="test", version="0.1.0")


def _principal() -> Principal:
    return Principal(id="op:test", type="operator", display_name="Test")


@pytest.fixture
def state(tmp_path: Path) -> EmailTriageState:
    db = Database(tmp_path / "triage.db")
    return EmailTriageState(db, trust_threshold=3)


def test_content_hash_is_stable_under_whitespace() -> None:
    a = content_hash(subject="Hi  there", body="hello\n\nworld", sender="b@x")
    b = content_hash(subject="Hi there", body="hello world", sender="B@X ")
    assert a == b


def test_content_hash_differs_for_different_senders() -> None:
    a = content_hash(subject="Hi", body="hello", sender="alice@x")
    b = content_hash(subject="Hi", body="hello", sender="bob@x")
    assert a != b


def test_trust_promotion_evaluate_starts_requiring_approval(
    state: EmailTriageState,
) -> None:
    t = TrustPromotion(state, allowed_auto_send_templates=("inquiry",))
    d = t.evaluate("inquiry")
    assert d.auto_send is False
    assert d.requires_approval is True


def test_trust_promotion_auto_sends_after_threshold(state: EmailTriageState) -> None:
    t = TrustPromotion(state, allowed_auto_send_templates=("inquiry",))
    for _ in range(3):
        t.record_approval("inquiry")
    d = t.evaluate("inquiry")
    assert d.auto_send is True


def test_trust_promotion_demotes_on_edit(state: EmailTriageState) -> None:
    t = TrustPromotion(state, allowed_auto_send_templates=("inquiry",))
    for _ in range(3):
        t.record_approval("inquiry")
    assert t.evaluate("inquiry").auto_send
    t.record_edit("inquiry", email_id="e1")
    assert not t.evaluate("inquiry").auto_send


def test_drift_detector_no_signal_on_empty(state: EmailTriageState) -> None:
    signals = DriftDetector(state, config=DriftConfig(window_hours=1)).evaluate()
    assert signals == []


def test_drift_detector_flags_high_skip_rate(state: EmailTriageState) -> None:
    for i in range(7):
        state.record_decision(
            routine_run_id="rr",
            email_id=f"e{i}",
            action="skipped",
            category=None,
            template=None,
            payload={},
        )
    state.record_decision(
        routine_run_id="rr",
        email_id="e7",
        action="drafted",
        category="inquiry",
        template="inquiry",
        payload={},
    )
    signals = DriftDetector(
        state, config=DriftConfig(window_hours=1, processed_skip_ratio_alarm=0.5)
    ).evaluate()
    assert any(s.kind == "skip_ratio_high" for s in signals)


def test_drift_detector_flags_low_send_ratio(state: EmailTriageState) -> None:
    for i in range(5):
        state.record_decision(
            routine_run_id="rr",
            email_id=f"e{i}",
            action="drafted",
            category="inquiry",
            template="inquiry",
            payload={},
        )
    state.record_decision(
        routine_run_id="rr",
        email_id="e6",
        action="approved",
        category="inquiry",
        template="inquiry",
        payload={},
    )
    signals = DriftDetector(
        state, config=DriftConfig(window_hours=1, draft_send_ratio_alarm=0.5)
    ).evaluate()
    assert any(s.kind == "draft_send_ratio_low" for s in signals)


def test_why_lookup_returns_decisions(state: EmailTriageState, tmp_path: Path) -> None:
    state.record_decision(
        routine_run_id="rr-1",
        email_id="e1",
        action="drafted",
        category="inquiry",
        template="inquiry",
        payload={"subject": "Hi"},
    )
    # Add an audit event for the same routine_run_id that references e1
    sink = FileAuditSink(tmp_path / "audit", deployment=_deployment(), source=_source())
    sink.emit(
        event_type="tool_call.invoked",
        severity="info",
        principal=_principal(),
        payload={"verb": "email.send_email", "email_id": "e1"},
        routine_run_id="rr-1",
    )
    sink.close()
    reader = FileAuditReader(tmp_path / "audit")
    why = WhyLookup(state, reader)
    entries = why.lookup("e1")
    assert len(entries) == 2
    kinds = [e.kind for e in entries]
    assert "decision.drafted" in kinds
    assert "tool_call.invoked" in kinds
