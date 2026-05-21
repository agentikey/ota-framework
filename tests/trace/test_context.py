from __future__ import annotations

import asyncio
import re

import pytest

from ota_core.trace import (
    SPAN_ID_PATTERN,
    TRACE_ID_PATTERN,
    bind_trace,
    current_span_id,
    current_trace_id,
    ensure_trace_id,
    new_span_id,
    new_trace_id,
)


def test_new_trace_id_matches_w3c_pattern() -> None:
    for _ in range(50):
        trace_id = new_trace_id()
        assert TRACE_ID_PATTERN.match(trace_id)
        assert len(trace_id) == 32


def test_new_span_id_matches_w3c_pattern() -> None:
    for _ in range(50):
        span_id = new_span_id()
        assert SPAN_ID_PATTERN.match(span_id)
        assert len(span_id) == 16


def test_current_trace_id_returns_none_outside_bind() -> None:
    assert current_trace_id() is None
    assert current_span_id() is None


def test_bind_trace_sets_and_restores() -> None:
    assert current_trace_id() is None
    with bind_trace() as (trace_id, span_id):
        assert current_trace_id() == trace_id
        assert current_span_id() == span_id
    assert current_trace_id() is None
    assert current_span_id() is None


def test_bind_trace_uses_supplied_ids() -> None:
    trace = "0123456789abcdef0123456789abcdef"
    span = "0123456789abcdef"
    with bind_trace(trace_id=trace, span_id=span) as (returned_trace, returned_span):
        assert returned_trace == trace
        assert returned_span == span
        assert current_trace_id() == trace
        assert current_span_id() == span


def test_bind_trace_inherits_outer_trace_id() -> None:
    trace = "feed1234feed1234feed1234feed1234"
    with bind_trace(trace_id=trace):
        with bind_trace() as (inner_trace, inner_span):
            assert inner_trace == trace
            assert re.fullmatch(SPAN_ID_PATTERN.pattern, inner_span)


def test_bind_trace_rejects_malformed_trace_id() -> None:
    with pytest.raises(ValueError, match="trace_id must match"):
        with bind_trace(trace_id="not-hex"):
            pass


def test_bind_trace_rejects_malformed_span_id() -> None:
    with pytest.raises(ValueError, match="span_id must match"):
        with bind_trace(span_id="not-hex"):
            pass


def test_ensure_trace_id_creates_when_unset() -> None:
    assert current_trace_id() is None
    trace_id = ensure_trace_id()
    assert TRACE_ID_PATTERN.match(trace_id)
    assert current_trace_id() is None


def test_ensure_trace_id_returns_existing() -> None:
    trace = "cafe1234cafe1234cafe1234cafe1234"
    with bind_trace(trace_id=trace):
        assert ensure_trace_id() == trace


async def test_trace_id_isolated_per_async_task() -> None:
    seen: dict[str, str | None] = {}

    async def child(name: str) -> None:
        with bind_trace() as (trace_id, _):
            await asyncio.sleep(0)
            seen[name] = current_trace_id()
            assert current_trace_id() == trace_id

    await asyncio.gather(child("a"), child("b"), child("c"))
    assert len({v for v in seen.values() if v}) == 3
