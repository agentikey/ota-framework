from __future__ import annotations

from typing import Any

import pytest

from ota_connect import iter_all
from ota_connect._types.pagination import Page


def test_iter_all_drains_single_page() -> None:
    def verb(*, cursor: str | None = None) -> Page[int]:
        assert cursor is None
        return Page(items=[1, 2, 3], next_cursor=None)

    assert list(iter_all(verb)) == [1, 2, 3]


def test_iter_all_follows_cursor() -> None:
    pages: dict[str | None, Page[int]] = {
        None: Page(items=[1, 2], next_cursor="c1"),
        "c1": Page(items=[3, 4], next_cursor="c2"),
        "c2": Page(items=[5], next_cursor=None),
    }

    def verb(*, cursor: str | None = None) -> Page[int]:
        return pages[cursor]

    assert list(iter_all(verb)) == [1, 2, 3, 4, 5]


def test_iter_all_passes_kwargs_through() -> None:
    seen: list[dict[str, Any]] = []

    def verb(*, since: str, cursor: str | None = None) -> Page[int]:
        seen.append({"since": since, "cursor": cursor})
        return Page(items=[1], next_cursor=None)

    list(iter_all(verb, since="2025-01-01"))
    assert seen == [{"since": "2025-01-01", "cursor": None}]


def test_iter_all_rejects_explicit_cursor() -> None:
    def verb(*, cursor: str | None = None) -> Page[int]:
        return Page(items=[], next_cursor=None)

    with pytest.raises(TypeError, match="manages the cursor"):
        list(iter_all(verb, cursor="x"))


def test_iter_all_propagates_exception() -> None:
    def verb(*, cursor: str | None = None) -> Page[int]:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        list(iter_all(verb))
