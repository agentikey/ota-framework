from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


class CronParseError(ValueError):
    pass


_FIELD_RANGES: tuple[tuple[int, int], ...] = (
    (0, 59),  # minute
    (0, 23),  # hour
    (1, 31),  # day of month
    (1, 12),  # month
    (0, 6),  # day of week (0=Mon, 6=Sun)
)


def _parse_field(spec: str, min_val: int, max_val: int) -> frozenset[int]:
    if spec == "*":
        return frozenset(range(min_val, max_val + 1))
    out: set[int] = set()
    for part in spec.split(","):
        step = 1
        if "/" in part:
            base, _, step_s = part.partition("/")
            try:
                step = int(step_s)
            except ValueError as e:
                raise CronParseError(f"invalid step: {step_s!r}") from e
            if step <= 0:
                raise CronParseError(f"step must be > 0: {step}")
        else:
            base = part
        if base == "*":
            values = range(min_val, max_val + 1)
        elif "-" in base:
            lo, _, hi = base.partition("-")
            try:
                lo_i, hi_i = int(lo), int(hi)
            except ValueError as e:
                raise CronParseError(f"invalid range: {base!r}") from e
            if lo_i > hi_i:
                raise CronParseError(f"range start > end: {base!r}")
            values = range(lo_i, hi_i + 1)
        else:
            try:
                v = int(base)
            except ValueError as e:
                raise CronParseError(f"invalid value: {base!r}") from e
            values = range(v, v + 1)
        for v in values:
            if v < min_val or v > max_val:
                raise CronParseError(f"value {v} outside [{min_val},{max_val}]")
            if (v - values.start) % step == 0:
                out.add(v)
    if not out:
        raise CronParseError(f"empty field: {spec!r}")
    return frozenset(out)


@dataclass(frozen=True)
class CronExpression:
    minutes: frozenset[int]
    hours: frozenset[int]
    days: frozenset[int]
    months: frozenset[int]
    weekdays: frozenset[int]

    @classmethod
    def parse(cls, expr: str) -> CronExpression:
        parts = expr.split()
        if len(parts) != 5:
            raise CronParseError(f"cron expression must have 5 fields, got {len(parts)}: {expr!r}")
        fields = tuple(
            _parse_field(parts[i], _FIELD_RANGES[i][0], _FIELD_RANGES[i][1]) for i in range(5)
        )
        return cls(
            minutes=fields[0],
            hours=fields[1],
            days=fields[2],
            months=fields[3],
            weekdays=fields[4],
        )

    def matches(self, dt: datetime) -> bool:
        return (
            dt.minute in self.minutes
            and dt.hour in self.hours
            and dt.day in self.days
            and dt.month in self.months
            and dt.weekday() in self.weekdays
        )

    def next_after(self, dt: datetime) -> datetime:
        if dt.tzinfo is None:
            raise ValueError("dt must be timezone-aware")
        candidate = (dt + timedelta(minutes=1)).replace(second=0, microsecond=0)
        # Worst-case sweep up to 4 years to handle February-29 edge cases.
        for _ in range(4 * 366 * 24 * 60):
            if self.matches(candidate):
                return candidate
            candidate = candidate + timedelta(minutes=1)
        raise CronParseError("no upcoming time matches expression within 4 years")
