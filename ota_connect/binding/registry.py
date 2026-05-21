"""AdapterRegistry — discovers adapter bundles and instantiates implementations.

The registry sits between `FilesystemIntegrationSource` (manifest discovery)
and the dispatch layer (which needs callable adapter instances). It caches one
implementation per adapter_id; instantiation is lazy.

The manifest's `entrypoint` field is a string of the form `module.path:attr`.
For mock / framework-bundled adapters, omit it and provide a callable factory
via `AdapterRegistry.register_factory(adapter_id, factory)` — used by tests
and by Phase 4 adapters during development.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from typing import Any

from ota_connect.binding.adapter_impl import AdapterImpl
from ota_connect.binding.errors import (
    AdapterLoadError,
    AdapterNotFoundError,
)
from ota_core.integration_source.errors import AdapterManifestNotFoundError
from ota_core.integration_source.source import AdapterBundle, IntegrationSource

AdapterFactory = Callable[[AdapterBundle], AdapterImpl]


@dataclass(frozen=True)
class LoadedAdapter:
    bundle: AdapterBundle
    impl: AdapterImpl

    @property
    def adapter_id(self) -> str:
        return self.bundle.adapter_id

    @property
    def integration_id(self) -> str:
        return self.bundle.integration_id


class AdapterRegistry:
    def __init__(self, source: IntegrationSource) -> None:
        self._source = source
        self._factories: dict[str, AdapterFactory] = {}
        self._cache: dict[str, LoadedAdapter] = {}
        self._lock = Lock()

    @property
    def source(self) -> IntegrationSource:
        return self._source

    def register_factory(self, adapter_id: str, factory: AdapterFactory) -> None:
        """Pre-register a callable factory for an adapter.

        Useful for in-process mock adapters that don't have an importable
        entrypoint. Tests use this to wire fixture adapters without setuptools
        entry points. Factories registered here take precedence over the
        manifest's `entrypoint` field.
        """
        with self._lock:
            self._factories[adapter_id] = factory
            self._cache.pop(adapter_id, None)

    def known_adapter_ids(self) -> list[str]:
        return self._source.list_ids()

    def get_bundle(self, adapter_id: str, *, capability: str, verb: str) -> AdapterBundle:
        try:
            return self._source.load(adapter_id)
        except AdapterManifestNotFoundError as e:
            raise AdapterNotFoundError(adapter_id, capability, verb) from e

    def load(self, adapter_id: str, *, capability: str, verb: str) -> LoadedAdapter:
        """Return a cached AdapterImpl for `adapter_id`, instantiating if needed."""
        with self._lock:
            cached = self._cache.get(adapter_id)
            if cached is not None:
                return cached
        bundle = self.get_bundle(adapter_id, capability=capability, verb=verb)
        impl = self._instantiate(bundle)
        loaded = LoadedAdapter(bundle=bundle, impl=impl)
        with self._lock:
            self._cache[adapter_id] = loaded
        return loaded

    def discover_all(self) -> list[AdapterBundle]:
        return self._source.discover_all()

    def _instantiate(self, bundle: AdapterBundle) -> AdapterImpl:
        factory = self._factories.get(bundle.adapter_id)
        if factory is not None:
            try:
                return factory(bundle)
            except BaseException as e:
                raise AdapterLoadError(bundle.adapter_id, f"<factory:{factory!r}>", e) from e
        entrypoint = bundle.manifest.entrypoint
        if not entrypoint:
            raise AdapterLoadError(
                bundle.adapter_id,
                "<missing>",
                ValueError("manifest has no `entrypoint` and no factory was registered"),
            )
        try:
            module_path, _, attr = entrypoint.partition(":")
            if not module_path or not attr:
                raise ValueError(f"entrypoint {entrypoint!r} must be 'module.path:attribute'")
            module = importlib.import_module(module_path)
            target = getattr(module, attr)
            impl: AdapterImpl = target(bundle) if callable(target) else target
        except BaseException as e:
            raise AdapterLoadError(bundle.adapter_id, entrypoint, e) from e
        return impl

    def adapters_satisfying(self, capability: str) -> list[AdapterBundle]:
        return [b for b in self.discover_all() if b.satisfies(capability)]

    def reset(self) -> None:
        """Clear the instance cache. Used by tests; not for production hot-reload."""
        with self._lock:
            self._cache.clear()


def find_adapter_for_capability(registry: AdapterRegistry, capability: str) -> AdapterBundle | None:
    candidates = registry.adapters_satisfying(capability)
    if len(candidates) == 1:
        return candidates[0]
    return None


__all__ = [
    "AdapterFactory",
    "AdapterRegistry",
    "LoadedAdapter",
    "find_adapter_for_capability",
]


# Avoid unused-name complaint for re-export grouping.
_ = Any
