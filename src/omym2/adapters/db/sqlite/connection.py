"""
Summary: Opens configured SQLite connections.
Why: Keeps SQLite connection setup consistent for migrations and UnitOfWork.
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from omym2.config import SQLITE_CONNECTION_TIMEOUT_SECONDS

if TYPE_CHECKING:
    from os import PathLike


def open_sqlite_connection(database_path: str | PathLike[str]) -> sqlite3.Connection:
    """Open a SQLite connection with adapter-required pragmas enabled.

    Args:
        database_path: Filesystem path to the application database.

    Returns:
        A connection that yields sqlite3.Row values and enforces foreign keys.
    """
    connection = sqlite3.connect(
        database_path,
        timeout=SQLITE_CONNECTION_TIMEOUT_SECONDS,
        isolation_level=None,
    )
    connection.row_factory = sqlite3.Row
    _ = connection.execute("PRAGMA foreign_keys = ON")
    return connection
