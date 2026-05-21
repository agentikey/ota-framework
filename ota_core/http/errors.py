from __future__ import annotations

import httpx


class HttpError(Exception):
    pass


class EgressBlocked(HttpError):
    def __init__(self, host: str, *, method: str, url: str) -> None:
        super().__init__(f"egress blocked: {method} {url} (host {host!r} not in allowlist)")
        self.host = host
        self.method = method
        self.url = url


class MaxRetriesExceeded(HttpError):
    def __init__(
        self,
        *,
        method: str,
        url: str,
        attempts: int,
        last_response: httpx.Response | None,
        last_exception: BaseException | None,
    ) -> None:
        reason: str
        if last_response is not None:
            reason = f"last status {last_response.status_code}"
        elif last_exception is not None:
            reason = f"last error {type(last_exception).__name__}: {last_exception}"
        else:
            reason = "no response and no exception captured"
        super().__init__(
            f"max retries exceeded for {method} {url} after {attempts} attempts; {reason}"
        )
        self.method = method
        self.url = url
        self.attempts = attempts
        self.last_response = last_response
        self.last_exception = last_exception
