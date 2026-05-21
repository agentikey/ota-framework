from __future__ import annotations

import re
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

TRACE_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
SPAN_ID_PATTERN = re.compile(r"^[a-f0-9]{16}$")

_TRACE_ID: ContextVar[str | None] = ContextVar("ota_trace_id", default=None)
_SPAN_ID: ContextVar[str | None] = ContextVar("ota_span_id", default=None)


def new_trace_id() -> str:
    return secrets.token_hex(16)


def new_span_id() -> str:
    return secrets.token_hex(8)


def current_trace_id() -> str | None:
    return _TRACE_ID.get()


def current_span_id() -> str | None:
    return _SPAN_ID.get()


def ensure_trace_id() -> str:
    existing = _TRACE_ID.get()
    if existing is not None:
        return existing
    return new_trace_id()


@contextmanager
def bind_trace(
    *,
    trace_id: str | None = None,
    span_id: str | None = None,
) -> Iterator[tuple[str, str]]:
    resolved_trace = trace_id if trace_id is not None else (current_trace_id() or new_trace_id())
    resolved_span = span_id if span_id is not None else new_span_id()
    if not TRACE_ID_PATTERN.match(resolved_trace):
        raise ValueError(f"trace_id must match {TRACE_ID_PATTERN.pattern}: {resolved_trace!r}")
    if not SPAN_ID_PATTERN.match(resolved_span):
        raise ValueError(f"span_id must match {SPAN_ID_PATTERN.pattern}: {resolved_span!r}")
    trace_token = _TRACE_ID.set(resolved_trace)
    span_token = _SPAN_ID.set(resolved_span)
    try:
        yield (resolved_trace, resolved_span)
    finally:
        _SPAN_ID.reset(span_token)
        _TRACE_ID.reset(trace_token)
