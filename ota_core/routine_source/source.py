from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import yaml
from pydantic import ValidationError

from ota_core.contracts.routine_source import RoutineBundleManifest
from ota_core.routine_source.errors import (
    DuplicateRoutineError,
    FileIntegrityError,
    ManifestNotFoundError,
    RoutineBundleError,
)
from ota_core.storage.markdown import read_markdown


@dataclass(frozen=True)
class RoutineBundle:
    manifest: RoutineBundleManifest
    directory: Path
    body: str

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def version(self) -> str:
        return self.manifest.version

    def file_path(self, relative: str) -> Path:
        return self.directory / relative


@runtime_checkable
class RoutineSource(Protocol):
    def list_ids(self) -> list[str]: ...

    def load(self, routine_id: str) -> RoutineBundle: ...

    def discover_all(self) -> list[RoutineBundle]: ...


_MANIFEST_NAMES = ("routine.md", "routine.yaml", "routine.yml")


class FilesystemRoutineSource:
    def __init__(
        self,
        root: Path | str,
        *,
        verify_files: bool = True,
    ) -> None:
        self._root = Path(root).expanduser()
        self._verify_files = verify_files

    @property
    def root(self) -> Path:
        return self._root

    def _candidate_dirs(self) -> list[Path]:
        if not self._root.exists():
            return []
        return [p for p in sorted(self._root.iterdir()) if p.is_dir()]

    def list_ids(self) -> list[str]:
        ids: list[str] = []
        for d in self._candidate_dirs():
            try:
                manifest = self._read_manifest(d)
            except (ManifestNotFoundError, RoutineBundleError):
                continue
            ids.append(manifest.id)
        return ids

    def discover_all(self) -> list[RoutineBundle]:
        bundles: list[RoutineBundle] = []
        seen: dict[str, list[str]] = {}
        for d in self._candidate_dirs():
            try:
                bundle = self._load_dir(d)
            except ManifestNotFoundError:
                continue
            seen.setdefault(bundle.id, []).append(str(d))
            bundles.append(bundle)
        for routine_id, paths in seen.items():
            if len(paths) > 1:
                raise DuplicateRoutineError(routine_id, paths)
        return bundles

    def load(self, routine_id: str) -> RoutineBundle:
        candidates: list[RoutineBundle] = []
        for d in self._candidate_dirs():
            try:
                bundle = self._load_dir(d)
            except ManifestNotFoundError:
                continue
            if bundle.id == routine_id:
                candidates.append(bundle)
        if not candidates:
            raise ManifestNotFoundError(f"routine {routine_id!r} not found under {self._root}")
        if len(candidates) > 1:
            raise DuplicateRoutineError(routine_id, [str(b.directory) for b in candidates])
        return candidates[0]

    def _read_manifest(self, directory: Path) -> RoutineBundleManifest:
        manifest_path, raw_manifest, _body = self._locate_manifest(directory)
        try:
            return RoutineBundleManifest.model_validate(raw_manifest)
        except ValidationError as e:
            raise RoutineBundleError(f"invalid routine manifest at {manifest_path}: {e}") from e

    def _load_dir(self, directory: Path) -> RoutineBundle:
        manifest_path, raw_manifest, body = self._locate_manifest(directory)
        try:
            manifest = RoutineBundleManifest.model_validate(raw_manifest)
        except ValidationError as e:
            raise RoutineBundleError(f"invalid routine manifest at {manifest_path}: {e}") from e
        bundle = RoutineBundle(manifest=manifest, directory=directory, body=body)
        if self._verify_files:
            _verify_file_hashes(bundle)
        return bundle

    def _locate_manifest(self, directory: Path) -> tuple[Path, dict[str, Any], str]:
        for name in _MANIFEST_NAMES:
            candidate = directory / name
            if not candidate.exists():
                continue
            if candidate.suffix == ".md":
                doc = read_markdown(candidate)
                if not doc.frontmatter:
                    raise RoutineBundleError(f"routine.md at {candidate} has no YAML frontmatter")
                return candidate, doc.frontmatter, doc.body
            with candidate.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                raise RoutineBundleError(
                    f"manifest at {candidate} must be a YAML mapping, got {type(data)!r}"
                )
            return candidate, data, ""
        raise ManifestNotFoundError(
            f"no routine manifest ({' | '.join(_MANIFEST_NAMES)}) under {directory}"
        )


def _verify_file_hashes(bundle: RoutineBundle) -> None:
    for entry in bundle.manifest.files:
        path = bundle.directory / entry.path
        if not path.exists():
            raise FileIntegrityError(entry.path, entry.sha256, "<missing>")
        actual = _sha256_file(path)
        expected = entry.sha256
        normalized_expected = expected.removeprefix("sha256:").removeprefix("sha256-")
        if actual != normalized_expected:
            raise FileIntegrityError(entry.path, expected, actual)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
