from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ota_core.automation.cron import CronExpression, CronParseError


def test_parse_star() -> None:
    cron = CronExpression.parse("* * * * *")
    assert 0 in cron.minutes
    assert 59 in cron.minutes
    assert len(cron.hours) == 24
    assert len(cron.weekdays) == 7


def test_parse_literal() -> None:
    cron = CronExpression.parse("30 14 * * *")
    assert cron.minutes == frozenset({30})
    assert cron.hours == frozenset({14})


def test_parse_step() -> None:
    cron = CronExpression.parse("*/15 * * * *")
    assert cron.minutes == frozenset({0, 15, 30, 45})


def test_parse_list() -> None:
    cron = CronExpression.parse("0,15,30 * * * *")
    assert cron.minutes == frozenset({0, 15, 30})


def test_parse_range() -> None:
    cron = CronExpression.parse("0-10 * * * *")
    assert cron.minutes == frozenset(range(0, 11))


def test_parse_invalid_field_count() -> None:
    with pytest.raises(CronParseError, match="5 fields"):
        CronExpression.parse("* * * *")


def test_parse_out_of_range() -> None:
    with pytest.raises(CronParseError, match="outside"):
        CronExpression.parse("60 * * * *")


def test_matches_exact_time() -> None:
    cron = CronExpression.parse("30 14 * * *")
    assert cron.matches(datetime(2026, 5, 20, 14, 30, tzinfo=UTC))
    assert not cron.matches(datetime(2026, 5, 20, 14, 31, tzinfo=UTC))


def test_next_after_within_hour() -> None:
    cron = CronExpression.parse("*/15 * * * *")
    nxt = cron.next_after(datetime(2026, 5, 20, 14, 7, tzinfo=UTC))
    assert nxt == datetime(2026, 5, 20, 14, 15, tzinfo=UTC)


def test_next_after_crosses_day() -> None:
    cron = CronExpression.parse("0 0 * * *")  # midnight
    nxt = cron.next_after(datetime(2026, 5, 20, 23, 59, tzinfo=UTC))
    assert nxt == datetime(2026, 5, 21, 0, 0, tzinfo=UTC)


def test_next_after_requires_aware() -> None:
    cron = CronExpression.parse("* * * * *")
    with pytest.raises(ValueError, match="timezone-aware"):
        cron.next_after(datetime(2026, 5, 20, 14, 0))


def test_weekday_filter() -> None:
    # Monday only at noon
    cron = CronExpression.parse("0 12 * * 0")
    monday = datetime(2026, 5, 18, 12, 0, tzinfo=UTC)  # 2026-05-18 was a Monday
    tuesday = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)
    assert cron.matches(monday)
    assert not cron.matches(tuesday)
