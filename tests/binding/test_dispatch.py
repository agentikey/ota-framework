"""End-to-end dispatch tests — Phase 3 tracer bullet.

Builds a real DispatchContext (FilesystemIntegrationSource + AdapterRegistry +
BindingResolver), installs it, sets up an L0bEnforcer routine_run, then calls
generated verbs from `ota_connect.messaging` / `ota_connect.email` and asserts:

1. The mock adapter received the call.
2. tool_call.invoked / tool_call.succeeded audit events were emitted.
3. Integration + scope enforcement runs before adapter invocation.
4. Adapter-thrown exceptions get normalized to OTAConnectError.
"""

from __future__ import annotations

import pytest

from ota_connect._types import ChannelRef
from ota_connect._types.errors import AdapterUnavailable, OTAConnectError
from ota_connect.binding import (
    DispatchContext,
    NotConfiguredError,
    dispatch_context,
)
from ota_connect.email import send_email
from ota_connect.messaging import send_message
from ota_core.audit import NullAuditSink
from ota_core.contracts.audit_event import Principal
from ota_core.policy import (
    IntegrationNotAllowedError,
    L0bEnforcer,
    RoutineRunContext,
    ScopeEscalationError,
)


def _routine_ctx(
    *,
    integrations: frozenset[str] = frozenset(),
    scopes: dict[str, frozenset[str]] | None = None,
    principal: Principal,
) -> RoutineRunContext:
    return RoutineRunContext(
        routine_id="ota.test",
        routine_run_id="11111111-1111-7111-8111-111111111111",
        trace_id="abc12300abc12300abc12300abc12300",
        principal=principal,
        allowed_integrations=integrations,
        declared_scopes=scopes or {},
    )


def test_dispatch_without_context_raises() -> None:
    target = ChannelRef(id="C1", kind="channel", name="general", adapter="mock_messaging")
    with pytest.raises(NotConfiguredError):
        send_message(target=target, content="hi")


def test_tracer_bullet_messaging_send_dm(
    dispatch_ctx: DispatchContext,
    enforcer: L0bEnforcer,
    audit_sink: NullAuditSink,
) -> None:
    """Phase 3 tracer bullet: routine calls send_message, mock adapter receives
    it, audit log captures dispatch with trace_id."""
    p = audit_sink._deployment
    principal = Principal(id="op:test", type="operator", display_name="Test")
    ctx = _routine_ctx(
        integrations=frozenset({"mock.messaging"}),
        scopes={"mock.messaging": frozenset({"messaging:send"})},
        principal=principal,
    )
    target = ChannelRef(id="C1", kind="channel", name="general", adapter="mock_messaging")
    with dispatch_context(dispatch_ctx):
        with enforcer.routine_run(ctx):
            ref = send_message(target=target, content="hello world")
    assert ref.adapter == "mock_messaging"
    assert ref.channel.id == "C1"
    # Verify mock received the call
    mock = dispatch_ctx.registry.load(
        "mock_messaging", capability="messaging", verb="send_message"
    ).impl
    assert len(mock.outbox) == 1  # type: ignore[attr-defined]
    assert mock.outbox[0]["content"] == "hello world"  # type: ignore[attr-defined]
    # Verify audit captured the dispatch
    events = [e.event_type for e in audit_sink.events]
    assert "routine.run_started" in events
    assert "tool_call.invoked" in events
    assert "tool_call.succeeded" in events
    assert "routine.run_completed" in events
    # trace_id flows through
    for e in audit_sink.events:
        assert e.trace_id == ctx.trace_id
    assert p is not None  # silence unused-var checker


