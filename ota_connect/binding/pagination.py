"""`iter_all` — framework primitive that flattens a paginated verb.

Routines avoid the boilerplate of `while next_cursor: page = verb(..., cursor)`
by calling:

    from ota_connect import iter_all
    from ota_connect.messaging import list_recent_messages

    for msg in iter_all(list_recent_messages, channel=ch, since=since):
        ...

The wrapped verb must:
- Accept `cursor: Cursor | None = None` (kwarg).
- Return a `Page[T]` (items + next_cursor).

`iter_all` repeatedly calls the verb until `next_cursor is None`. Failures
during a page propagate; partial iteration is the caller's problem to handle
via try/except.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any, TypeVar

from ota_connect._types.pagination import Page

T = TypeVar("T")


def iter_all(
    verb: Callable[..., Page[T]],
    /,
    **kwargs: Any,
) -> Iterator[T]:
    if "cursor" in kwargs:
        raise TypeError(
            f"iter_all manages the cursor; do not pass `cursor=` (got {kwargs['cursor']!r})"
        )
    cursor: str | None = None
    while True:
        page = verb(cursor=cursor, **kwargs)
        yield from page.items
        if page.next_cursor is None:
            return
        cursor = page.next_cursor
