"""
Summary: Tests SQLite connection pragma setup.
Why: Verifies WAL journal mode and explicit FULL synchronous durability.
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, cast

from omym2.adapters.db.sqlite.connection import open_sqlite_connection

if TYPE_CHECKING:
    from os import PathLike
    from pathlib import Path

    import pytest

SYNCHRONOUS_FULL = 2


def test_open_sqlite_connection_enables_wal(tmp_path: Path) -> None:
    """Opened connections use WAL journal mode."""
    connection = open_sqlite_connection(tmp_path / "app.sqlite3")

    row = cast("tuple[object, ...] | None", connection.execute("PRAGMA journal_mode").fetchone())
    connection.close()

    assert row is not None
    assert row[0] == "wal"


def test_open_sqlite_connection_sets_synchronous_full(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Opened connections override a WAL connection's NORMAL synchronous level."""
    real_connect = sqlite3.connect

    def _connect_with_normal_synchronous(
        database_path: str | PathLike[str],
        *,
        timeout: float,
        isolation_level: None,
    ) -> sqlite3.Connection:
        connection = real_connect(
            database_path,
            timeout=timeout,
            isolation_level=isolation_level,
        )
        _ = connection.execute("PRAGMA journal_mode = WAL")
        _ = connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    monkeypatch.setattr(sqlite3, "connect", _connect_with_normal_synchronous)
    connection = open_sqlite_connection(tmp_path / "app.sqlite3")

    row = cast("tuple[object, ...] | None", connection.execute("PRAGMA synchronous").fetchone())
    connection.close()

    assert row is not None
    assert row[0] == SYNCHRONOUS_FULL
