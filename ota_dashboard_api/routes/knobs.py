"""Routine knob editor — list current values, post updates.

v0.1 keeps an in-memory dict on `DashboardState`; Phase 5 wires this to the
real routine engine knob store.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ota_dashboard_api.app import DashboardState, dashboard_state
from ota_dashboard_api.models import (
    KnobsUpdateRequest,
    KnobsUpdateResponse,
    KnobValue,
    RoutineKnobsResponse,
)

router = APIRouter()


def _knobs_store(state: DashboardState) -> dict[str, dict[str, Any]]:
    store: dict[str, dict[str, Any]] | None = getattr(state, "knobs_by_routine", None)
    if store is None:
        store = {}
        state.knobs_by_routine = store  # type: ignore[attr-defined]
    return store


@router.get("/routines/{routine_id}/knobs", response_model=RoutineKnobsResponse)
def get_knobs(
    routine_id: str,
    state: DashboardState = Depends(dashboard_state),
) -> RoutineKnobsResponse:
    if routine_id not in state.routines_installed:
        raise HTTPException(404, f"routine {routine_id!r} not installed")
    knobs = _knobs_store(state).get(routine_id, {})
    return RoutineKnobsResponse(
        routine_id=routine_id,
        knobs=[
            KnobValue(name=name, type="string", value=value, default=value, description="")
            for name, value in knobs.items()
        ],
    )


@router.post("/routines/{routine_id}/knobs", response_model=KnobsUpdateResponse)
def update_knobs(
    routine_id: str,
    request: KnobsUpdateRequest,
    state: DashboardState = Depends(dashboard_state),
) -> KnobsUpdateResponse:
    if routine_id not in state.routines_installed:
        raise HTTPException(404, f"routine {routine_id!r} not installed")
    store = _knobs_store(state)
    routine_knobs = store.setdefault(routine_id, {})
    routine_knobs.update(request.knobs)
    return KnobsUpdateResponse(routine_id=routine_id, applied=dict(request.knobs))
