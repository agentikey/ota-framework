from __future__ import annotations

from dataclasses import dataclass

from ota_core.routine_source import RoutineSource


@dataclass(frozen=True)
class LoadManifest:
    """Pre-flight context-resolution output for a routing decision.

    Per architecture §3 Conductor: the conductor's routing output is a
    declared load manifest, not a free-form handoff. The framework loads
    exactly this set deterministically — no LLM judgment in the loading step.
    """

    routine_id: str
    integration_ids: tuple[str, ...]
    state_shards: tuple[str, ...]
    identity_files: tuple[str, ...] = ()
    startup_context: tuple[str, ...] = ()


class LoadManifestResolver:
    """Resolves a routine_id into its declared load manifest.

    v0.1 derives the manifest from the routine bundle. v0.2+ may extend with
    operator-provided overrides and identity-file selection driven by a
    `requires_identity` declaration.
    """

    def __init__(self, *, routine_source: RoutineSource) -> None:
        self._source = routine_source

    def resolve(self, routine_id: str) -> LoadManifest:
        bundle = self._source.load(routine_id)
        manifest = bundle.manifest
        return LoadManifest(
            routine_id=routine_id,
            integration_ids=tuple(d.id for d in manifest.dependencies.integrations),
            state_shards=tuple(s.name for s in manifest.state.shards),
            identity_files=(),  # v0.2: derived from a `requires_identity` field
            startup_context=(),
        )
