from __future__ import annotations

from pathlib import Path

from ota_core.audit import NullAuditSink
from ota_core.branches import BranchRegistry
from ota_core.conductor import Conductor, DirectRouter, Intent
from ota_core.contracts.audit_event import DeploymentInfo, Principal, SourceInfo
from ota_core.identity import InMemoryIdentityProvider
from ota_core.observability import NullObservabilitySink
from ota_core.policy import L0bEnforcer
from ota_core.routine_source import FilesystemRoutineSource
from ota_core.secrets import InMemorySecretsProvider
from ota_core.systems import (
    Capability,
    LoadManifestResolver,
    RoutineEngine,
    System,
)
from tests.routine_source.conftest import make_routine_dir


def _principal() -> Principal:
    return Principal(id="op:test", type="operator", display_name="Test")


def _build_system(tmp_path: Path) -> tuple[System, NullAuditSink, NullObservabilitySink]:
    audit = NullAuditSink(
        deployment=DeploymentInfo(id="d", mode="vps", edition="core", version="0.1.0"),
        source=SourceInfo(component="system", version="0.1.0"),
    )
    obs = NullObservabilitySink()
    source = FilesystemRoutineSource(tmp_path)
    engine = RoutineEngine(
        routine_source=source,
        identity_provider=InMemoryIdentityProvider([]),
        secrets_provider=InMemorySecretsProvider(),
        audit_sink=audit,
        observability=obs,
        l0b=L0bEnforcer(audit_sink=audit, observability=obs),
    )
    conductor = Conductor(
        router=DirectRouter("ota.hello"),
        engine=engine,
        audit_sink=audit,
        observability=obs,
    )
    branches = BranchRegistry.default(routines=["ota.hello"])
    system = System(
        conductor=conductor,
        branches=branches,
        engine=engine,
        load_manifest_resolver=LoadManifestResolver(routine_source=source),
    )
    return system, audit, obs


def _write_routine(tmp_path: Path) -> None:
    helpers = "async def run(runtime):\n    runtime.call('echo', 'hi')\n    return 'ok'\n"
    make_routine_dir(
        tmp_path,
        routine_id="ota.hello",
        extra_files={"helpers.py": helpers},
    )


async def test_system_dispatches_intent(tmp_path: Path) -> None:
    _write_routine(tmp_path)
    system, _, _ = _build_system(tmp_path)
    system.conductor.register_routine(
        "ota.hello",
        capabilities={"echo": Capability("echo", lambda x: x)},
    )
    result = await system.dispatch(
        Intent(text="hi", channel="cli", user_id="op"),
        principal=_principal(),
    )
    assert result.routine_id == "ota.hello"
    assert result.return_value == "ok"


def test_system_branch_for_routine(tmp_path: Path) -> None:
    _write_routine(tmp_path)
    system, _, _ = _build_system(tmp_path)
    assert system.branch_for("ota.hello") == "productivity"
    assert system.branch_for("ota.unknown") is None


def test_system_load_manifest_resolves(tmp_path: Path) -> None:
    _write_routine(tmp_path)
    system, _, _ = _build_system(tmp_path)
    manifest = system.load_manifest_resolver.resolve("ota.hello")
    assert manifest.routine_id == "ota.hello"
