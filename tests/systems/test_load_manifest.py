from __future__ import annotations

from pathlib import Path

import pytest

from ota_core.routine_source import FilesystemRoutineSource, ManifestNotFoundError
from ota_core.systems import LoadManifestResolver
from tests.routine_source.conftest import make_routine_dir


def test_resolve_basic(tmp_path: Path) -> None:
    make_routine_dir(tmp_path, routine_id="ota.hello")
    resolver = LoadManifestResolver(routine_source=FilesystemRoutineSource(tmp_path))
    manifest = resolver.resolve("ota.hello")
    assert manifest.routine_id == "ota.hello"
    assert manifest.integration_ids == ()
    assert manifest.state_shards == ()


def test_resolve_includes_integrations(tmp_path: Path) -> None:
    make_routine_dir(
        tmp_path,
        routine_id="ota.email",
        manifest_overrides={
            "dependencies": {
                "routines": [],
                "integrations": [
                    {
                        "id": "gmail",
                        "scopes": ["email:read", "email:send"],
                        "optional": False,
                        "binding_level": "routine_exclusive",
                        "on_emergency_kill": "burn_credential",
                    },
                ],
            },
        },
    )
    resolver = LoadManifestResolver(routine_source=FilesystemRoutineSource(tmp_path))
    manifest = resolver.resolve("ota.email")
    assert manifest.integration_ids == ("gmail",)


def test_resolve_includes_state_shards(tmp_path: Path) -> None:
    make_routine_dir(
        tmp_path,
        routine_id="ota.triage",
        manifest_overrides={
            "state": {
                "shards": [
                    {"name": "triage_state", "schema_url": "schemas/triage_state.json"},
                ],
            },
        },
    )
    resolver = LoadManifestResolver(routine_source=FilesystemRoutineSource(tmp_path))
    manifest = resolver.resolve("ota.triage")
    assert manifest.state_shards == ("triage_state",)


def test_resolve_unknown_raises(tmp_path: Path) -> None:
    resolver = LoadManifestResolver(routine_source=FilesystemRoutineSource(tmp_path))
    with pytest.raises(ManifestNotFoundError):
        resolver.resolve("ghost.routine")
