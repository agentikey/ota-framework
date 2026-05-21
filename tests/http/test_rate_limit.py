from __future__ import annotations

import asyncio
import time

import pytest

from ota_core.http import RateLimitPolicy, TokenBucket
from ota_core.http.client import backoff_delay, parse_retry_after


def test_rate_limit_policy_rejects_invalid() -> None:
    with pytest.raises(ValueError, match="requests_per_second"):
        RateLimitPolicy(requests_per_second=0, burst_capacity=1)
    with pytest.raises(ValueError, match="burst_capacity"):
        RateLimitPolicy(requests_per_second=1.0, burst_capacity=0)


async def test_burst_capacity_allows_immediate_back_to_back() -> None:
    bucket = TokenBucket(RateLimitPolicy(requests_per_second=1.0, burst_capacity=5))
    start = time.monotonic()
    for _ in range(5):
        await bucket.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.05


async def test_exceeding_burst_blocks_until_refill() -> None:
    bucket = TokenBucket(RateLimitPolicy(requests_per_second=20.0, burst_capacity=1))
    await bucket.acquire()
    start = time.monotonic()
    await bucket.acquire()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.04


def test_parse_retry_after_seconds() -> None:
    assert parse_retry_after("3") == 3.0
    assert parse_retry_after("0.5") == 0.5
    assert parse_retry_after("  10 ") == 10.0


def test_parse_retry_after_http_date() -> None:
    far_future = "Wed, 01 Jan 2099 00:00:00 GMT"
    result = parse_retry_after(far_future)
    assert result is not None
    assert result > 0


def test_parse_retry_after_negative_clamped_to_zero() -> None:
    past_date = "Wed, 01 Jan 2000 00:00:00 GMT"
    assert parse_retry_after(past_date) == 0.0


def test_parse_retry_after_none() -> None:
    assert parse_retry_after(None) is None
    assert parse_retry_after("") is None
    assert parse_retry_after("garbage value") is None


def test_backoff_delay_within_bounds() -> None:
    for attempt in range(6):
        delay = backoff_delay(attempt, base=0.5, cap=10.0)
        assert 0 <= delay <= 10.0


async def test_acquire_zero_tokens_rejected() -> None:
    bucket = TokenBucket(RateLimitPolicy(requests_per_second=1.0, burst_capacity=1))
    with pytest.raises(ValueError, match=">= 1"):
        await bucket.acquire(0)


async def test_concurrent_acquires_serialized() -> None:
    bucket = TokenBucket(RateLimitPolicy(requests_per_second=50.0, burst_capacity=1))
    await bucket.acquire()
    start = time.monotonic()
    await asyncio.gather(bucket.acquire(), bucket.acquire(), bucket.acquire())
    elapsed = time.monotonic() - start
    assert elapsed >= 0.04
