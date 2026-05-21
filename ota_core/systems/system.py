from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ota_core.branches import BranchRegistry
from ota_core.contracts.audit_event import Principal
from ota_core.systems.engine import RoutineEngine, RoutineRunResult
from ota_core.systems.load_manifest import LoadManifestResolver

if TYPE_CHECKING:
    from ota_core.conductor import Conductor, Intent


@dataclass
class System:
    """Wires Conductor → Branch → Routine into a single dispatch surface.

    v0.1 has one branch (productivity) and direct routing, so the dispatch
    chain is trivial. The composition exists so v0.2+ can plug in
    branch-aware routing without rewriting callers.
    """

    conductor: Conductor
    branches: BranchRegistry
    engine: RoutineEngine
    load_manifest_resolver: LoadManifestResolver

    async def dispatch(
        self,
        intent: Intent,
        *,
        principal: Principal,
        request_id: str | None = None,
    ) -> RoutineRunResult:
        return await self.conductor.dispatch(
            intent,
            principal=principal,
            request_id=request_id,
        )

    def branch_for(self, routine_id: str) -> str | None:
        branch = self.branches.for_routine(routine_id)
        return branch.name if branch is not None else None
