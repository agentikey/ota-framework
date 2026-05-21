from __future__ import annotations

from pathlib import Path

import pytest

from ota_connect.binding import (
    AdapterLoadError,
    AdapterNotFoundError,
    AdapterRegistry,
)
from ota_core.integration_source.source import FilesystemIntegrationSource


def test_load_mock_messaging_adapter(adapter_registry: AdapterRegistry) -> None:
    loaded = adapter_registry.load("mock_messaging", capability="messaging", verb="send_message")
    assert loaded.adapter_id == "mock_messaging"
    assert loaded.integration_id == "mock.messaging"
    assert callable(getattr(loaded.impl, "invoke", None))


def test_load_caches_instance(adapter_registry: AdapterRegistry) -> None:
    first = adapter_registry.load("mock_messaging", capability="messaging", verb="send_message")
    second = adapter_registry.load("mock_messaging", capability="messaging", verb="send_message")
    assert first.impl is second.impl


def test_unknown_adapter_raises(adapter_registry: AdapterRegistry) -> None:
    with pytest.raises(AdapterNotFoundError):
        adapter_registry.load("does_not_exist", capability="messaging", verb="send_message")


def test_registered_factory_wins_over_entrypoint(
    adapter_registry: AdapterRegistry,
) -> None:
    sentinel = object()

    def factory(_bundle: object) -> object:
        class Stub:
            def invoke(self, capability: str, verb: str, /, **kwargs: object) -> object:
                return sentinel

        return Stub()

    adapter_registry.register_factory("mock_messaging", factory)  # type: ignore[arg-type]
    loaded = adapter_registry.load("mock_messaging", capability="messaging", verb="send_message")
    assert loaded.impl.invoke("messaging", "send_message") is sentinel


def test_entrypoint_failure_raises_adapter_load_error(tmp_path: Path) -> None:
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "manifest.yaml").write_text(
        "schema_version: 0.1.0\n"
        "adapter_id: broken\n"
        "integration_id: broken\n"
        "version: 0.1.0\n"
        "framework_compat: '>=0.1.0'\n"
        "capabilities:\n"
        "  - capability: messaging\n"
        "    version: 0.1.0\n"
        "entrypoint: nonexistent.module:missing\n",
        encoding="utf-8",
    )
    reg = AdapterRegistry(FilesystemIntegrationSource([tmp_path]))
    with pytest.raises(AdapterLoadError):
        reg.load("broken", capability="messaging", verb="send_message")
