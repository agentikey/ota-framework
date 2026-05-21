from __future__ import annotations

from decimal import Decimal

import pytest

from ota_core.audit import NullAuditSink
from ota_core.contracts.audit_event import DeploymentInfo, Principal, SourceInfo
from ota_core.contracts.llm_requirements import LLMBudget
from ota_core.policy import (
    BudgetExceededError,
    IntegrationNotAllowedError,
    L0bEnforcer,
    NotInRoutineRunError,
    RoutineRunContext,
    ScopeEscalationError,
    active_context,
    verb,
)


def _deployment() -> DeploymentInfo:
    return DeploymentInfo(id="d", mode="vps", edition="core", version="0.1.0")


def _source() -> SourceInfo:
    return SourceInfo(component="test", version="0.1.0")


def _principal() -> Principal:
    return Principal(id="op:test", type="operator", display_name="Test")


def _ctx(
    *,
    routine_id: str = "ota.hello",
    integrations: frozenset[str] = frozenset(),
    scopes: dict[str, frozenset[str]] | None = None,
    budget: LLMBudget | None = None,
) -> RoutineRunContext:
    return RoutineRunContext(
        routine_id=routine_id,
        routine_run_id="11111111-1111-7111-8111-111111111111",
        trace_id="abc12300abc12300abc12300abc12300",
        principal=_principal(),
        allowed_integrations=integrations,
        declared_scopes=scopes or {},
        budget=budget,
    )


def test_routine_run_emits_started_and_completed() -> None:
    sink = NullAuditSink(deployment=_deployment(), source=_source())
    enforcer = L0bEnforcer(audit_sink=sink)
    with enforcer.routine_run(_ctx()):
        pass
    events = [e.event_type for e in sink.events]
    assert events == ["routine.run_started", "routine.run_completed"]


def test_routine_run_emits_failed_on_exception() -> None:
    sink = NullAuditSink(deployment=_deployment(), source=_source())
    enforcer = L0bEnforcer(audit_sink=sink)
    with pytest.raises(RuntimeError):
        with enforcer.routine_run(_ctx()):
            raise RuntimeError("boom")
    events = [e.event_type for e in sink.events]
    assert events == ["routine.run_started", "routine.run_failed"]


def test_active_context_returns_enforcer_and_ctx() -> None:
    sink = NullAuditSink(deployment=_deployment(), source=_source())
    enforcer = L0bEnforcer(audit_sink=sink)
    assert active_context() is None
    with enforcer.routine_run(_ctx()) as ctx:
        active = active_context()
        assert active is not None
        active_enforcer, active_ctx = active
        assert active_enforcer is enforcer
        assert active_ctx is ctx
    assert active_context() is None


def test_enforce_integration_allows_declared() -> None:
    sink = NullAuditSink(deployment=_deployment(), source=_source())
    enforcer = L0bEnforcer(audit_sink=sink)
    with enforcer.routine_run(_ctx(integrations=frozenset({"slack", "gmail"}))):
        enforcer.enforce_integration("slack")
        enforcer.enforce_integration("gmail")


def test_enforce_integration_blocks_undeclared() -> None:
    sink = NullAuditSink(deployment=_deployment(), source=_source())
    enforcer = L0bEnforcer(audit_sink=sink)
    with enforcer.routine_run(_ctx(integrations=frozenset({"slack"}))):
        with pytest.raises(IntegrationNotAllowedError):
            enforcer.enforce_integration("notion")
    blocked = [e for e in sink.events if e.event_type == "tool_call.blocked_by_policy"]
    assert blocked and blocked[0].payload["integration_id"] == "notion"


def test_enforce_scopes_passes_when_subset() -> None:
    sink = NullAuditSink(deployment=_deployment(), source=_source())
    enforcer = L0bEnforcer(audit_sink=sink)
    with enforcer.routine_run(_ctx(scopes={"gmail": frozenset({"email:send", "email:read"})})):
        enforcer.enforce_scopes("gmail", ("email:send",))


def test_enforce_scopes_blocks_escalation() -> None:
    sink = NullAuditSink(deployment=_deployment(), source=_source())
    enforcer = L0bEnforcer(audit_sink=sink)
    with enforcer.routine_run(_ctx(scopes={"gmail": frozenset({"email:read"})})):
        with pytest.raises(ScopeEscalationError) as exc:
            enforcer.enforce_scopes("gmail", ("email:read", "email:send"))
        assert exc.value.missing == ("email:send",)
    escalations = [e for e in sink.events if e.event_type == "policy.scope_escalation_attempt"]
    assert escalations


