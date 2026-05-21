from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from types import TracebackType
from typing import Any

import httpx

from ota_core.http.errors import EgressBlocked, MaxRetriesExceeded

_DEFAULT_RETRY_STATUSES: tuple[int, ...] = (429, 500, 502, 503, 504)


@dataclass(frozen=True)
class RateLimitPolicy:
    requests_per_second: float
    burst_capacity: int

    def __post_init__(self) -> None:
        if self.requests_per_second <= 0:
            raise ValueError("requests_per_second must be > 0")
        if self.burst_capacity < 1:
            raise ValueError("burst_capacity must be >= 1")


class TokenBucket:
    def __init__(self, policy: RateLimitPolicy) -> None:
        self._rate = policy.requests_per_second
        self._capacity = policy.burst_capacity
        self._tokens = float(policy.burst_capacity)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1) -> None:
        if tokens < 1:
            raise ValueError("tokens must be >= 1")
        async with self._lock:
            while True:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
                deficit = tokens - self._tokens
                await asyncio.sleep(deficit / self._rate)

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(float(self._capacity), self._tokens + elapsed * self._rate)
        self._last_refill = now


def parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    stripped = value.strip()
    try:
        return max(0.0, float(stripped))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(stripped)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    delta = (when - datetime.now(UTC)).total_seconds()
    return max(0.0, delta)


def backoff_delay(attempt: int, base: float, cap: float) -> float:
    exp = min(cap, base * (2**attempt))
    return random.uniform(0, exp)


class HttpClient:
    def __init__(
        self,
        *,
        user_agent: str = "OneTrueAgent-Core/0.0.1",
        default_timeout: float = 30.0,
        max_retries: int = 3,
        base_backoff: float = 0.5,
        max_backoff: float = 60.0,
        retry_status_codes: tuple[int, ...] = _DEFAULT_RETRY_STATUSES,
        allowlist: frozenset[str] | None = None,
        sleep: Any = asyncio.sleep,
    ) -> None:
        self._user_agent = user_agent
        self._default_timeout = default_timeout
        self._max_retries = max_retries
        self._base_backoff = base_backoff
        self._max_backoff = max_backoff
        self._retry_status_codes = retry_status_codes
        self._allowlist: frozenset[str] | None = allowlist
        self._sleep = sleep
        self._rate_limits: dict[str, TokenBucket] = {}
        self._client = httpx.AsyncClient(
            headers={"User-Agent": user_agent},
            timeout=default_timeout,
        )

    def set_rate_limit(self, host: str, policy: RateLimitPolicy) -> None:
        self._rate_limits[host] = TokenBucket(policy)

    def set_allowlist(self, allowlist: frozenset[str] | None) -> None:
        self._allowlist = allowlist

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        parsed = httpx.URL(url)
        host = parsed.host

        if self._allowlist is not None and host not in self._allowlist:
            raise EgressBlocked(host, method=method, url=url)

        bucket = self._rate_limits.get(host)

        last_response: httpx.Response | None = None
        last_exception: BaseException | None = None

        for attempt in range(self._max_retries + 1):
            if bucket is not None:
                await bucket.acquire()
            try:
                response = await self._client.request(method, url, **kwargs)
            except (httpx.NetworkError, httpx.TimeoutException) as e:
                last_exception = e
                last_response = None
                if attempt >= self._max_retries:
                    raise MaxRetriesExceeded(
                        method=method,
                        url=url,
                        attempts=attempt + 1,
                        last_response=None,
                        last_exception=e,
                    ) from e
                await self._sleep(backoff_delay(attempt, self._base_backoff, self._max_backoff))
                continue

            if response.status_code not in self._retry_status_codes:
                return response

            last_response = response
            last_exception = None
            if attempt >= self._max_retries:
                raise MaxRetriesExceeded(
                    method=method,
                    url=url,
                    attempts=attempt + 1,
                    last_response=response,
                    last_exception=None,
                )

            retry_after = parse_retry_after(response.headers.get("Retry-After"))
            delay = (
                retry_after
                if retry_after is not None
                else backoff_delay(attempt, self._base_backoff, self._max_backoff)
            )
            await self._sleep(delay)

        raise MaxRetriesExceeded(
            method=method,
            url=url,
            attempts=self._max_retries + 1,
            last_response=last_response,
            last_exception=last_exception,
        )

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("PUT", url, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("PATCH", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("DELETE", url, **kwargs)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> HttpClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()
