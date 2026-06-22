"""
Summary: Applies packaged SQLite schema migrations.
Why: Creates and upgrades the internal database lazily under OMYM2 data storage.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

from omym2.adapters.db.sqlite.connection import open_sqlite_connection
from omym2.config import SQLITE_MIGRATION_FILE_ENCODING, SQLITE_MIGRATION_FILE_EXTENSION
from omym2.shared.time import utc_now

MIGRATIONS_PACKAGE: Final = "omym2.adapters.db.sqlite.migrations"
INVALID_MIGRATION_NAME_MESSAGE: Final = "Expected SQLite migration name text."
INCOMPLETE_MIGRATION_STATEMENT_MESSAGE: Final = "SQLite migration contains an incomplete SQL statement."

if TYPE_CHECKING:
    from importlib.resources.abc import Traversable
    from os import PathLike

CREATE_MIGRATIONS_TABLE_SQL: Final = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_name TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
)
"""
SELECT_APPLIED_MIGRATIONS_SQL: Final = """
SELECT migration_name
FROM schema_migrations
ORDER BY migration_name
"""
INSERT_MIGRATION_SQL: Final = """
INSERT INTO schema_migrations (migration_name, applied_at)
VALUES (?, ?)
"""


@dataclass(frozen=True, slots=True)
class SQLiteMigration:
    """One packaged SQLite migration script."""

    name: str
    sql: str


def migrate_database(database_path: str | PathLike[str]) -> None:
    """Create the database path and apply any pending migrations.

    Args:
        database_path: Filesystem path to the SQLite database file.
    """
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    connection = open_sqlite_connection(database_path)
    try:
        _ = connection.execute(CREATE_MIGRATIONS_TABLE_SQL)
        applied_migrations = _applied_migration_names(connection)
        for migration in load_packaged_migrations():
            if migration.name not in applied_migrations:
                _apply_migration(connection, migration)
    finally:
        connection.close()


def load_packaged_migrations() -> tuple[SQLiteMigration, ...]:
    """Return migration resources in deterministic filename order."""
    migration_root = resources.files(MIGRATIONS_PACKAGE)
    migration_files: list[Traversable] = sorted(
        (resource for resource in migration_root.iterdir() if resource.name.endswith(SQLITE_MIGRATION_FILE_EXTENSION)),
        key=lambda resource: resource.name,
    )
    return tuple(
        SQLiteMigration(
            name=resource.name,
            sql=resource.read_text(encoding=SQLITE_MIGRATION_FILE_ENCODING),
        )
        for resource in migration_files
    )


def _applied_migration_names(connection: sqlite3.Connection) -> set[str]:
    raw_rows = cast("list[object]", connection.execute(SELECT_APPLIED_MIGRATIONS_SQL).fetchall())
    rows = tuple(cast("sqlite3.Row", row) for row in raw_rows)
    return {_migration_name_from_row(row) for row in rows}


def _apply_migration(connection: sqlite3.Connection, migration: SQLiteMigration) -> None:
    # The schema script and migration marker belong in one transaction so a
    # partially applied migration is not recorded as complete.
    _ = connection.execute("BEGIN")
    try:
        _execute_migration_script(connection, migration.sql)
        _ = connection.execute(
            INSERT_MIGRATION_SQL,
            (migration.name, utc_now().isoformat()),
        )
    except sqlite3.DatabaseError:
        connection.rollback()
        raise
    connection.commit()


def _execute_migration_script(connection: sqlite3.Connection, sql: str) -> None:
    statement_lines: list[str] = []
    for line in sql.splitlines(keepends=True):
        statement_lines.append(line)
        statement = "".join(statement_lines)
        if sqlite3.complete_statement(statement):
            _ = connection.execute(statement)
            statement_lines.clear()

    if "".join(statement_lines).strip():
        raise sqlite3.DatabaseError(INCOMPLETE_MIGRATION_STATEMENT_MESSAGE)


def _migration_name_from_row(row: sqlite3.Row) -> str:
    value = cast("object", row["migration_name"])
    if isinstance(value, str):
        return value
    raise TypeError(INVALID_MIGRATION_NAME_MESSAGE)
