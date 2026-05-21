from __future__ import annotations

import pytest

from ota_core.branches import Branch, BranchRegistry, DuplicateBranchError


def test_branch_contains() -> None:
    b = Branch(name="productivity", routines=("ota.hello", "ota.greet"))
    assert b.contains("ota.hello")
    assert not b.contains("ota.ghost")


def test_branch_is_frozen() -> None:
    b = Branch(name="x")
    with pytest.raises(AttributeError):
        b.name = "y"  # type: ignore[misc]


def test_registry_register_and_get() -> None:
    registry = BranchRegistry()
    branch = Branch(name="productivity", routines=("ota.hello",))
    registry.register(branch)
    assert registry.get("productivity") is branch


def test_registry_duplicate_raises() -> None:
    registry = BranchRegistry()
    registry.register(Branch(name="x"))
    with pytest.raises(DuplicateBranchError):
        registry.register(Branch(name="x"))


def test_registry_for_routine() -> None:
    registry = BranchRegistry()
    registry.register(Branch(name="productivity", routines=("ota.hello",)))
    registry.register(Branch(name="ops", routines=("ota.deploy",)))
    assert registry.for_routine("ota.hello") is not None
    assert registry.for_routine("ota.hello").name == "productivity"
    assert registry.for_routine("ota.unknown") is None


def test_registry_deregister() -> None:
    registry = BranchRegistry()
    registry.register(Branch(name="x"))
    registry.deregister("x")
    assert registry.get("x") is None


def test_registry_default_seeds_productivity() -> None:
    registry = BranchRegistry.default(routines=["ota.hello"])
    productivity = registry.get("productivity")
    assert productivity is not None
    assert "ota.hello" in productivity.routines


def test_registry_all_returns_list() -> None:
    registry = BranchRegistry()
    registry.register(Branch(name="a"))
    registry.register(Branch(name="b"))
    names = {b.name for b in registry.all()}
    assert names == {"a", "b"}