def test_disallowed_integration_blocks_dispatch(
    dispatch_ctx: DispatchContext,
    enforcer: L0bEnforcer,
    audit_sink: NullAuditSink,
) -> None:
    principal = Principal(id="op:test", type="operator", display_name="Test")
    ctx = _routine_ctx(
        integrations=frozenset({"some.other.integration"}),
        principal=principal,
    )
    target = ChannelRef(id="C1", kind="channel", name="general", adapter="mock_messaging")
    with dispatch_context(dispatch_ctx):
        with enforcer.routine_run(ctx):
            with pytest.raises(IntegrationNotAllowedError):
                send_message(target=target, content="blocked")
    events = [e.event_type for e in audit_sink.events]
    assert "tool_call.blocked_by_policy" in events
    # And tool_call.failed because the @verb decorator caught the exception
    assert "tool_call.failed" in events


def test_missing_scope_blocks_dispatch(
    dispatch_ctx: DispatchContext,
    enforcer: L0bEnforcer,
    audit_sink: NullAuditSink,
) -> None:
    principal = Principal(id="op:test", type="operator", display_name="Test")
    ctx = _routine_ctx(
        integrations=frozenset({"mock.messaging"}),
        scopes={"mock.messaging": frozenset({"messaging:read"})},  # missing send
        principal=principal,
    )
    target = ChannelRef(id="C1", kind="channel", name="general", adapter="mock_messaging")
    with dispatch_context(dispatch_ctx):
        with enforcer.routine_run(ctx):
            with pytest.raises(ScopeEscalationError):
                send_message(target=target, content="needs send scope")
    events = [e.event_type for e in audit_sink.events]
    assert "policy.scope_escalation_attempt" in events


def test_email_send_dispatches_through_mock(
    dispatch_ctx: DispatchContext,
    enforcer: L0bEnforcer,
) -> None:
    principal = Principal(id="op:test", type="operator", display_name="Test")
    ctx = _routine_ctx(
        integrations=frozenset({"mock.email"}),
        scopes={"mock.email": frozenset({"email:send"})},
        principal=principal,
    )
    with dispatch_context(dispatch_ctx):
        with enforcer.routine_run(ctx):
            ref = send_email(
                to=["mailto:bob@example.com"],
                subject="hi",
                body="body",
            )
    assert ref.adapter == "mock_email"
    mock = dispatch_ctx.registry.load("mock_email", capability="email", verb="send_email").impl
    assert len(mock.outbox) == 1  # type: ignore[attr-defined]


def test_adapter_raised_runtime_error_normalized_to_adapter_unavailable(
    dispatch_ctx: DispatchContext,
    enforcer: L0bEnforcer,
) -> None:
    """Raise a plain RuntimeError from the mock and observe normalization."""

    def boom(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("upstream went sideways")

    mock = dispatch_ctx.registry.load(
        "mock_messaging", capability="messaging", verb="send_message"
    ).impl
    object.__setattr__(mock, "_verb_send_message", boom)

    principal = Principal(id="op:test", type="operator", display_name="Test")
    ctx = _routine_ctx(
        integrations=frozenset({"mock.messaging"}),
        scopes={"mock.messaging": frozenset({"messaging:send"})},
        principal=principal,
    )
    target = ChannelRef(id="C1", kind="channel", name="general", adapter="mock_messaging")

    with dispatch_context(dispatch_ctx):
        with enforcer.routine_run(ctx):
            with pytest.raises(AdapterUnavailable) as exc_info:
                send_message(target=target, content="hi")
    assert exc_info.value.adapter == "mock_messaging"
    assert exc_info.value.capability == "messaging"
    assert exc_info.value.verb == "send_message"
    assert exc_info.value.retryable is True
    assert isinstance(exc_info.value, OTAConnectError)


def test_dispatch_works_outside_routine_run(
    dispatch_ctx: DispatchContext,
) -> None:
    """Calling a verb without a routine_run skips L0b enforcement but still dispatches."""
    target = ChannelRef(id="C1", kind="channel", name="general", adapter="mock_messaging")
    with dispatch_context(dispatch_ctx):
        ref = send_message(target=target, content="naked call")
    assert ref.adapter == "mock_messaging"
