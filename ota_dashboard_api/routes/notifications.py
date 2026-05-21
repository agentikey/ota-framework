"""Critical banner / notification surface.

The banner persists across restart per the architecture decision. v0.1 keeps
the active banner state on `DashboardState.critical_banner`; Phase 5 swaps
this for SQLite persistence so the banner survives process restart.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from ota_dashboard_api.app import DashboardState, dashboard_state
from ota_dashboard_api.models import CriticalBannerResponse

router = APIRouter()


class RaiseBannerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    severity: Literal["info", "warn", "error", "critical"]
    title: str
    description: str | None = None


@router.get("/notifications/banner", response_model=CriticalBannerResponse)
def get_banner(
    state: DashboardState = Depends(dashboard_state),
) -> CriticalBannerResponse:
    raw: dict[str, Any] | None = state.critical_banner
    if raw is None:
        return CriticalBannerResponse(active=False)
    return CriticalBannerResponse(
        active=True,
        severity=raw["severity"],
        title=raw["title"],
        description=raw.get("description"),
        raised_at=raw["raised_at"],
    )


@router.post("/notifications/banner", response_model=CriticalBannerResponse)
def raise_banner(
    request: RaiseBannerRequest,
    state: DashboardState = Depends(dashboard_state),
) -> CriticalBannerResponse:
    state.critical_banner = {
        "severity": request.severity,
        "title": request.title,
        "description": request.description,
        "raised_at": datetime.now(UTC),
    }
    return get_banner(state)


@router.delete("/notifications/banner", response_model=CriticalBannerResponse)
def clear_banner(
    state: DashboardState = Depends(dashboard_state),
) -> CriticalBannerResponse:
    state.critical_banner = None
    return CriticalBannerResponse(active=False)
