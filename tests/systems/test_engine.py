from __future__ import annotations

from pathlib import Path

import pytest

from ota_core.audit import NullAuditSink
from ota_core.contracts.audit_event import DeploymentInfo, Principal, SourceInfo
from ota_core.identity import InMemoryIdentityProvider
from ota_core.observability import NullObservabilitySink
from ota_core.policy import L0bEnforcer
from ota_core.routine_source import FilesystemRoutineSource
from ota_core.secrets import InMemorySecretsProvider
from ota_core.systems import (
    Capability,
    KnobResolutionError,
    RoutineEngine,
    RoutineRunError,
    resolve_knobs,
)
from tests.routine_source.conftest import make_routine_dir


def _principal() -> Principal:
    return Principal(id="op:test", type="operator", display_name="Test")


def _build_engine(tmp_path: Path) -> tuple[RoutineEngine, NullAuditSink, NullObservabilitySink]:
    audit = NullAuditSink(
        deployment=DeploymentInfo(id="d", mode="vps", edition="core", version="0.1.0"),
        source=SourceInfo(component="engine", version="0.1.0"),
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
    return engine, audit, obs


def _write_hello_routine(tmp_path: Path, *, helpers: str | None = None) -> Path:
    helpers = (
        helpers
        or """
async def run(runtime):
    runtime.call("say_hello", "world")
    return {"ok": True}
"""
    )
    return make_routine_dir(
        tmp_path,
        routine_id="ota.hello",
        extra_files={"helpers.py": helpers},
    )


async def test_load_returns_handle(tmp_path: Path) -> None:
    _write_hello_routine(tmp_path)
    engine, _, _ = _build_engine(tmp_path)
    handle = engine.load("ota.hello")
    assert handle.bundle.id == "ota.hello"
    assert handle.helpers is not None
    assert handle.main_callable() is not None


async def test_load_without_helpers_returns_handle(tmp_path: Path) -> None:
    make_routine_dir(tmp_path, routine_id="ota.hello")
    engine, _, _ = _build_engine(tmp_path)
    handle = engine.load("ota.hello")
    assert handle.helpers is None
    assert handle.main_callable() is None


async def test_run_invokes_helpers_run_and_returns_value(tmp_path: Path) -> None:
    _write_hello_routine(tmp_path)
    engine, audit, _ = _build_engine(tmp_path)
    handle = engine.load("ota.hello")

    invoked: list[str] = []

    def say_hello(target: str) -> None:
        invoked.append(target)

    capabilities = {"say_hello": Capability("say_hello", say_hello)}
    result = await engine.run(handle, principal=_principal(), capabilities=capabilities)
    assert invoked == ["world"]
    assert result.return_value == {"ok": True}
    assert result.routine_id == "ota.hello"
    # Audit trace recorded run_started + run_completed
    events = [e.event_type for e in audit.events]
    assert "routine.run_started" in events
    assert "routine.run_completed" in events


async def test_run_without_helpers_raises(tmp_path: Path) -> None:
    make_routine_dir(tmp_path, routine_id="ota.hello")
    engine, _, _ = _build_engine(tmp_path)
    handle = engine.load("ota.hello")
    with pytest.raises(RoutineRunError, match=r"no helpers\.py"):
        await engine.run(handle, principal=_principal())


async def test_run_propagates_helpers_exception_and_records_failure(tmp_path: Path) -> None:
    _write_hello_routine(
        tmp_path,
        helpers="async def run(runtime):\n    raise RuntimeError('boom')\n",
    )
    engine, audit, _ = _build_engine(tmp_path)
    handle = engine.load("ota.hello")
    with pytest.raises(RuntimeError, match="boom"):
        await engine.run(handle, principal=_principal())
    events = [e.event_type for e in audit.events]
    assert "routine.run_failed" in events


async def test_run_supports_sync_run_function(tmp_path: Path) -> None:
    _write_hello_routine(tmp_path, helpers="def run(runtime):\n    return 42\n")
    engine, _, _ = _build_engine(tmp_path)
    handle = engine.load("ota.hello")
    result = await engine.run(handle, principal=_principal())
    assert result.return_value == 42


async def test_runtime_call_unknown_capability_raises(tmp_path: Path) -> None:
    _write_hello_routine(
        tmp_path,
        helpers='async def run(runtime):\n    runtime.call("ghost")\n',
    )
    engine, _, _ = _build_engine(tmp_path)
    handle = engine.load("ota.hello")
    with pytest.raises(KeyError, match="ghost"):
        await engine.run(handle, principal=_principal())


def test_resolve_knobs_default_values(tmp_path: Path) -> None:

    make_routine_dir(
        tmp_path,
        routine_id="ota.x",
        manifest_overrides={
            "knobs": [
                {"name": "enabled", "type": "bool", "default": True, "description": ""},
                {
                    "name": "level",
                    "type": "enum",
                    "values": ["low", "med", "high"],
                    "default": "low",
                    "description": "",
                },
            ]
        },
    )
    engine, _, _ = _build_engine(tmp_path)
    handle = engine.load("ota.x")
    assert handle.knobs == {"enabled": True, "level": "low"}


def test_resolve_knobs_with_overrides(tmp_path: Path) -> None:
    make_routine_dir(
        tmp_path,
        routine_id="ota.x",
        manifest_overrides={
            "knobs": [
                {"name": "enabled", "type": "bool", "default": True},
                {"name": "count", "type": "int", "default": 5, "min": 1, "max": 10},
            ]
        },
    )
    engine, _, _ = _build_engine(tmp_path)
    handle = engine.load("ota.x", knob_overrides={"count": 7})
    assert handle.knobs == {"enabled": True, "count": 7}


def test_resolve_knobs_rejects_unknown_override(tmp_path: Path) -> None:
    make_routine_dir(tmp_path, routine_id="ota.x")
    engine, _, _ = _build_engine(tmp_path)
    with pytest.raises(KnobResolutionError, match="unknown knob"):
        engine.load("ota.x", knob_overrides={"ghost": True})


def test_resolve_knobs_int_out_of_range(tmp_path: Path) -> None:
    make_routine_dir(
        tmp_path,
        routine_id="ota.x",
        manifest_overrides={
            "knobs": [{"name": "n", "type": "int", "default": 1, "min": 0, "max": 5}],
        },
    )
    engine, _, _ = _build_engine(tmp_path)
    with pytest.raises(KnobResolutionError, match="> max"):
        engine.load("ota.x", knob_overrides={"n": 99})


async def test_run_emits_observability_span(tmp_path: Path) -> None:
    _write_hello_routine(tmp_path)
    engine, _, obs = _build_engine(tmp_path)
    handle = engine.load("ota.hello")
    capabilities = {"say_hello": Capability("say_hello", lambda x: None)}
    await engine.run(handle, principal=_principal(), capabilities=capabilities)
    spans = [r for r in obs.records if r["kind"] == "span" and r["name"] == "routine.run"]
    assert len(spans) == 1


def test_resolve_knobs_secret_ref_requires_override() -> None:
    from ota_core.contracts.routine_source import RoutineBundleManifest

    with pytest.raises(KnobResolutionError, match="no default"):
        # Build minimal manifest shell — easier to call the function directly
        # via the route's resolve_knobs path

        manifest_dict = {
            "schema_version": "1.0.0",
            "id": "ota.x",
            "version": "0.1.0",
            "framework_compat": ">=0.1.0",
            "metadata": {
                "name": "X",
                "description": "",
                "author": "x",
                "author_url": "https://x",
                "category": "x",
                "tags": [],
            },
            "dependencies": {"routines": [], "integrations": []},
            "capabilities": {"provides": [], "consumes": []},
            "llm_requirements": {
                "schema_version": "1.0.0",
                "required": [],
                "preferred": [],
                "pii_categories": ["none"],
            },
            "knobs": [{"name": "api_key", "type": "secret_ref"}],
            "automation": {"cadence": [], "events": []},
            "gates": [],
            "state": {"shards": []},
            "artifacts": {"stale_artifact_ttl": "4h"},
            "files": [{"path": "x.md", "role": "asset", "sha256": "a" * 64}],
            "signature": {
                "algorithm": "ed25519",
                "key_id": "k",
                "value": "v",
                "signed_fields": ["id"],
            },
        }
        manifest = RoutineBundleManifest.model_validate(manifest_dict)
        resolve_knobs(manifest)
