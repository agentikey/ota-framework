"""FastAPI app factory + dependency wiring.

The factory takes concrete implementations of the seams the dashboard reads:
`AuditReader`, `GateManager`, `EmailTriageState`. Phase 5 (deployment) wires
real instances. Tests construct in-memory implementations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request

from ota_core.audit.reader import AuditReader
from ota_core.policy.gates import GateManager
from ota_routines.email_triage.state import EmailTriageState


@dataclass
class DashboardState:
    """Container for the seams the dashboard touches."""

    audit_reader: AuditReader
    gate_manager: GateManager | None = None
    triage_state: EmailTriageState | None = None
    framework_version: str = "0.1.0"
    deployment_id: str = "local"
    edition: str = "core"
    routines_installed: tuple[str, ...] = ()
    critical_banner: dict[str, Any] | None = None


def dashboard_state(request: Request) -> DashboardState:
    """FastAPI dependency that returns the app's DashboardState."""
    return request.app.state.dashboard  # type: ignore[no-any-return]


def create_app(state: DashboardState) -> FastAPI:
    from ota_dashboard_api.routes import (
        approval_queue,
        audit,
        fleet,
        knobs,
        notifications,
        why,
    )

    app = FastAPI(
        title="OTA Dashboard API",
        version="0.1.0",
        description=(
            "Operator dashboard for the OTA framework. Read-only audit, "
            "approval queue, /why drill-down, routine knob editor."
        ),
    )
    app.state.dashboard = state
    app.include_router(approval_queue.router, prefix="/api/v1", tags=["approvals"])
    app.include_router(audit.router, prefix="/api/v1", tags=["audit"])
    app.include_router(why.router, prefix="/api/v1", tags=["why"])
    app.include_router(knobs.router, prefix="/api/v1", tags=["knobs"])
    app.include_router(fleet.router, prefix="/api/v1", tags=["fleet"])
    app.include_router(notifications.router, prefix="/api/v1", tags=["notifications"])

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "version": state.framework_version}

    return app
