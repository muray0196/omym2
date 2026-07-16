"""
Summary: Tests durable provider request cadence reservations.
Why: Proves retries and separate processes cannot bypass provider timing policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast

import pytest

from omym2.adapters.db.sqlite.connection import open_sqlite_connection
from omym2.adapters.db.sqlite.provider_request_cadence import SQLiteProviderRequestCadence

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path


@dataclass(slots=True)
class _AdvancingClock:
    current: datetime

    def now(self) -> datetime:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)


def test_provider_request_cadence_persists_across_adapter_instances(tmp_path: Path) -> None:
    database_path = tmp_path / "omym2.sqlite3"
    clock = _AdvancingClock(datetime(2026, 7, 16, 0, 0, tzinfo=UTC))
    first = SQLiteProviderRequestCadence(database_path, "musicbrainz", clock=clock, sleeper=clock.sleep)
    second = SQLiteProviderRequestCadence(database_path, "musicbrainz", clock=clock, sleeper=clock.sleep)

    first.wait_for_request(1.0)
    second.wait_for_request(1.0)

    assert clock.current == datetime(2026, 7, 16, 0, 0, 1, tzinfo=UTC)
    connection = open_sqlite_connection(database_path)
    try:
        stored = cast(
            "sqlite3.Row | None",
            connection.execute("SELECT provider, last_request_at FROM provider_request_cadence").fetchone(),
        )
    finally:
        connection.close()
    assert stored is not None
    assert tuple(stored) == ("musicbrainz", clock.current.isoformat())


def test_provider_request_cadence_releases_write_lock_before_sleeping(tmp_path: Path) -> None:
    """A separate connection can write while one cadence caller waits for its reserved interval."""
    database_path = tmp_path / "omym2.sqlite3"
    clock = _AdvancingClock(datetime(2026, 7, 16, 0, 0, tzinfo=UTC))
    first = SQLiteProviderRequestCadence(database_path, "musicbrainz", clock=clock, sleeper=clock.sleep)
    first.wait_for_request(1.0)
    writes_during_sleep = 0

    def write_through_separate_connection(seconds: float) -> None:
        nonlocal writes_during_sleep
        connection = open_sqlite_connection(database_path)
        try:
            _ = connection.execute("BEGIN IMMEDIATE")
            _ = connection.execute(
                "INSERT INTO provider_request_cadence (provider, last_request_at) VALUES (?, ?)",
                ("other-provider", clock.current.isoformat()),
            )
            connection.commit()
        finally:
            connection.close()
        writes_during_sleep += 1
        clock.sleep(seconds)

    waiting = SQLiteProviderRequestCadence(
        database_path,
        "musicbrainz",
        clock=clock,
        sleeper=write_through_separate_connection,
    )

    waiting.wait_for_request(1.0)

    assert writes_during_sleep == 1
    assert clock.current == datetime(2026, 7, 16, 0, 0, 1, tzinfo=UTC)


def test_provider_request_cadence_rejects_invalid_inputs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="identity"):
        _ = SQLiteProviderRequestCadence(tmp_path / "db.sqlite3", "  ")

    cadence = SQLiteProviderRequestCadence(tmp_path / "db.sqlite3", "musicbrainz")
    with pytest.raises(ValueError, match="non-negative"):
        cadence.wait_for_request(-0.1)
