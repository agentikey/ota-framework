"""Fleet — v0.1 placeholder showing the single local install."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ota_dashboard_api.app import DashboardState, dashboard_state
from ota_dashboard_api.models import FleetEntry, FleetResponse

router = APIRouter()


@router.get("/fleet", response_model=FleetResponse)
def fleet(state: DashboardState = Depends(dashboard_state)) -> FleetResponse:
    return FleetResponse(
        entries=[
            FleetEntry(
                deployment_id=state.deployment_id,
                edition=state.edition,
                framework_version=state.framework_version,
                routines=list(state.routines_installed),
            )
        ]
    )
