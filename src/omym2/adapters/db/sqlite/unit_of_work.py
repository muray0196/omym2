"""
Summary: Implements SQLite transactions with usecase-scoped connection reuse.
Why: Preserves durable boundaries without reconnecting for each apply step.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Self

from omym2.adapters.db.sqlite.connection import open_sqlite_connection
from omym2.adapters.db.sqlite.migration_runner import ensure_database_migrated
from omym2.adapters.db.sqlite.repositories import (
    SQLiteAcceptedArtistNameRepository,
    SQLiteCheckIssueRepository,
    SQLiteCheckRunRepository,
    SQLiteFileEventRepository,
    SQLiteLibraryRepository,
    SQLiteOperationRepository,
    SQLitePlanActionRepository,
    SQLitePlanRepository,
    SQLiteRunRepository,
    SQLiteTrackRepository,
)
from omym2.domain.models.plan import PlanStatus

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Generator
    from os import PathLike
    from types import TracebackType

    from omym2.domain.models.operation import Operation
    from omym2.domain.models.run import Run
    from omym2.shared.ids import PlanId

UNIT_OF_WORK_ALREADY_OPEN_MESSAGE = "SQLiteUnitOfWork is already open."
UNIT_OF_WORK_NOT_OPEN_MESSAGE = "SQLiteUnitOfWork must be entered before use."


@dataclass(slots=True)
class SQLiteUnitOfWork:
    """SQLite UnitOfWork implementation with lazy database creation."""

    database_path: str | PathLike[str]
    _connection: sqlite3.Connection | None = field(default=None, init=False)
    _accepted_artist_names: SQLiteAcceptedArtistNameRepository | None = field(default=None, init=False)
    _libraries: SQLiteLibraryRepository | None = field(default=None, init=False)
    _check_runs: SQLiteCheckRunRepository | None = field(default=None, init=False)
    _check_issues: SQLiteCheckIssueRepository | None = field(default=None, init=False)
    _tracks: SQLiteTrackRepository | None = field(default=None, init=False)
    _plans: SQLitePlanRepository | None = field(default=None, init=False)
    _plan_actions: SQLitePlanActionRepository | None = field(default=None, init=False)
    _runs: SQLiteRunRepository | None = field(default=None, init=False)
    _file_events: SQLiteFileEventRepository | None = field(default=None, init=False)
    _operations: SQLiteOperationRepository | None = field(default=None, init=False)
    _is_completed: bool = field(default=True, init=False)
    _is_transaction_open: bool = field(default=False, init=False)
    _is_usecase_scope_open: bool = field(default=False, init=False)

    @contextmanager
    def usecase_scope(self) -> Generator[None]:
        """Keep one lazy SQLite connection across this usecase's transactions."""
        if self._is_usecase_scope_open or self._is_transaction_open or self._connection is not None:
            raise RuntimeError(UNIT_OF_WORK_ALREADY_OPEN_MESSAGE)

        self._is_usecase_scope_open = True
        try:
            yield
        finally:
            self._is_usecase_scope_open = False
            self._close_connection()

    @property
    def accepted_artist_names(self) -> SQLiteAcceptedArtistNameRepository:
        """Repository for sticky accepted provider artist names."""
        if self._accepted_artist_names is None:
            raise RuntimeError(UNIT_OF_WORK_NOT_OPEN_MESSAGE)
        return self._accepted_artist_names

    @property
    def libraries(self) -> SQLiteLibraryRepository:
        """Repository for Library identity and registration state."""
        if self._libraries is None:
            raise RuntimeError(UNIT_OF_WORK_NOT_OPEN_MESSAGE)
        return self._libraries

    @property
    def check_runs(self) -> SQLiteCheckRunRepository:
        """Repository for each Library's latest completed check run."""
        if self._check_runs is None:
            raise RuntimeError(UNIT_OF_WORK_NOT_OPEN_MESSAGE)
        return self._check_runs

    @property
    def check_issues(self) -> SQLiteCheckIssueRepository:
        """Repository for the latest check run's findings."""
        if self._check_issues is None:
            raise RuntimeError(UNIT_OF_WORK_NOT_OPEN_MESSAGE)
        return self._check_issues

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

    @property
    def operations(self) -> SQLiteOperationRepository:
        """Repository for durable background request lifecycle records."""
        if self._operations is None:
            raise RuntimeError(UNIT_OF_WORK_NOT_OPEN_MESSAGE)
        return self._operations

    def __enter__(self) -> Self:
        """Open the SQLite transaction boundary."""
        if self._is_transaction_open:
            raise RuntimeError(UNIT_OF_WORK_ALREADY_OPEN_MESSAGE)

        connection = self._connection
        if connection is None:
            ensure_database_migrated(self.database_path)
            connection = open_sqlite_connection(self.database_path)
            self._connection = connection
        try:
            _ = connection.execute("BEGIN")
        except BaseException:
            self._close_connection()
            raise

        self._accepted_artist_names = SQLiteAcceptedArtistNameRepository(connection)
        self._libraries = SQLiteLibraryRepository(connection)
        self._check_runs = SQLiteCheckRunRepository(connection)
        self._check_issues = SQLiteCheckIssueRepository(connection)
        self._tracks = SQLiteTrackRepository(connection)
        self._plans = SQLitePlanRepository(connection)
        self._plan_actions = SQLitePlanActionRepository(connection)
        self._runs = SQLiteRunRepository(connection)
        self._file_events = SQLiteFileEventRepository(connection)
        self._operations = SQLiteOperationRepository(connection)
        self._is_completed = False
        self._is_transaction_open = True
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
        if connection is None or not self._is_transaction_open:
            return None

        try:
            if not self._is_completed:
                connection.rollback()
        finally:
            self._reset_transaction()
            if not self._is_usecase_scope_open:
                self._close_connection()

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

    def claim_apply(self, plan_id: PlanId, run: Run, operation: Operation) -> bool:
        """Stage one compare-and-set Apply claim and its durable associations."""
        claimed = self.plans.compare_and_set_status(plan_id, PlanStatus.READY, PlanStatus.APPLYING)
        if not claimed:
            return False
        self.runs.save(run)
        self.operations.save(operation)
        return True

    def _require_connection(self) -> sqlite3.Connection:
        connection = self._connection
        if connection is None or not self._is_transaction_open:
            raise RuntimeError(UNIT_OF_WORK_NOT_OPEN_MESSAGE)
        return connection

    def _reset_transaction(self) -> None:
        self._accepted_artist_names = None
        self._libraries = None
        self._check_runs = None
        self._check_issues = None
        self._tracks = None
        self._plans = None
        self._plan_actions = None
        self._runs = None
        self._file_events = None
        self._operations = None
        self._is_completed = True
        self._is_transaction_open = False

    def _close_connection(self) -> None:
        connection = self._connection
        if connection is None:
            return

        try:
            if self._is_transaction_open and not self._is_completed:
                connection.rollback()
        finally:
            self._reset_transaction()
            self._connection = None
            connection.close()
