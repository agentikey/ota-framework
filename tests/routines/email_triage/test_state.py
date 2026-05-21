from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from ota_core.storage.database import Database
from ota_routines.email_triage.state import EmailTriageState


@pytest.fixture
def state(tmp_path: Path) -> EmailTriageState:
    db = Database(tmp_path / "triage.db")
    return EmailTriageState(db, trust_threshold=3)


def test_mark_processed_first_time_returns_true(state: EmailTriageState) -> None:
    assert state.mark_processed(email_id="e1", content_hash="h1") is True
    assert state.mark_processed(email_id="e1", content_hash="h1") is False


def test_is_processed(state: EmailTriageState) -> None:
    assert not state.is_processed(email_id="e1", content_hash="h1")
    state.mark_processed(email_id="e1", content_hash="h1")
    assert state.is_processed(email_id="e1", content_hash="h1")


def test_record_unedited_approval_increments(state: EmailTriageState) -> None:
    trust = state.record_unedited_approval("inquiry")
    assert trust.consecutive_unedited == 1
    assert trust.total_sent == 1
    trust = state.record_unedited_approval("inquiry")
    assert trust.consecutive_unedited == 2


def test_trust_promotion_threshold_promotes(state: EmailTriageState) -> None:
    state.opt_in_auto_send("inquiry", enabled=True)
    state.record_unedited_approval("inquiry")
    state.record_unedited_approval("inquiry")
    trust = state.record_unedited_approval("inquiry")
    assert trust.auto_send_enabled is True
    assert trust.consecutive_unedited == 3


def test_record_edit_resets_and_demotes(state: EmailTriageState) -> None:
    state.opt_in_auto_send("inquiry", enabled=True)
    state.record_unedited_approval("inquiry")
    state.record_unedited_approval("inquiry")
    state.record_unedited_approval("inquiry")  # promoted
    trust = state.record_edit("inquiry", email_id="e1")
    assert trust.consecutive_unedited == 0
    assert trust.auto_send_enabled is False
    assert trust.demoted_at is not None


def test_record_decision_persists(state: EmailTriageState) -> None:
    state.record_decision(
        routine_run_id="rr-1",
        email_id="e1",
        action="drafted",
        category="inquiry",
        template="inquiry",
        payload={"subject": "Hi", "body": "..."},
    )
    rows = state.by_email_id("e1")
    assert len(rows) == 1
    assert rows[0].action == "drafted"
    assert rows[0].payload["subject"] == "Hi"


def test_recent_decisions_filters_by_window(state: EmailTriageState) -> None:
    for i in range(5):
        state.record_decision(
            routine_run_id="rr-1",
            email_id=f"e{i}",
            action="drafted",
            category="inquiry",
            template="inquiry",
            payload={},
        )
    recent = state.recent_decisions(within=timedelta(hours=1))
    assert len(recent) == 5
    recent_skipped = state.recent_decisions(within=timedelta(hours=1), actions=["skipped"])
    assert recent_skipped == []


def test_by_routine_run_returns_chronological(state: EmailTriageState) -> None:
    for i in range(3):
        state.record_decision(
            routine_run_id="rr-1",
            email_id=f"e{i}",
            action="drafted",
            category=None,
            template=None,
            payload={},
        )
    rows = state.by_routine_run("rr-1")
    assert [r.email_id for r in rows] == ["e0", "e1", "e2"]


def test_list_trust_returns_all(state: EmailTriageState) -> None:
    state.record_unedited_approval("a")
    state.record_unedited_approval("b")
    rows = state.list_trust()
    assert {r.template for r in rows} == {"a", "b"}
