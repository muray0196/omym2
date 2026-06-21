"""
Summary: Provides timezone-aware time helpers.
Why: Keeps persisted timestamps explicit and deterministic at boundaries.
"""

from __future__ import annotations

from datetime import UTC, datetime

NAIVE_DATETIME_MESSAGE = "Datetime value must include timezone information."


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """Convert a timezone-aware timestamp to UTC.

    Args:
        value: Timestamp supplied by caller or adapter code.

    Returns:
        The same instant represented in UTC.

    Raises:
        ValueError: The timestamp has no timezone information.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(NAIVE_DATETIME_MESSAGE)
    return value.astimezone(UTC)
