"""
Summary: Tests SQLite connection pragma setup.
Why: Verifies WAL journal mode and FULL synchronous durability defaults.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from omym2.adapters.db.sqlite.connection import open_sqlite_connection

if TYPE_CHECKING:
    from pathlib import Path

SYNCHRONOUS_FULL = 2


def test_open_sqlite_connection_enables_wal(tmp_path: Path) -> None:
    """Opened connections use WAL journal mode."""
    connection = open_sqlite_connection(tmp_path / "app.sqlite3")

    row = cast("tuple[object, ...] | None", connection.execute("PRAGMA journal_mode").fetchone())
    connection.close()

    assert row is not None
    assert row[0] == "wal"


def test_open_sqlite_connection_keeps_synchronous_full(tmp_path: Path) -> None:
    """Opened connections keep the default FULL synchronous level."""
    connection = open_sqlite_connection(tmp_path / "app.sqlite3")

    row = cast("tuple[object, ...] | None", connection.execute("PRAGMA synchronous").fetchone())
    connection.close()

    assert row is not None
    assert row[0] == SYNCHRONOUS_FULL
