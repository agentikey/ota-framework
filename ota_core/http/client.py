from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from types import TracebackType
from typing import Any

import httpx

from ota_core.http.errors import EgressBlocked, MaxRetriesExceeded

_DEFAULT_RETRY_STATUSES: tuple[int, ...] = (429, 500, 502, 503, 504)

AllowlistMatcher = frozenset[str] | Callable[[str], bool]


@dataclass(frozen=True)
class RateLimitPolicy:
    requests_per_second: float
    burst_capacity: int
    requests_per_minute: float | None = None
    burst_per_minute: int | None = None

    def __post_init__(self) -> None:
        if self.requests_per_second <= 0:
            raise ValueError("requests_per_second must be > 0")
        if self.burst_capacity < 1:
            raise ValueError("burst_capacity must be >= 1")
        if self.requests_per_minute is not None and self.requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be > 0")
        if self.burst_per_minute is not None and self.burst_per_minute < 1:
            raise ValueError("burst_per_minute must be >= 1")


class TokenBucket:
    def __init__(self, policy: RateLimitPolicy) -> None:
        self._sec_rate = policy.requests_per_second
        self._sec_capacity = policy.burst_capacity
        self._sec_tokens = float(policy.burst_capacity)
        self._sec_last_refill = time.monotonic()

        self._min_rate: float | None = None
        self._min_capacity: int = 0
        self._min_tokens: float = 0.0
        self._min_last_refill: float = time.monotonic()
        if policy.requests_per_minute is not None:
            self._min_rate = policy.requests_per_minute / 60.0
            self._min_capacity = (
                policy.burst_per_minute
                if policy.burst_per_minute is not None
                else max(1, int(policy.requests_per_minute))
            )
            self._min_tokens = float(self._min_capacity)

        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1) -> None:
        if tokens < 1:
            raise ValueError("tokens must be >= 1")
        async with self._lock:
            while True:
                self._refill_second()
                if self._min_rate is not None:
                    self._refill_minute()
                wait_sec = max(0.0, (tokens - self._sec_tokens) / self._sec_rate)
                wait_min = 0.0
                if self._min_rate is not None:
                    wait_min = max(0.0, (tokens - self._min_tokens) / self._min_rate)
                wait = max(wait_sec, wait_min)
                if wait <= 0:
                    self._sec_tokens -= tokens
                    if self._min_rate is not None:
                        self._min_tokens -= tokens
                    return
                await asyncio.sleep(wait)

    def _refill_second(self) -> None:
        now = time.monotonic()
        elapsed = now - self._sec_last_refill
        self._sec_tokens = min(
            float(self._sec_capacity),
            self._sec_tokens + elapsed * self._sec_rate,
        )
        self._sec_last_refill = now

    def _refill_minute(self) -> None:
        assert self._min_rate is not None
        now = time.monotonic()
        elapsed = now - self._min_last_refill
        self._min_tokens = min(
            float(self._min_capacity),
            self._min_tokens + elapsed * self._min_rate,
        )
        self._min_last_refill = now


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
        allowlist: AllowlistMatcher | None = None,
        sleep: Any = asyncio.sleep,
    ) -> None:
        self._user_agent = user_agent
        self._default_timeout = default_timeout
        self._max_retries = max_retries
        self._base_backoff = base_backoff
        self._max_backoff = max_backoff
        self._retry_status_codes = retry_status_codes
        self._allowlist: AllowlistMatcher | None = allowlist
        self._sleep = sleep
        self._rate_limits: dict[str, TokenBucket] = {}
        self._client = httpx.AsyncClient(
            headers={"User-Agent": user_agent},
            timeout=default_timeout,
        )

    def set_rate_limit(self, host: str, policy: RateLimitPolicy) -> None:
        self._rate_limits[host] = TokenBucket(policy)

    def set_allowlist(self, allowlist: AllowlistMatcher | None) -> None:
        self._allowlist = allowlist

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        parsed = httpx.URL(url)
        host = parsed.host

        if self._allowlist is not None:
            allowed = (
                self._allowlist(host) if callable(self._allowlist) else host in self._allowlist
            )
            if not allowed:
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
