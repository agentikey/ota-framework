from __future__ import annotations

from ota_connect.binding import ActionEvent, ActionRouter
from ota_core.audit import NullAuditSink
from ota_core.contracts.audit_event import Principal


def test_dispatch_invokes_registered_handler(audit_sink: NullAuditSink) -> None:
    received: list[ActionEvent] = []

    router = ActionRouter(
        audit_sink=audit_sink,
        principal=_principal(),
    )
    router.register("ota.test", received.append)
    event = ActionEvent(
        kind="messaging.action_triggered",
        routine_id="ota.test",
        adapter_id="mock_messaging",
        integration_id="mock.messaging",
        payload={"button": "approve"},
        correlation_id="msg-1",
    )
    assert router.dispatch(event) is True
    assert received == [event]
    types = [e.event_type for e in audit_sink.events]
    assert "integration.messaging.action_triggered" in types


def test_dispatch_drops_unknown_routine_but_audits(audit_sink: NullAuditSink) -> None:
    router = ActionRouter(audit_sink=audit_sink, principal=_principal())
    event = ActionEvent(
        kind="messaging.action_triggered",
        routine_id="ota.unknown",
        adapter_id="mock_messaging",
        integration_id="mock.messaging",
        payload={},
    )
    assert router.dispatch(event) is False
    # audit emitted with delivered=False, severity=warn
    types = [(e.event_type, e.severity) for e in audit_sink.events]
    assert ("integration.messaging.action_triggered", "warn") in types


def test_unregister(audit_sink: NullAuditSink) -> None:
    router = ActionRouter(audit_sink=audit_sink, principal=_principal())
    router.register("ota.test", lambda _e: None)
    router.unregister("ota.test")
    event = ActionEvent(
        kind="messaging.action_triggered",
        routine_id="ota.test",
        adapter_id="mock_messaging",
        integration_id="mock.messaging",
    )
    assert router.dispatch(event) is False


def _principal() -> Principal:
    return Principal(id="op:test", type="operator", display_name="Test")
