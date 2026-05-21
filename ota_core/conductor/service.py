from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ota_core.audit import AuditSink
from ota_core.conductor.errors import RoutineNotRegisteredError
from ota_core.conductor.router import (
    Intent,
    IntentRouter,
    RegisteredRoutine,
    RoutingDecision,
)
from ota_core.contracts.audit_event import Principal
from ota_core.observability import ObservabilitySink
from ota_core.systems import Capability, RoutineEngine, RoutineRunResult


class Conductor:
    def __init__(
        self,
        *,
        router: IntentRouter,
        engine: RoutineEngine,
        audit_sink: AuditSink,
        observability: ObservabilitySink,
    ) -> None:
        self._router = router
        self._engine = engine
        self._audit = audit_sink
        self._obs = observability
        self._registry: dict[str, RegisteredRoutine] = {}

    @property
    def router(self) -> IntentRouter:
        return self._router

    def register_routine(
        self,
        routine_id: str,
        *,
        capabilities: Mapping[str, Capability] | None = None,
        knob_overrides: Mapping[str, Any] | None = None,
    ) -> None:
        self._registry[routine_id] = RegisteredRoutine(
            routine_id=routine_id,
            capabilities=dict(capabilities or {}),
            knob_overrides=dict(knob_overrides or {}),
        )

    def deregister_routine(self, routine_id: str) -> None:
        self._registry.pop(routine_id, None)

    def registered(self) -> list[str]:
        return sorted(self._registry.keys())

    def decide(self, intent: Intent) -> RoutingDecision:
        return self._router.route(intent)

    async def dispatch(
        self,
        intent: Intent,
        *,
        principal: Principal,
        request_id: str | None = None,
    ) -> RoutineRunResult:
        decision = self._router.route(intent)
        registered = self._registry.get(decision.routine_id)
        if registered is None:
            raise RoutineNotRegisteredError(decision.routine_id)
        self._obs.metric(
            "conductor.route_decided",
            1.0,
            attributes={
                "routine_id": decision.routine_id,
                "channel": intent.channel,
                "fallback_used": str(decision.fallback_used).lower(),
            },
        )
        handle = self._engine.load(
            decision.routine_id,
            knob_overrides=registered.knob_overrides,
        )
        return await self._engine.run(
            handle,
            principal=principal,
            capabilities=registered.capabilities,
            request_id=request_id,
        )
