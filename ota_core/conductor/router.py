from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from ota_core.conductor.errors import NoRouteError

if TYPE_CHECKING:
    from ota_core.systems import Capability


@dataclass(frozen=True)
class Intent:
    text: str
    channel: str
    user_id: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RoutingDecision:
    routine_id: str
    confidence: float
    reason: str
    fallback_used: bool = False


@dataclass
class RegisteredRoutine:
    routine_id: str
    capabilities: dict[str, Capability] = field(default_factory=dict)
    knob_overrides: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class IntentRouter(Protocol):
    def route(self, intent: Intent) -> RoutingDecision: ...


class DirectRouter:
    """Direct routing — every intent goes to the single registered routine.

    v0.1 default. Replaced in v0.2 by SemanticRouter + LLM fallback once a
    second routine exists. The interface (Intent → RoutingDecision) does not
    change; only the routing strategy.
    """

    def __init__(self, routine_id: str) -> None:
        if not routine_id:
            raise ValueError("routine_id cannot be empty")
        self._routine_id = routine_id

    @property
    def routine_id(self) -> str:
        return self._routine_id

    def route(self, intent: Intent) -> RoutingDecision:
        return RoutingDecision(
            routine_id=self._routine_id,
            confidence=1.0,
            reason=f"direct routing to {self._routine_id} (v0.1 single-routine mode)",
            fallback_used=False,
        )


class RoutineNotFoundRouter:
    """A router that always raises NoRouteError. Useful for negative tests."""

    def route(self, intent: Intent) -> RoutingDecision:
        raise NoRouteError(f"{intent.channel}: {intent.text[:40]}")
