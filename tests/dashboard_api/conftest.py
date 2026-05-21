from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ota_core.audit import FileAuditReader, FileAuditSink, NullAuditSink
from ota_core.contracts.audit_event import DeploymentInfo, Principal, SourceInfo
from ota_core.policy.gates import GateManager, GateStore
from ota_core.storage.database import Database
from ota_dashboard_api.app import DashboardState, create_app
from ota_routines.email_triage.state import EmailTriageState


def _deployment() -> DeploymentInfo:
    return DeploymentInfo(id="d", mode="vps", edition="core", version="0.1.0")


def _source() -> SourceInfo:
    return SourceInfo(component="test", version="0.1.0")


def _principal() -> Principal:
    return Principal(id="op:test", type="operator", display_name="Test")


@pytest.fixture
def audit_dir(tmp_path: Path) -> Path:
    return tmp_path / "audit"


@pytest.fixture
def audit_sink(audit_dir: Path) -> FileAuditSink:
    return FileAuditSink(audit_dir, deployment=_deployment(), source=_source())


@pytest.fixture
def audit_reader(audit_dir: Path) -> FileAuditReader:
    audit_dir.mkdir(parents=True, exist_ok=True)
    return FileAuditReader(audit_dir)


@pytest.fixture
def gate_manager(tmp_path: Path) -> GateManager:
    db = Database(tmp_path / "gates.db")
    store = GateStore(db)
    return GateManager(
        store=store,
        audit_sink=NullAuditSink(deployment=_deployment(), source=_source()),
        principal=_principal(),
    )


@pytest.fixture
def triage_state(tmp_path: Path) -> EmailTriageState:
    db = Database(tmp_path / "triage.db")
    return EmailTriageState(db, trust_threshold=3)


@pytest.fixture
def dashboard(
    audit_reader: FileAuditReader,
    gate_manager: GateManager,
    triage_state: EmailTriageState,
) -> DashboardState:
    return DashboardState(
        audit_reader=audit_reader,
        gate_manager=gate_manager,
        triage_state=triage_state,
        routines_installed=("ota.email-triage", "ota.hello"),
    )


@pytest.fixture
def client(dashboard: DashboardState) -> TestClient:
    return TestClient(create_app(dashboard))
