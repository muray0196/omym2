"""
Summary: Tests timezone-aware time helpers.
Why: Keeps persisted timestamps explicit about UTC conversion.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from omym2.shared.time import NAIVE_DATETIME_MESSAGE, as_utc, utc_now

EXPECTED_UTC_HOUR = 0
UTC_OFFSET_HOURS = 9
UTC_OFFSET_SECONDS = 0
UTC_OFFSET_MINUTES = 0
WALL_CLOCK_DAY = 1
WALL_CLOCK_HOUR = 9
WALL_CLOCK_MICROSECOND = 0
WALL_CLOCK_MINUTE = 0
WALL_CLOCK_MONTH = 1
WALL_CLOCK_SECOND = 0
WALL_CLOCK_YEAR = 2026


def test_utc_now_returns_timezone_aware_utc() -> None:
    """Current timestamp helper returns an aware UTC datetime."""
    timestamp = utc_now()

    assert timestamp.tzinfo is UTC


def test_as_utc_converts_aware_datetime_to_utc() -> None:
    """Aware timestamps are normalized to UTC."""
    tokyo = timezone(timedelta(hours=UTC_OFFSET_HOURS, minutes=UTC_OFFSET_MINUTES, seconds=UTC_OFFSET_SECONDS))
    local_timestamp = datetime(
        WALL_CLOCK_YEAR,
        WALL_CLOCK_MONTH,
        WALL_CLOCK_DAY,
        WALL_CLOCK_HOUR,
        WALL_CLOCK_MINUTE,
        WALL_CLOCK_SECOND,
        WALL_CLOCK_MICROSECOND,
        tzinfo=tokyo,
    )

    converted_timestamp = as_utc(local_timestamp)

    assert converted_timestamp.tzinfo is UTC
    assert converted_timestamp.hour == EXPECTED_UTC_HOUR


def test_as_utc_rejects_naive_datetime() -> None:
    """Naive timestamps are rejected before persistence."""
    aware_timestamp = datetime(
        WALL_CLOCK_YEAR,
        WALL_CLOCK_MONTH,
        WALL_CLOCK_DAY,
        WALL_CLOCK_HOUR,
        WALL_CLOCK_MINUTE,
        WALL_CLOCK_SECOND,
        WALL_CLOCK_MICROSECOND,
        tzinfo=UTC,
    )
    naive_timestamp = aware_timestamp.replace(tzinfo=None)

    with pytest.raises(ValueError, match=NAIVE_DATETIME_MESSAGE):
        _ = as_utc(naive_timestamp)
