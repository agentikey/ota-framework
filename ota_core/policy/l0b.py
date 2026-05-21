from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from ota_core.audit import AuditSink
from ota_core.contracts.audit_event import EventType, Principal
from ota_core.contracts.llm_requirements import LLMBudget
from ota_core.contracts.shared import Severity
from ota_core.observability import ObservabilitySink
from ota_core.policy.errors import (
    BudgetExceededError,
    IntegrationNotAllowedError,
    NotInRoutineRunError,
    ScopeEscalationError,
)
from ota_core.trace import bind_trace


@dataclass
class RoutineRunContext:
    routine_id: str
    routine_run_id: str
    trace_id: str
    principal: Principal
    allowed_integrations: frozenset[str] = frozenset()
    declared_scopes: Mapping[str, frozenset[str]] = field(default_factory=dict)
    budget: LLMBudget | None = None
    request_id: str | None = None
    tenant_id: str | None = None

    input_tokens_used: int = 0
    output_tokens_used: int = 0
    usd_spent: Decimal = Decimal("0")
    tool_calls_made: int = 0

    def remaining_input_tokens(self) -> int | None:
        if self.budget is None or self.budget.max_input_tokens_per_run is None:
            return None
        return max(0, self.budget.max_input_tokens_per_run - self.input_tokens_used)

    def remaining_output_tokens(self) -> int | None:
        if self.budget is None or self.budget.max_output_tokens_per_run is None:
            return None
        return max(0, self.budget.max_output_tokens_per_run - self.output_tokens_used)

    def remaining_usd(self) -> Decimal | None:
        if self.budget is None or self.budget.max_usd_per_run is None:
            return None
        return max(Decimal("0"), Decimal(str(self.budget.max_usd_per_run)) - self.usd_spent)


_ACTIVE: ContextVar[tuple[L0bEnforcer, RoutineRunContext] | None] = ContextVar(
    "ota_l0b_active", default=None
)


def active_context() -> tuple[L0bEnforcer, RoutineRunContext] | None:
    return _ACTIVE.get()


