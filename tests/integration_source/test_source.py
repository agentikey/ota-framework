from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from ota_core.integration_source import (
    AdapterBundle,
    AdapterDiscoveryError,
    AdapterManifestNotFoundError,
    DuplicateAdapterError,
    FilesystemIntegrationSource,
    IntegrationSource,
)


def _write_adapter(
    root: Path,
    adapter_id: str,
    *,
    integration_id: str | None = None,
    capabilities: list[dict[str, str]] | None = None,
    version: str = "0.1.0",
    schema_version: str = "1.0.0",
    extra: dict[str, Any] | None = None,
) -> Path:
    d = root / adapter_id
    d.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "schema_version": schema_version,
        "adapter_id": adapter_id,
        "integration_id": integration_id or adapter_id.split("_")[0],
        "version": version,
        "framework_compat": ">=0.1.0",
        "capabilities": capabilities or [{"capability": "messaging", "version": "1.0.0"}],
        "auth_styles": ["oauth2"],
    }
    if extra:
        manifest.update(extra)
    (d / "manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return d


def test_protocol_satisfaction(tmp_path: Path) -> None:
    src: IntegrationSource = FilesystemIntegrationSource([tmp_path])
    assert isinstance(src, IntegrationSource)


def test_empty_root_returns_nothing(tmp_path: Path) -> None:
    src = FilesystemIntegrationSource([tmp_path])
    assert src.list_ids() == []
    assert src.discover_all() == []


def test_missing_root_returns_nothing(tmp_path: Path) -> None:
    src = FilesystemIntegrationSource([tmp_path / "nonexistent"])
    assert src.list_ids() == []


def test_discover_adapter(tmp_path: Path) -> None:
    _write_adapter(tmp_path, "slack_socket", integration_id="slack")
    src = FilesystemIntegrationSource([tmp_path])
    bundles = src.discover_all()
    assert len(bundles) == 1
    assert bundles[0].adapter_id == "slack_socket"
    assert bundles[0].integration_id == "slack"


def test_load_specific_adapter(tmp_path: Path) -> None:
    _write_adapter(tmp_path, "slack_socket")
    _write_adapter(
        tmp_path,
        "gmail_oauth",
        integration_id="gmail",
        capabilities=[{"capability": "email", "version": "1.0.0"}],
    )
    src = FilesystemIntegrationSource([tmp_path])
    gmail = src.load("gmail_oauth")
    assert gmail.integration_id == "gmail"
    assert gmail.satisfies("email")


def test_load_unknown_raises(tmp_path: Path) -> None:
    src = FilesystemIntegrationSource([tmp_path])
    with pytest.raises(AdapterManifestNotFoundError):
        src.load("ghost")


def test_directory_without_manifest_skipped(tmp_path: Path) -> None:
    (tmp_path / "not_an_adapter").mkdir()
    src = FilesystemIntegrationSource([tmp_path])
    assert src.list_ids() == []


def test_underscore_prefixed_dirs_skipped(tmp_path: Path) -> None:
    _write_adapter(tmp_path, "_internal", integration_id="internal")
    _write_adapter(tmp_path, "slack_socket")
    src = FilesystemIntegrationSource([tmp_path])
    assert src.list_ids() == ["slack_socket"]


def test_invalid_manifest_raises(tmp_path: Path) -> None:
    d = tmp_path / "broken"
    d.mkdir()
    (d / "manifest.yaml").write_text("- not a mapping\n", encoding="utf-8")
    src = FilesystemIntegrationSource([tmp_path])
    with pytest.raises(AdapterDiscoveryError, match="must be a YAML mapping"):
        src.discover_all()


def test_validation_error_surfaced(tmp_path: Path) -> None:
    d = tmp_path / "bad"
    d.mkdir()
    (d / "manifest.yaml").write_text('schema_version: "1.0.0"\nadapter_id: x\n', encoding="utf-8")
    src = FilesystemIntegrationSource([tmp_path])
    with pytest.raises(AdapterDiscoveryError, match="invalid adapter manifest"):
        src.discover_all()


def test_duplicate_adapter_id_detected(tmp_path: Path) -> None:
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    _write_adapter(root_a, "slack_socket")
    _write_adapter(root_b, "slack_socket")
    src = FilesystemIntegrationSource([root_a, root_b])
    with pytest.raises(DuplicateAdapterError, match="slack_socket"):
        src.discover_all()


def test_multiple_roots_discover_combined(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    _write_adapter(a, "slack_socket")
    _write_adapter(
        b,
        "gmail_oauth",
        integration_id="gmail",
        capabilities=[{"capability": "email", "version": "1.0.0"}],
    )
    src = FilesystemIntegrationSource([a, b])
    assert set(src.list_ids()) == {"slack_socket", "gmail_oauth"}


def test_by_capability_filter(tmp_path: Path) -> None:
    _write_adapter(tmp_path, "slack_socket")
    _write_adapter(
        tmp_path,
        "gmail_oauth",
        integration_id="gmail",
        capabilities=[{"capability": "email", "version": "1.0.0"}],
    )
    src = FilesystemIntegrationSource([tmp_path])
    email_adapters = src.by_capability("email")
    assert {b.adapter_id for b in email_adapters} == {"gmail_oauth"}


def test_by_capability_version_filter(tmp_path: Path) -> None:
    _write_adapter(
        tmp_path, "v1_adapter", capabilities=[{"capability": "messaging", "version": "1.0.0"}]
    )
    _write_adapter(
        tmp_path, "v2_adapter", capabilities=[{"capability": "messaging", "version": "2.0.0"}]
    )
    src = FilesystemIntegrationSource([tmp_path])
    v2 = src.by_capability("messaging", "2.0.0")
    assert {b.adapter_id for b in v2} == {"v2_adapter"}


def test_satisfies_method() -> None:
    from ota_core.integration_source.manifest import AdapterCapabilityClaim, AdapterManifest

    manifest = AdapterManifest(
        schema_version="1.0.0",
        adapter_id="x",
        integration_id="i",
        version="0.1.0",
        framework_compat=">=0.1.0",
        capabilities=[AdapterCapabilityClaim(capability="messaging", version="1.0.0")],
    )
    bundle = AdapterBundle(manifest=manifest, directory=Path("/"))
    assert bundle.satisfies("messaging")
    assert bundle.satisfies("messaging", "1.0.0")
    assert not bundle.satisfies("messaging", "2.0.0")
    assert not bundle.satisfies("email")
