"""OTA operator dashboard backend (FastAPI).

`create_app()` returns a fully wired `FastAPI` instance. Dependencies (audit
reader, gate manager, triage state) are bound at app-creation time so tests
can inject lightweight in-memory implementations.
"""

from ota_dashboard_api.app import DashboardState, create_app, dashboard_state

__all__ = ["DashboardState", "create_app", "dashboard_state"]
