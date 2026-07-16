"""
Summary: Reserves durable cross-process provider request cadence slots.
Why: Prevents process restarts or concurrent callers from exceeding provider limits.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, cast

from omym2.adapters.db.sqlite.connection import open_sqlite_connection
from omym2.adapters.db.sqlite.migration_runner import ensure_database_migrated
from omym2.features.common_ports import SystemClock
from omym2.shared.time import as_utc

if TYPE_CHECKING:
    from collections.abc import Callable
    from os import PathLike

    from omym2.features.common_ports import Clock

SELECT_PROVIDER_CADENCE_SQL = """
SELECT last_request_at
FROM provider_request_cadence
WHERE provider = ?
"""
UPSERT_PROVIDER_CADENCE_SQL = """
INSERT INTO provider_request_cadence (provider, last_request_at)
VALUES (?, ?)
ON CONFLICT(provider) DO UPDATE SET last_request_at = excluded.last_request_at
"""
INVALID_PROVIDER_MESSAGE = "Provider cadence identity must not be empty."
INVALID_INTERVAL_MESSAGE = "Provider cadence interval must be non-negative."
INVALID_TIMESTAMP_MESSAGE = "Stored provider cadence timestamp must be text."
CADENCE_STORAGE_ERROR_MESSAGE = "Provider cadence storage is unavailable."


@dataclass(frozen=True, slots=True)
class SQLiteProviderRequestCadence:
    """Reserve one provider request time without holding a transaction while waiting."""

    database_path: str | PathLike[str]
    provider: str
    clock: Clock = field(default_factory=SystemClock)
    sleeper: Callable[[float], None] = time.sleep

    def __post_init__(self) -> None:
        """Reject identities that cannot form a durable cadence key."""
        if self.provider.strip() == "":
            raise ValueError(INVALID_PROVIDER_MESSAGE)

    def wait_for_request(self, minimum_interval_seconds: float) -> None:
        """Atomically reserve the next permitted request time across processes."""
        if minimum_interval_seconds < 0:
            raise ValueError(INVALID_INTERVAL_MESSAGE)
        try:
            ensure_database_migrated(self.database_path)
            while True:
                remaining = self._try_reserve(minimum_interval_seconds)
                if remaining <= 0:
                    return
                self.sleeper(remaining)
        except (sqlite3.Error, TypeError, ValueError) as exc:
            raise OSError(CADENCE_STORAGE_ERROR_MESSAGE) from exc

    def _try_reserve(self, minimum_interval_seconds: float) -> float:
        connection = open_sqlite_connection(self.database_path)
        try:
            _ = connection.execute("BEGIN IMMEDIATE")
            row = cast(
                "sqlite3.Row | None",
                connection.execute(SELECT_PROVIDER_CADENCE_SQL, (self.provider,)).fetchone(),
            )
            now = as_utc(self.clock.now())
            remaining = _remaining_interval(row, now, minimum_interval_seconds)
            if remaining > 0:
                connection.rollback()
                return remaining
            _ = connection.execute(
                UPSERT_PROVIDER_CADENCE_SQL,
                (self.provider, now.isoformat()),
            )
            connection.commit()
            return 0.0
        finally:
            if connection.in_transaction:
                connection.rollback()
            connection.close()


def _remaining_interval(
    row: sqlite3.Row | None,
    now: datetime,
    minimum_interval_seconds: float,
) -> float:
    if row is None:
        return 0.0
    raw_timestamp = cast("object", row["last_request_at"])
    if not isinstance(raw_timestamp, str):
        raise TypeError(INVALID_TIMESTAMP_MESSAGE)
    last_request_at = as_utc(datetime.fromisoformat(raw_timestamp))
    elapsed_seconds = max(0.0, (now - last_request_at).total_seconds())
    return max(0.0, minimum_interval_seconds - elapsed_seconds)
