from __future__ import annotations

import fnmatch
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from ota_core.http.client import HttpClient, RateLimitPolicy


@dataclass(frozen=True)
class AllowlistRule:
    pattern: str

    def matches(self, host: str) -> bool:
        if self.pattern == host:
            return True
        if "*" in self.pattern or "?" in self.pattern or "[" in self.pattern:
            return fnmatch.fnmatchcase(host, self.pattern)
        return False


def compile_allowlist(patterns: Iterable[str]) -> Callable[[str], bool]:
    rules = tuple(AllowlistRule(p) for p in patterns)

    def predicate(host: str) -> bool:
        return any(rule.matches(host) for rule in rules)

    return predicate


class NetworkPosture:
    def __init__(self, http_client: HttpClient) -> None:
        self._http = http_client
        self._rules: tuple[AllowlistRule, ...] = ()
        self._rate_limits: dict[str, RateLimitPolicy] = {}

    @property
    def rules(self) -> tuple[AllowlistRule, ...]:
        return self._rules

    @property
    def rate_limits(self) -> dict[str, RateLimitPolicy]:
        return dict(self._rate_limits)

    def configure_allowlist(self, patterns: Iterable[str]) -> None:
        self._rules = tuple(AllowlistRule(p) for p in patterns)
        if not self._rules:
            self._http.set_allowlist(frozenset())
            return
        rules = self._rules
        self._http.set_allowlist(lambda host: any(rule.matches(host) for rule in rules))

    def extend_allowlist(self, patterns: Iterable[str]) -> None:
        merged = list(rule.pattern for rule in self._rules)
        merged.extend(patterns)
        self.configure_allowlist(merged)

    def remove_allowlist_entries(self, patterns: Iterable[str]) -> None:
        drop = set(patterns)
        remaining = [r.pattern for r in self._rules if r.pattern not in drop]
        self.configure_allowlist(remaining)

    def is_allowed(self, host: str) -> bool:
        return any(rule.matches(host) for rule in self._rules)

    def configure_rate_limit(self, host: str, policy: RateLimitPolicy) -> None:
        self._rate_limits[host] = policy
        self._http.set_rate_limit(host, policy)

    def clear_rate_limit(self, host: str) -> None:
        self._rate_limits.pop(host, None)
