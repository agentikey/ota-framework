from __future__ import annotations

import pytest

from ota_core.conductor import (
    DirectRouter,
    Intent,
    IntentRouter,
    NoRouteError,
)
from ota_core.conductor.router import RoutineNotFoundRouter


def test_direct_router_satisfies_protocol() -> None:
    router: IntentRouter = DirectRouter("ota.hello")
    assert isinstance(router, IntentRouter)


def test_direct_router_routes_to_single_routine() -> None:
    router = DirectRouter("ota.hello")
    decision = router.route(Intent(text="anything", channel="cli", user_id="u1"))
    assert decision.routine_id == "ota.hello"
    assert decision.confidence == 1.0
    assert not decision.fallback_used


def test_direct_router_requires_id() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        DirectRouter("")


def test_intent_dataclass_is_frozen() -> None:
    intent = Intent(text="hi", channel="cli", user_id="u")
    with pytest.raises(AttributeError):
        intent.text = "x"  # type: ignore[misc]


def test_routine_not_found_router_raises() -> None:
    router = RoutineNotFoundRouter()
    with pytest.raises(NoRouteError):
        router.route(Intent(text="hi", channel="cli", user_id="u"))