def test_budget_input_tokens_enforced() -> None:
    sink = NullAuditSink(deployment=_deployment(), source=_source())
    enforcer = L0bEnforcer(audit_sink=sink)
    budget = LLMBudget(max_input_tokens_per_run=1000, max_output_tokens_per_run=500)
    with enforcer.routine_run(_ctx(budget=budget)):
        enforcer.reserve_llm_budget(input_tokens=400, output_tokens=200)
        enforcer.record_llm_usage(input_tokens=400, output_tokens=200)
        enforcer.reserve_llm_budget(input_tokens=500, output_tokens=100)  # ok (900 / 1000)
        enforcer.record_llm_usage(input_tokens=500, output_tokens=100)
        with pytest.raises(BudgetExceededError) as exc:
            enforcer.reserve_llm_budget(input_tokens=200)  # would put us at 1100 / 1000
        assert exc.value.kind == "input_tokens"


def test_budget_usd_enforced() -> None:
    sink = NullAuditSink(deployment=_deployment(), source=_source())
    enforcer = L0bEnforcer(audit_sink=sink)
    budget = LLMBudget(max_usd_per_run=0.10)
    with enforcer.routine_run(_ctx(budget=budget)):
        enforcer.reserve_llm_budget(usd=Decimal("0.05"))
        enforcer.record_llm_usage(input_tokens=0, output_tokens=0, usd=Decimal("0.05"))
        with pytest.raises(BudgetExceededError) as exc:
            enforcer.reserve_llm_budget(usd=Decimal("0.10"))
        assert exc.value.kind == "usd"


def test_no_budget_record_does_not_raise() -> None:
    sink = NullAuditSink(deployment=_deployment(), source=_source())
    enforcer = L0bEnforcer(audit_sink=sink)
    with enforcer.routine_run(_ctx()):
        enforcer.reserve_llm_budget(input_tokens=10**9)


def test_record_llm_usage_updates_context() -> None:
    sink = NullAuditSink(deployment=_deployment(), source=_source())
    enforcer = L0bEnforcer(audit_sink=sink)
    with enforcer.routine_run(_ctx()) as ctx:
        enforcer.record_llm_usage(input_tokens=10, output_tokens=20, usd=Decimal("0.01"))
        assert ctx.input_tokens_used == 10
        assert ctx.output_tokens_used == 20
        assert ctx.usd_spent == Decimal("0.01")


def test_verb_decorator_wraps_invocation_in_audit() -> None:
    @verb(idempotency="best_effort", required_scopes=["messaging:send"], destructive=False)
    def send_message(target: str, body: str) -> str:
        return f"sent to {target}: {body}"

    sink = NullAuditSink(deployment=_deployment(), source=_source())
    enforcer = L0bEnforcer(audit_sink=sink)
    with enforcer.routine_run(_ctx()) as ctx:
        result = send_message("@omar", body="hi")
        assert result == "sent to @omar: hi"
        assert ctx.tool_calls_made == 1
    events = [e.event_type for e in sink.events]
    assert "tool_call.invoked" in events
    assert "tool_call.succeeded" in events


def test_verb_decorator_emits_failed_on_exception() -> None:
    @verb(idempotency="best_effort", required_scopes=[], destructive=False)
    def boom() -> None:
        raise ValueError("nope")

    sink = NullAuditSink(deployment=_deployment(), source=_source())
    enforcer = L0bEnforcer(audit_sink=sink)
    with enforcer.routine_run(_ctx()):
        with pytest.raises(ValueError):
            boom()
    events = [e.event_type for e in sink.events]
    assert "tool_call.failed" in events
    assert "tool_call.succeeded" not in events


def test_verb_decorator_no_op_outside_run() -> None:
    @verb(idempotency="best_effort", required_scopes=[], destructive=False)
    def ping() -> str:
        return "pong"

    assert ping() == "pong"


def test_verb_decorator_preserves_metadata() -> None:
    @verb(idempotency="guaranteed", required_scopes=["x:y"], destructive=True)
    def f() -> None:
        pass

    assert f._ota_verb_meta == {
        "idempotency": "guaranteed",
        "required_scopes": ["x:y"],
        "destructive": True,
    }


def test_enforcement_outside_context_raises() -> None:
    sink = NullAuditSink(deployment=_deployment(), source=_source())
    enforcer = L0bEnforcer(audit_sink=sink)
    with pytest.raises(NotInRoutineRunError):
        enforcer.enforce_integration("slack")


def test_routine_run_audit_payload_includes_counters() -> None:
    sink = NullAuditSink(deployment=_deployment(), source=_source())
    enforcer = L0bEnforcer(audit_sink=sink)
    with enforcer.routine_run(_ctx()):
        enforcer.record_llm_usage(input_tokens=5, output_tokens=3)
    completed = next(e for e in sink.events if e.event_type == "routine.run_completed")
    assert completed.payload["input_tokens_used"] == 5
    assert completed.payload["output_tokens_used"] == 3
