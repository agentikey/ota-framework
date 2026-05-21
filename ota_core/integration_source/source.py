from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import yaml
from pydantic import ValidationError

from ota_core.integration_source.errors import (
    AdapterDiscoveryError,
    AdapterManifestNotFoundError,
    DuplicateAdapterError,
)
from ota_core.integration_source.manifest import AdapterManifest

_MANIFEST_NAMES = ("manifest.yaml", "manifest.yml")


@dataclass(frozen=True)
class AdapterBundle:
    manifest: AdapterManifest
    directory: Path

    @property
    def adapter_id(self) -> str:
        return self.manifest.adapter_id

    @property
    def integration_id(self) -> str:
        return self.manifest.integration_id

    def satisfies(self, capability: str, version: str | None = None) -> bool:
        for claim in self.manifest.capabilities:
            if claim.capability == capability and (version is None or claim.version == version):
                return True
        return False


@runtime_checkable
class IntegrationSource(Protocol):
    def list_ids(self) -> list[str]: ...

    def load(self, adapter_id: str) -> AdapterBundle: ...

    def discover_all(self) -> list[AdapterBundle]: ...


class FilesystemIntegrationSource:
    def __init__(self, roots: Iterable[Path | str]) -> None:
        self._roots = [Path(r).expanduser() for r in roots]

    @property
    def roots(self) -> list[Path]:
        return list(self._roots)

    def _candidate_dirs(self) -> list[Path]:
        out: list[Path] = []
        for root in self._roots:
            if not root.exists():
                continue
            for child in sorted(root.iterdir()):
                if child.is_dir() and not child.name.startswith("_"):
                    out.append(child)
        return out

    def list_ids(self) -> list[str]:
        ids: list[str] = []
        for d in self._candidate_dirs():
            try:
                manifest = _read_manifest(d)
            except (AdapterManifestNotFoundError, AdapterDiscoveryError):
                continue
            ids.append(manifest.adapter_id)
        return ids

    def discover_all(self) -> list[AdapterBundle]:
        bundles: list[AdapterBundle] = []
        seen: dict[str, list[str]] = {}
        for d in self._candidate_dirs():
            try:
                manifest = _read_manifest(d)
            except AdapterManifestNotFoundError:
                continue
            bundle = AdapterBundle(manifest=manifest, directory=d)
            seen.setdefault(bundle.adapter_id, []).append(str(d))
            bundles.append(bundle)
        for adapter_id, paths in seen.items():
            if len(paths) > 1:
                raise DuplicateAdapterError(adapter_id, paths)
        return bundles

    def load(self, adapter_id: str) -> AdapterBundle:
        candidates: list[AdapterBundle] = []
        for d in self._candidate_dirs():
            try:
                manifest = _read_manifest(d)
            except AdapterManifestNotFoundError:
                continue
            if manifest.adapter_id == adapter_id:
                candidates.append(AdapterBundle(manifest=manifest, directory=d))
        if not candidates:
            raise AdapterManifestNotFoundError(
                f"adapter {adapter_id!r} not found under {[str(r) for r in self._roots]}"
            )
        if len(candidates) > 1:
            raise DuplicateAdapterError(adapter_id, [str(b.directory) for b in candidates])
        return candidates[0]

    def by_capability(self, capability: str, version: str | None = None) -> list[AdapterBundle]:
        return [b for b in self.discover_all() if b.satisfies(capability, version)]


def _read_manifest(directory: Path) -> AdapterManifest:
    for name in _MANIFEST_NAMES:
        candidate = directory / name
        if not candidate.exists():
            continue
        with candidate.open("r", encoding="utf-8") as f:
            data: Any = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise AdapterDiscoveryError(
                f"adapter manifest at {candidate} must be a YAML mapping, got {type(data)!r}"
            )
        try:
            return AdapterManifest.model_validate(data)
        except ValidationError as e:
            raise AdapterDiscoveryError(f"invalid adapter manifest at {candidate}: {e}") from e
    raise AdapterManifestNotFoundError(
        f"no manifest ({' | '.join(_MANIFEST_NAMES)}) under {directory}"
    )
