"""
Summary: Reads persisted Libraries for Bootstrap.
Why: Keeps SQLite construction and failures behind a feature-owned port.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.features.bootstrap.ports import LibrarySnapshotUnavailableError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from os import PathLike

    from omym2.domain.models.library import Library


@dataclass(frozen=True, slots=True)
class SQLiteLibrarySnapshotReader:
    """Read all Library headers through the SQLite UnitOfWork."""

    database_path: str | PathLike[str]

    def list_libraries(self) -> Sequence[Library]:
        """Return persisted Libraries or one stable storage failure."""
        try:
            with SQLiteUnitOfWork(self.database_path) as uow:
                return tuple(uow.libraries.list_all())
        except (OSError, sqlite3.DatabaseError) as exc:
            raise LibrarySnapshotUnavailableError from exc
