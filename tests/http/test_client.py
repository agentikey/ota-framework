from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest
from pytest_httpx import HTTPXMock

from ota_core.http import EgressBlocked, HttpClient, MaxRetriesExceeded


def _record_sleeps(records: list[float]) -> Callable[[float], Any]:
    async def fake_sleep(delay: float) -> None:
        records.append(delay)

    return fake_sleep


async def test_get_passes_through_user_agent(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="https://api.example.com/ping", json={"ok": True})

    async with HttpClient(user_agent="OneTrueAgent-Core/0.0.1") as client:
        response = await client.get("https://api.example.com/ping")

    assert response.status_code == 200
    request = httpx_mock.get_request()
    assert request is not None
    assert request.headers["user-agent"] == "OneTrueAgent-Core/0.0.1"


async def test_retries_on_503_then_succeeds(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="https://api.example.com/x", status_code=503)
    httpx_mock.add_response(url="https://api.example.com/x", status_code=503)
    httpx_mock.add_response(url="https://api.example.com/x", status_code=200, json={"ok": True})
    sleeps: list[float] = []

    async with HttpClient(max_retries=3, sleep=_record_sleeps(sleeps)) as client:
        response = await client.get("https://api.example.com/x")

    assert response.status_code == 200
    assert len(httpx_mock.get_requests()) == 3
    assert len(sleeps) == 2


async def test_retry_after_seconds_header_honored(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://api.example.com/r",
        status_code=429,
        headers={"Retry-After": "2.5"},
    )
    httpx_mock.add_response(url="https://api.example.com/r", status_code=200)
    sleeps: list[float] = []

    async with HttpClient(max_retries=2, sleep=_record_sleeps(sleeps)) as client:
        await client.get("https://api.example.com/r")

    assert sleeps == [2.5]


async def test_exhausted_retries_raises_max_retries(httpx_mock: HTTPXMock) -> None:
    for _ in range(4):
        httpx_mock.add_response(url="https://api.example.com/x", status_code=503)
    sleeps: list[float] = []

    with pytest.raises(MaxRetriesExceeded) as exc_info:
        async with HttpClient(max_retries=3, sleep=_record_sleeps(sleeps)) as client:
            await client.get("https://api.example.com/x")

    assert exc_info.value.last_response is not None
    assert exc_info.value.last_response.status_code == 503
    assert exc_info.value.attempts == 4


async def test_network_error_triggers_retries(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("network down"))
    httpx_mock.add_exception(httpx.ConnectError("network down"))
    httpx_mock.add_response(url="https://api.example.com/x", status_code=200)
    sleeps: list[float] = []

    async with HttpClient(max_retries=3, sleep=_record_sleeps(sleeps)) as client:
        response = await client.get("https://api.example.com/x")

    assert response.status_code == 200
    assert len(sleeps) == 2


async def test_non_retryable_status_returned_unchanged(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="https://api.example.com/x", status_code=404)

    async with HttpClient(max_retries=3) as client:
        response = await client.get("https://api.example.com/x")

    assert response.status_code == 404
    assert len(httpx_mock.get_requests()) == 1


async def test_egress_allowlist_blocks_unlisted_host() -> None:
    async with HttpClient(allowlist=frozenset({"good.example.com"})) as client:
        with pytest.raises(EgressBlocked) as exc_info:
            await client.get("https://evil.example.com/x")

    assert exc_info.value.host == "evil.example.com"


async def test_egress_allowlist_permits_listed_host(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="https://good.example.com/x", json={})

    async with HttpClient(allowlist=frozenset({"good.example.com"})) as client:
        response = await client.get("https://good.example.com/x")

    assert response.status_code == 200
