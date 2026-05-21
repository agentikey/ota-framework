from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field


class DuplicateBranchError(Exception):
    pass


@dataclass(frozen=True)
class Branch:
    """A role-specialized sub-agent grouping a set of routines.

    v0.1 ships with one branch (`productivity`). The abstraction is here so
    v0.2+ can add more (operations, research, etc.) without runtime changes.
    """

    name: str
    description: str = ""
    routines: tuple[str, ...] = ()

    def contains(self, routine_id: str) -> bool:
        return routine_id in self.routines


@dataclass
class BranchRegistry:
    _branches: dict[str, Branch] = field(default_factory=dict)

    def register(self, branch: Branch) -> None:
        if branch.name in self._branches:
            raise DuplicateBranchError(f"branch already registered: {branch.name}")
        self._branches[branch.name] = branch

    def deregister(self, name: str) -> None:
        self._branches.pop(name, None)

    def get(self, name: str) -> Branch | None:
        return self._branches.get(name)

    def all(self) -> list[Branch]:
        return list(self._branches.values())

    def for_routine(self, routine_id: str) -> Branch | None:
        for branch in self._branches.values():
            if branch.contains(routine_id):
                return branch
        return None

    @classmethod
    def default(cls, *, routines: Iterable[str] = ()) -> BranchRegistry:
        """Shorthand: a registry with the single `productivity` branch."""
        registry = cls()
        registry.register(
            Branch(
                name="productivity",
                description="Productivity automation routines (v0.1 default branch).",
                routines=tuple(routines),
            )
        )
        return registry
