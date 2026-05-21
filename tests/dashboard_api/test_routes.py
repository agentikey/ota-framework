from __future__ import annotations

from fastapi.testclient import TestClient

from ota_core.audit import FileAuditSink
from ota_core.contracts.audit_event import DeploymentInfo, Principal, SourceInfo
from ota_core.policy.gates import GateManager, GateProposal
from ota_routines.email_triage.state import EmailTriageState


def _deployment() -> DeploymentInfo:
    return DeploymentInfo(id="d", mode="vps", edition="core", version="0.1.0")


def _source() -> SourceInfo:
    return SourceInfo(component="test", version="0.1.0")


def _principal() -> Principal:
    return Principal(id="op:test", type="operator", display_name="Test")


def _proposal(**overrides: object) -> GateProposal:
    base: dict[str, object] = {
        "routine_id": "ota.email-triage",
        "routine_run_id": "rr-1",
        "gate_id": "draft_review",
        "approval_modes": ("approve",),
        "kind": "preview",
        "summary": "Email to bob",
        "payload": {"subject": "Hi", "body": "..."},
    }
    base.update(overrides)
    return GateProposal(**base)  # type: ignore[arg-type]


def test_healthz_returns_ok(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": "0.1.0"}


def test_fleet_returns_single_entry(client: TestClient) -> None:
    r = client.get("/api/v1/fleet")
    assert r.status_code == 200
    data = r.json()
    assert len(data["entries"]) == 1
    assert "ota.email-triage" in data["entries"][0]["routines"]


def test_approvals_list_empty_initially(client: TestClient) -> None:
    r = client.get("/api/v1/approvals")
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_approvals_list_after_propose(client: TestClient, gate_manager: GateManager) -> None:
    gate_manager.propose_for_review(_proposal())
    r = client.get("/api/v1/approvals")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["gate_id"] == "draft_review"


def test_approvals_filter_by_routine(client: TestClient, gate_manager: GateManager) -> None:
    gate_manager.propose_for_review(_proposal(routine_id="ota.email-triage"))
    gate_manager.propose_for_review(_proposal(routine_id="ota.hello"))
    r = client.get("/api/v1/approvals", params={"routine_id": "ota.email-triage"})
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["routine_id"] == "ota.email-triage"


def test_approvals_decide_approve(client: TestClient, gate_manager: GateManager) -> None:
    instance = gate_manager.propose_for_review(_proposal())
    r = client.post(
        f"/api/v1/approvals/{instance.id}/decide",
        json={"action": "approve"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "approved"


def test_approvals_decide_edit_and_approve(client: TestClient, gate_manager: GateManager) -> None:
    instance = gate_manager.propose_for_review(_proposal())
    r = client.post(
        f"/api/v1/approvals/{instance.id}/decide",
        json={"action": "edit_and_approve", "edits": {"subject": "edited"}},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "modified_and_approved"


def test_approvals_decide_invalid_returns_400(
    client: TestClient, gate_manager: GateManager
) -> None:
    r = client.post(
        "/api/v1/approvals/missing/decide",
        json={"action": "approve"},
    )
    assert r.status_code == 400


def test_audit_scan_returns_events(client: TestClient, audit_sink: FileAuditSink) -> None:
    audit_sink.emit(event_type="tool_call.invoked", severity="info", principal=_principal())
    audit_sink.close()
    r = client.get("/api/v1/audit")
    assert r.status_code == 200
    events = r.json()["events"]
    assert len(events) == 1
    assert events[0]["event_type"] == "tool_call.invoked"


def test_audit_by_trace(client: TestClient, audit_sink: FileAuditSink) -> None:
    audit_sink.emit(
        event_type="tool_call.invoked",
        severity="info",
        principal=_principal(),
        trace_id="a" * 32,
    )
    audit_sink.emit(
        event_type="tool_call.invoked",
        severity="info",
        principal=_principal(),
        trace_id="b" * 32,
    )
    audit_sink.close()
    r = client.get(f"/api/v1/audit/trace/{'a' * 32}")
    assert r.status_code == 200
    assert len(r.json()["events"]) == 1


def test_audit_csv_export(client: TestClient, audit_sink: FileAuditSink) -> None:
    audit_sink.emit(event_type="tool_call.invoked", severity="info", principal=_principal())
    audit_sink.close()
    r = client.get("/api/v1/audit.csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "tool_call.invoked" in r.text


def test_why_returns_decision_trail(client: TestClient, triage_state: EmailTriageState) -> None:
    triage_state.record_decision(
        routine_run_id="rr-1",
        email_id="e1",
        action="drafted",
        category="inquiry",
        template="inquiry",
        payload={"subject": "Hi"},
    )
    r = client.get("/api/v1/why/e1")
    assert r.status_code == 200
    entries = r.json()["entries"]
    assert any(e["kind"] == "decision.drafted" for e in entries)


def test_get_knobs_for_unknown_routine_404(client: TestClient) -> None:
    r = client.get("/api/v1/routines/ota.unknown/knobs")
    assert r.status_code == 404


def test_post_knobs_updates_inmemory(client: TestClient) -> None:
    r = client.post(
        "/api/v1/routines/ota.email-triage/knobs",
        json={"knobs": {"operator_first_name": "Alex"}},
    )
    assert r.status_code == 200
    r = client.get("/api/v1/routines/ota.email-triage/knobs")
    assert r.status_code == 200
    knobs = r.json()["knobs"]
    assert any(k["name"] == "operator_first_name" for k in knobs)


def test_banner_lifecycle(client: TestClient) -> None:
    r = client.get("/api/v1/notifications/banner")
    assert r.json()["active"] is False
    r = client.post(
        "/api/v1/notifications/banner",
        json={"severity": "critical", "title": "Drift detected"},
    )
    assert r.json()["active"] is True
    assert r.json()["severity"] == "critical"
    r = client.delete("/api/v1/notifications/banner")
    assert r.json()["active"] is False
