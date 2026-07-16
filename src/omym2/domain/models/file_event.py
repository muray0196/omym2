"""
Summary: Defines durable Library file mutation events.
Why: Preserves evidence before and after apply mutates managed files.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePath
from typing import TYPE_CHECKING

from omym2.shared.paths import normalize_library_relative_path
from omym2.shared.time import as_utc

if TYPE_CHECKING:
    from datetime import datetime

    from omym2.shared.ids import ActionId, CompanionAssetId, EventId, LibraryId, RunId


class FileEventType(StrEnum):
    """Supported durable operation event types."""

    MOVE_FILE = "move_file"
    MOVE_LYRICS_FILE = "move_lyrics_file"
    MOVE_ARTWORK_FILE = "move_artwork_file"
    MOVE_UNPROCESSED_FILE = "move_unprocessed_file"


class FileEventStatus(StrEnum):
    """Supported durable operation event statuses."""

    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class FileEvent:
    """Durable operation log entry for one Library-managed file mutation."""

    event_id: EventId
    library_id: LibraryId
    run_id: RunId
    plan_action_id: ActionId
    event_type: FileEventType
    source_path: str
    target_path: str
    status: FileEventStatus
    started_at: datetime
    completed_at: datetime | None
    error_code: str | None
    error_message: str | None
    sequence_no: int
    companion_asset_id: CompanionAssetId | None = None

    def __post_init__(self) -> None:
        """Normalize path references and timestamps for durable history."""
        if not PurePath(self.source_path).is_absolute():
            object.__setattr__(self, "source_path", normalize_library_relative_path(self.source_path))
        if not PurePath(self.target_path).is_absolute():
            object.__setattr__(self, "target_path", normalize_library_relative_path(self.target_path))
        object.__setattr__(self, "started_at", as_utc(self.started_at))
        if self.completed_at is not None:
            object.__setattr__(self, "completed_at", as_utc(self.completed_at))

    def mark_succeeded(self, completed_at: datetime) -> FileEvent:
        """Return this event as a confirmed successful mutation."""
        return self._with_result(FileEventStatus.SUCCEEDED, completed_at, None, None)

    def mark_failed(self, completed_at: datetime, error_code: str, error_message: str) -> FileEvent:
        """Return this event as a failed or unconfirmed mutation."""
        return self._with_result(FileEventStatus.FAILED, completed_at, error_code, error_message)

    def _with_result(
        self,
        status: FileEventStatus,
        completed_at: datetime,
        error_code: str | None,
        error_message: str | None,
    ) -> FileEvent:
        return FileEvent(
            event_id=self.event_id,
            library_id=self.library_id,
            run_id=self.run_id,
            plan_action_id=self.plan_action_id,
            event_type=self.event_type,
            source_path=self.source_path,
            target_path=self.target_path,
            status=status,
            started_at=self.started_at,
            completed_at=completed_at,
            error_code=error_code,
            error_message=error_message,
            sequence_no=self.sequence_no,
            companion_asset_id=self.companion_asset_id,
        )
