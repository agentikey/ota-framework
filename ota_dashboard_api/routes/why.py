"""/why — render the routine's reasoning for a single email_id."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ota_dashboard_api.app import DashboardState, dashboard_state
from ota_dashboard_api.models import WhyEntryModel, WhyResponse
from ota_routines.email_triage.helpers import WhyLookup

router = APIRouter()


@router.get("/why/{email_id}", response_model=WhyResponse)
def why(
    email_id: str,
    state: DashboardState = Depends(dashboard_state),
) -> WhyResponse:
    if state.triage_state is None:
        raise HTTPException(503, "triage state not configured")
    lookup = WhyLookup(state.triage_state, state.audit_reader)
    entries = lookup.lookup(email_id)
    return WhyResponse(
        email_id=email_id,
        entries=[
            WhyEntryModel(
                timestamp=e.timestamp,
                kind=e.kind,
                description=e.description,
                payload=e.payload,
            )
            for e in entries
        ],
    )
