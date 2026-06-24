"""
Summary: Implements SQLite transaction-scoped UnitOfWork.
Why: Gives usecases one durable repository boundary per interaction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Self

from omym2.adapters.db.sqlite.connection import open_sqlite_connection
from omym2.adapters.db.sqlite.migration_runner import migrate_database
from omym2.adapters.db.sqlite.repositories import (
    SQLiteFileEventRepository,
    SQLiteLibraryRepository,
    SQLitePlanActionRepository,
    SQLitePlanRepository,
    SQLiteRunRepository,
    SQLiteTrackRepository,
)

if TYPE_CHECKING:
    import sqlite3
    from os import PathLike
    from types import TracebackType

UNIT_OF_WORK_ALREADY_OPEN_MESSAGE = "SQLiteUnitOfWork is already open."
UNIT_OF_WORK_NOT_OPEN_MESSAGE = "SQLiteUnitOfWork must be entered before use."


@dataclass(slots=True)
class SQLiteUnitOfWork:
    """SQLite UnitOfWork implementation with lazy database creation."""

    database_path: str | PathLike[str]
    _connection: sqlite3.Connection | None = field(default=None, init=False)
    _libraries: SQLiteLibraryRepository | None = field(default=None, init=False)
    _tracks: SQLiteTrackRepository | None = field(default=None, init=False)
    _plans: SQLitePlanRepository | None = field(default=None, init=False)
    _plan_actions: SQLitePlanActionRepository | None = field(default=None, init=False)
    _runs: SQLiteRunRepository | None = field(default=None, init=False)
    _file_events: SQLiteFileEventRepository | None = field(default=None, init=False)
    _is_completed: bool = field(default=True, init=False)

    @property
    def libraries(self) -> SQLiteLibraryRepository:
        """Repository for Library identity and registration state."""
        if self._libraries is None:
            raise RuntimeError(UNIT_OF_WORK_NOT_OPEN_MESSAGE)
        return self._libraries

    @property
    def tracks(self) -> SQLiteTrackRepository:
        """Repository for managed Track state."""
        if self._tracks is None:
            raise RuntimeError(UNIT_OF_WORK_NOT_OPEN_MESSAGE)
        return self._tracks

    @property
    def plans(self) -> SQLitePlanRepository:
        """Repository for reviewed Plans."""
        if self._plans is None:
            raise RuntimeError(UNIT_OF_WORK_NOT_OPEN_MESSAGE)
        return self._plans

    @property
    def plan_actions(self) -> SQLitePlanActionRepository:
        """Repository for recorded PlanActions."""
        if self._plan_actions is None:
            raise RuntimeError(UNIT_OF_WORK_NOT_OPEN_MESSAGE)
        return self._plan_actions

    @property
    def runs(self) -> SQLiteRunRepository:
        """Repository for apply Runs."""
        if self._runs is None:
            raise RuntimeError(UNIT_OF_WORK_NOT_OPEN_MESSAGE)
        return self._runs

    @property
    def file_events(self) -> SQLiteFileEventRepository:
        """Repository for durable filesystem operation logs."""
        if self._file_events is None:
            raise RuntimeError(UNIT_OF_WORK_NOT_OPEN_MESSAGE)
        return self._file_events

    def __enter__(self) -> Self:
        """Open the SQLite transaction boundary."""
        if self._connection is not None:
            raise RuntimeError(UNIT_OF_WORK_ALREADY_OPEN_MESSAGE)

        migrate_database(self.database_path)
        connection = open_sqlite_connection(self.database_path)
        _ = connection.execute("BEGIN")

        self._connection = connection
        self._libraries = SQLiteLibraryRepository(connection)
        self._tracks = SQLiteTrackRepository(connection)
        self._plans = SQLitePlanRepository(connection)
        self._plan_actions = SQLitePlanActionRepository(connection)
        self._runs = SQLiteRunRepository(connection)
        self._file_events = SQLiteFileEventRepository(connection)
        self._is_completed = False
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        """Close the transaction, rolling back any uncommitted changes."""
        del exc, tb
        connection = self._connection
        if connection is None:
            return None

        try:
            if not self._is_completed:
                connection.rollback()
        finally:
            self._connection = None
            self._libraries = None
            self._tracks = None
            self._plans = None
            self._plan_actions = None
            self._runs = None
            self._file_events = None
            self._is_completed = True
            connection.close()

        return None

    def commit(self) -> None:
        """Commit the current UnitOfWork transaction."""
        connection = self._require_connection()
        if not self._is_completed:
            connection.commit()
            self._is_completed = True

    def rollback(self) -> None:
        """Rollback the current UnitOfWork transaction."""
        connection = self._require_connection()
        if not self._is_completed:
            connection.rollback()
            self._is_completed = True

    def _require_connection(self) -> sqlite3.Connection:
        connection = self._connection
        if connection is None:
            raise RuntimeError(UNIT_OF_WORK_NOT_OPEN_MESSAGE)
        return connection