class L0bEnforcer:
    def __init__(
        self,
        *,
        audit_sink: AuditSink,
        observability: ObservabilitySink | None = None,
    ) -> None:
        self._audit = audit_sink
        self._obs = observability

    @contextmanager
    def routine_run(self, ctx: RoutineRunContext) -> Iterator[RoutineRunContext]:
        active_token = _ACTIVE.set((self, ctx))
        try:
            with bind_trace(trace_id=ctx.trace_id):
                self._audit.emit(
                    event_type="routine.run_started",
                    severity="info",
                    principal=ctx.principal,
                    payload={
                        "routine_id": ctx.routine_id,
                        "routine_run_id": ctx.routine_run_id,
                    },
                    routine_run_id=ctx.routine_run_id,
                    request_id=ctx.request_id,
                    tenant_id=ctx.tenant_id,
                )
                try:
                    yield ctx
                except BaseException as exc:
                    self._audit.emit(
                        event_type="routine.run_failed",
                        severity="error",
                        principal=ctx.principal,
                        payload={
                            "routine_id": ctx.routine_id,
                            "routine_run_id": ctx.routine_run_id,
                            "error_class": type(exc).__name__,
                            "error_message": str(exc),
                        },
                        routine_run_id=ctx.routine_run_id,
                        request_id=ctx.request_id,
                        tenant_id=ctx.tenant_id,
                    )
                    raise
                else:
                    self._audit.emit(
                        event_type="routine.run_completed",
                        severity="info",
                        principal=ctx.principal,
                        payload={
                            "routine_id": ctx.routine_id,
                            "routine_run_id": ctx.routine_run_id,
                            "tool_calls_made": ctx.tool_calls_made,
                            "input_tokens_used": ctx.input_tokens_used,
                            "output_tokens_used": ctx.output_tokens_used,
                            "usd_spent": str(ctx.usd_spent),
                        },
                        routine_run_id=ctx.routine_run_id,
                        request_id=ctx.request_id,
                        tenant_id=ctx.tenant_id,
                    )
        finally:
            _ACTIVE.reset(active_token)

    def enforce_integration(self, integration_id: str) -> None:
        ctx = self._require_ctx()
        if ctx.allowed_integrations and integration_id not in ctx.allowed_integrations:
            self._audit.emit(
                event_type="tool_call.blocked_by_policy",
                severity="warn",
                principal=ctx.principal,
                payload={
                    "reason": "integration_not_allowed",
                    "integration_id": integration_id,
                    "allowed": sorted(ctx.allowed_integrations),
                },
                routine_run_id=ctx.routine_run_id,
            )
            raise IntegrationNotAllowedError(
                integration_id=integration_id,
                allowed=tuple(sorted(ctx.allowed_integrations)),
            )

    def enforce_scopes(self, integration_id: str, required_scopes: tuple[str, ...]) -> None:
        ctx = self._require_ctx()
        declared = ctx.declared_scopes.get(integration_id, frozenset())
        missing = tuple(s for s in required_scopes if s not in declared)
        if missing:
            self._audit.emit(
                event_type="policy.scope_escalation_attempt",
                severity="warn",
                principal=ctx.principal,
                payload={
                    "integration_id": integration_id,
                    "missing_scopes": list(missing),
                    "declared_scopes": sorted(declared),
                },
                routine_run_id=ctx.routine_run_id,
            )
            raise ScopeEscalationError(
                integration_id=integration_id,
                missing=missing,
                declared=tuple(sorted(declared)),
            )

    def reserve_llm_budget(
        self,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        usd: Decimal | float = Decimal("0"),
    ) -> None:
        ctx = self._require_ctx()
        budget = ctx.budget
        if budget is None:
            return
        usd_d = usd if isinstance(usd, Decimal) else Decimal(str(usd))
        if budget.max_input_tokens_per_run is not None:
            projected = ctx.input_tokens_used + input_tokens
            if projected > budget.max_input_tokens_per_run:
                self._emit_budget_exceeded(
                    ctx,
                    "input_tokens",
                    budget.max_input_tokens_per_run,
                    ctx.input_tokens_used,
                    projected,
                )
                raise BudgetExceededError(
                    "input_tokens",
                    budget.max_input_tokens_per_run,
                    ctx.input_tokens_used,
                    projected,
                )
        if budget.max_output_tokens_per_run is not None:
            projected = ctx.output_tokens_used + output_tokens
            if projected > budget.max_output_tokens_per_run:
                self._emit_budget_exceeded(
                    ctx,
                    "output_tokens",
                    budget.max_output_tokens_per_run,
                    ctx.output_tokens_used,
                    projected,
                )
                raise BudgetExceededError(
                    "output_tokens",
                    budget.max_output_tokens_per_run,
                    ctx.output_tokens_used,
                    projected,
                )
        if budget.max_usd_per_run is not None:
            projected_usd = ctx.usd_spent + usd_d
            limit = Decimal(str(budget.max_usd_per_run))
            if projected_usd > limit:
                self._emit_budget_exceeded(
                    ctx, "usd", float(limit), float(ctx.usd_spent), float(projected_usd)
                )
                raise BudgetExceededError(
                    "usd", float(limit), float(ctx.usd_spent), float(projected_usd)
                )

    def record_llm_usage(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
        usd: Decimal | float = Decimal("0"),
        model: str | None = None,
    ) -> None:
        ctx = self._require_ctx()
        ctx.input_tokens_used += input_tokens
        ctx.output_tokens_used += output_tokens
        ctx.usd_spent += usd if isinstance(usd, Decimal) else Decimal(str(usd))
        self._audit.emit(
            event_type="llm.response",
            severity="info",
            principal=ctx.principal,
            payload={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "usd": str(usd),
                "model": model,
            },
            routine_run_id=ctx.routine_run_id,
        )

    def record_verb_invocation(
        self,
        *,
        verb_name: str,
        verb_meta: dict[str, Any],
        kwargs: Mapping[str, Any],
    ) -> Callable[[bool, BaseException | None], None]:
        ctx = self._require_ctx()
        ctx.tool_calls_made += 1
        invocation_id = uuid.uuid4().hex
        self._audit.emit(
            event_type="tool_call.invoked",
            severity="info",
            principal=ctx.principal,
            payload={
                "verb": verb_name,
                "invocation_id": invocation_id,
                "destructive": verb_meta.get("destructive", False),
                "idempotency": verb_meta.get("idempotency"),
                "required_scopes": verb_meta.get("required_scopes", []),
                "kwarg_keys": sorted(kwargs.keys()),
            },
            routine_run_id=ctx.routine_run_id,
        )

        def complete(succeeded: bool, error: BaseException | None) -> None:
            event: EventType = "tool_call.succeeded" if succeeded else "tool_call.failed"
            severity: Severity = "info" if succeeded else "error"
            payload: dict[str, Any] = {
                "verb": verb_name,
                "invocation_id": invocation_id,
            }
            if error is not None:
                payload["error_class"] = type(error).__name__
                payload["error_message"] = str(error)
            self._audit.emit(
                event_type=event,
                severity=severity,
                principal=ctx.principal,
                payload=payload,
                routine_run_id=ctx.routine_run_id,
            )

        return complete

    def _require_ctx(self) -> RoutineRunContext:
        active = _ACTIVE.get()
        if active is None or active[0] is not self:
            raise NotInRoutineRunError(
                "L0b enforcement called outside of an active routine_run context"
            )
        return active[1]

    def _emit_budget_exceeded(
        self,
        ctx: RoutineRunContext,
        kind: str,
        limit: float,
        used: float,
        requested: float,
    ) -> None:
        self._audit.emit(
            event_type="policy.budget_exceeded",
            severity="error",
            principal=ctx.principal,
            payload={
                "kind": kind,
                "limit": limit,
                "used": used,
                "requested": requested,
            },
            routine_run_id=ctx.routine_run_id,
        )
