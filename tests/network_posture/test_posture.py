from __future__ import annotations

import time

import pytest
from pytest_httpx import HTTPXMock

from ota_core.http.client import HttpClient, RateLimitPolicy, TokenBucket
from ota_core.http.errors import EgressBlocked
from ota_core.network_posture import AllowlistRule, NetworkPosture, compile_allowlist


def test_allowlist_rule_exact_match() -> None:
    rule = AllowlistRule("api.slack.com")
    assert rule.matches("api.slack.com")
    assert not rule.matches("hooks.slack.com")


def test_allowlist_rule_wildcard_subdomain() -> None:
    rule = AllowlistRule("*.slack.com")
    assert rule.matches("api.slack.com")
    assert rule.matches("hooks.slack.com")
    assert not rule.matches("slack.com")
    assert not rule.matches("api.notslack.com")


def test_allowlist_rule_character_class() -> None:
    rule = AllowlistRule("region-[12].googleapis.com")
    assert rule.matches("region-1.googleapis.com")
    assert rule.matches("region-2.googleapis.com")
    assert not rule.matches("region-3.googleapis.com")


def test_compile_allowlist_combines_rules() -> None:
    predicate = compile_allowlist(["api.slack.com", "*.googleapis.com"])
    assert predicate("api.slack.com")
    assert predicate("gmail.googleapis.com")
    assert not predicate("evil.com")


async def test_posture_blocks_disallowed_host(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="https://api.slack.com/api/x", json={})
    client = HttpClient()
    posture = NetworkPosture(client)
    posture.configure_allowlist(["api.slack.com"])
    response = await client.get("https://api.slack.com/api/x")
    assert response.status_code == 200
    with pytest.raises(EgressBlocked):
        await client.get("https://evil.com/x")
    await client.aclose()


async def test_posture_glob_allows_matching_subdomain(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="https://gmail.googleapis.com/x", json={})
    client = HttpClient()
    posture = NetworkPosture(client)
    posture.configure_allowlist(["*.googleapis.com"])
    response = await client.get("https://gmail.googleapis.com/x")
    assert response.status_code == 200
    await client.aclose()


async def test_posture_extend_and_remove(httpx_mock: HTTPXMock) -> None:
    client = HttpClient()
    posture = NetworkPosture(client)
    posture.configure_allowlist(["api.slack.com"])
    posture.extend_allowlist(["*.googleapis.com"])
    assert posture.is_allowed("gmail.googleapis.com")
    posture.remove_allowlist_entries(["api.slack.com"])
    assert not posture.is_allowed("api.slack.com")
    await client.aclose()


async def test_posture_empty_allowlist_blocks_everything(httpx_mock: HTTPXMock) -> None:
    client = HttpClient()
    posture = NetworkPosture(client)
    posture.configure_allowlist([])
    with pytest.raises(EgressBlocked):
        await client.get("https://anything.com/x")
    await client.aclose()


async def test_rate_limit_rpm_blocks_after_minute_budget() -> None:
    # rpm=600 → 10/s refill, burst=3 → after burst, ~0.1s wait per token
    bucket = TokenBucket(
        RateLimitPolicy(
            requests_per_second=100.0,
            burst_capacity=100,
            requests_per_minute=600.0,
            burst_per_minute=3,
        )
    )
    for _ in range(3):
        await bucket.acquire()
    start = time.monotonic()
    await bucket.acquire()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.08  # ~0.1s wait on the per-minute bucket


async def test_rate_limit_rpm_does_not_block_within_minute_burst() -> None:
    bucket = TokenBucket(
        RateLimitPolicy(
            requests_per_second=100.0,
            burst_capacity=100,
            requests_per_minute=600.0,
            burst_per_minute=10,
        )
    )
    start = time.monotonic()
    for _ in range(10):
        await bucket.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.05


async def test_rate_limit_tighter_bucket_wins() -> None:
    # rps=1000 (very loose), rpm=300 (5/s, tight) — minute bucket dominates after burst
    bucket = TokenBucket(
        RateLimitPolicy(
            requests_per_second=1000.0,
            burst_capacity=1000,
            requests_per_minute=300.0,
            burst_per_minute=2,
        )
    )
    await bucket.acquire()
    await bucket.acquire()
    start = time.monotonic()
    await bucket.acquire()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.15  # 1 token at 5/s = 200ms


def test_rate_limit_policy_validates_rpm_inputs() -> None:
    with pytest.raises(ValueError, match="requests_per_minute must be > 0"):
        RateLimitPolicy(requests_per_second=1.0, burst_capacity=1, requests_per_minute=0)
    with pytest.raises(ValueError, match="burst_per_minute must be >= 1"):
        RateLimitPolicy(
            requests_per_second=1.0,
            burst_capacity=1,
            requests_per_minute=10,
            burst_per_minute=0,
        )


async def test_posture_configure_rate_limit_records_policy() -> None:
    client = HttpClient()
    posture = NetworkPosture(client)
    policy = RateLimitPolicy(requests_per_second=1.0, burst_capacity=5, requests_per_minute=60)
    posture.configure_rate_limit("api.slack.com", policy)
    assert posture.rate_limits == {"api.slack.com": policy}
    posture.clear_rate_limit("api.slack.com")
    assert posture.rate_limits == {}
    await client.aclose()


def test_posture_exposes_rules() -> None:
    client = HttpClient()
    posture = NetworkPosture(client)
    posture.configure_allowlist(["a.com", "*.b.com"])
    patterns = [r.pattern for r in posture.rules]
    assert patterns == ["a.com", "*.b.com"]
