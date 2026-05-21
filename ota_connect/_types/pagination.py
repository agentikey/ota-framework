# AUTO-GENERATED from vocabulary/_types.md -- DO NOT EDIT.
# Run `python scripts/gen_vocab_stubs.py` to regenerate.

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")

Cursor = str  # opaque token; adapter-specific format


@dataclass(frozen=True)
class Page(Generic[T]):
    items: list[T]
    next_cursor: Cursor | None  # None when no more pages
