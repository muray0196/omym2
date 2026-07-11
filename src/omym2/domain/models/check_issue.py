"""
Summary: Defines consistency issues reported by check.
Why: Findings are persisted as one Library's latest check run (see CheckRun) so
browsing reads stored state instead of recomputing issues on every request.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePath
from typing import TYPE_CHECKING

from omym2.shared.paths import normalize_library_relative_path

if TYPE_CHECKING:
    from omym2.shared.ids import LibraryId, PlanId, TrackId


class CheckIssueType(StrEnum):
    """Supported check issue types."""

    DB_FILE_MISSING = "db_file_missing"
    UNMANAGED_FILE_EXISTS = "unmanaged_file_exists"
    CONTENT_HASH_CHANGED = "content_hash_changed"
    METADATA_HASH_CHANGED = "metadata_hash_changed"
    CURRENT_PATH_DIFFERS_FROM_CANONICAL_PATH = "current_path_differs_from_canonical_path"
    DUPLICATE_CANDIDATE = "duplicate_candidate"
    PLAN_SOURCE_CHANGED = "plan_source_changed"
    PENDING_FILE_EVENT_EXISTS = "pending_file_event_exists"
    LIBRARY_UNREGISTERED = "library_unregistered"
    LIBRARY_STALE = "library_stale"
    LIBRARY_BLOCKED = "library_blocked"


class CheckIssueGrouping(StrEnum):
    """Supported group-by keys for persisted CheckIssue browsing."""

    ISSUE_TYPE = "issue_type"
    SEVERITY = "severity"
    PATH_ROOT = "path_root"
    ARTIST_ALBUM = "artist_album"
    SUGGESTED_COMMAND = "suggested_command"
    LIBRARY_ID = "library_id"


@dataclass(frozen=True, slots=True)
class CheckIssue:
    """Calculated inconsistency between DB state and filesystem observations."""

    issue_type: CheckIssueType
    library_id: LibraryId
    path: str | None = None
    track_id: TrackId | None = None
    plan_id: PlanId | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        """Normalize Library-managed paths while allowing external paths."""
        if self.path is not None and not PurePath(self.path).is_absolute():
            object.__setattr__(self, "path", normalize_library_relative_path(self.path))
