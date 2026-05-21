from __future__ import annotations

from pathlib import Path

import pytest

from ota_core.audit import NullAuditSink
from ota_core.conductor import (
    Conductor,
    DirectRouter,
    Intent,
    RoutineNotRegisteredError,
)
from ota_core.contracts.audit_event import DeploymentInfo, Principal, SourceInfo
from ota_core.identity import InMemoryIdentityProvider
from ota_core.observability import NullObservabilitySink
from ota_core.policy import L0bEnforcer
from ota_core.routine_source import FilesystemRoutineSource
from ota_core.secrets import InMemorySecretsProvider
from ota_core.systems import Capability, RoutineEngine
from tests.routine_source.conftest import make_routine_dir


def _principal() -> Principal:
    return Principal(id="op:test", type="operator", display_name="Test")


def _build(tmp_path: Path) -> Conductor:
    audit = NullAuditSink(
        deployment=DeploymentInfo(id="d", mode="vps", edition="core", version="0.1.0"),
        source=SourceInfo(component="conductor", version="0.1.0"),
    )
    obs = NullObservabilitySink()
    engine = RoutineEngine(
        routine_source=FilesystemRoutineSource(tmp_path),
        identity_provider=InMemoryIdentityProvider([]),
        secrets_provider=InMemorySecretsProvider(),
        audit_sink=audit,
        observability=obs,
        l0b=L0bEnforcer(audit_sink=audit, observability=obs),
    )
    return Conductor(
        router=DirectRouter("ota.hello"),
        engine=engine,
        audit_sink=audit,
        observability=obs,
    )


def _write_routine(tmp_path: Path) -> None:
    make_routine_dir(
        tmp_path,
        routine_id="ota.hello",
        extra_files={
            "helpers.py": (
                "async def run(runtime):\n"
                "    return runtime.call('echo', runtime.context.routine_run_id)\n"
            ),
        },
    )


async def test_dispatch_routes_to_registered_routine(tmp_path: Path) -> None:
    _write_routine(tmp_path)
    conductor = _build(tmp_path)
    conductor.register_routine(
        "ota.hello",
        capabilities={"echo": Capability("echo", lambda x: x)},
    )
    intent = Intent(text="say hi", channel="cli", user_id="op")
    result = await conductor.dispatch(intent, principal=_principal())
    assert result.routine_id == "ota.hello"
    assert result.return_value == result.routine_run_id


async def test_dispatch_unregistered_routine_raises(tmp_path: Path) -> None:
    _write_routine(tmp_path)
    conductor = _build(tmp_path)
    with pytest.raises(RoutineNotRegisteredError):
        await conductor.dispatch(
            Intent(text="x", channel="cli", user_id="op"),
            principal=_principal(),
        )


def test_decide_returns_routing_decision(tmp_path: Path) -> None:
    _write_routine(tmp_path)
    conductor = _build(tmp_path)
    decision = conductor.decide(Intent(text="x", channel="cli", user_id="op"))
    assert decision.routine_id == "ota.hello"


def test_registered_list(tmp_path: Path) -> None:
    _write_routine(tmp_path)
    conductor = _build(tmp_path)
    conductor.register_routine("ota.hello")
    assert conductor.registered() == ["ota.hello"]
    conductor.deregister_routine("ota.hello")
    assert conductor.registered() == []


async def test_observability_metric_emitted(tmp_path: Path) -> None:
    _write_routine(tmp_path)
    audit = NullAuditSink(
        deployment=DeploymentInfo(id="d", mode="vps", edition="core", version="0.1.0"),
        source=SourceInfo(component="conductor", version="0.1.0"),
    )
    obs = NullObservabilitySink()
    engine = RoutineEngine(
        routine_source=FilesystemRoutineSource(tmp_path),
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
    conductor.register_routine(
        "ota.hello",
        capabilities={"echo": Capability("echo", lambda x: x)},
    )
    await conductor.dispatch(
        Intent(text="hi", channel="cli", user_id="op"),
        principal=_principal(),
    )
    metrics = [
        r for r in obs.records if r["kind"] == "metric" and r["name"] == "conductor.route_decided"
    ]
    assert metrics
