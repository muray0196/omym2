"""
Summary: Defines consistency issues reported by check.
Why: Persists each Library's latest findings for cheap inspection.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePath, PureWindowsPath
from typing import TYPE_CHECKING

from omym2.shared.paths import normalize_library_relative_path

if TYPE_CHECKING:
    from omym2.shared.ids import CompanionAssetId, LibraryId, PlanId, TrackId


class CheckIssueType(StrEnum):
    """Supported check issue types."""

    DB_FILE_MISSING = "db_file_missing"
    UNMANAGED_FILE_EXISTS = "unmanaged_file_exists"
    CONTENT_HASH_CHANGED = "content_hash_changed"
    METADATA_HASH_CHANGED = "metadata_hash_changed"
    CURRENT_PATH_DIFFERS_FROM_CANONICAL_PATH = "current_path_differs_from_canonical_path"
    COMPANION_FILE_MISSING = "companion_file_missing"
    COMPANION_CONTENT_HASH_CHANGED = "companion_content_hash_changed"
    COMPANION_CURRENT_PATH_DIFFERS_FROM_CANONICAL_PATH = "companion_current_path_differs_from_canonical_path"
    COMPANION_OWNER_MISSING = "companion_owner_missing"
    UNMANAGED_COMPANION_EXISTS = "unmanaged_companion_exists"
    FAILED_COMPANION_SOURCE_EXISTS = "failed_companion_source_exists"
    UNPROCESSED_FILE_MISSING = "unprocessed_file_missing"
    UNPROCESSED_CONTENT_HASH_CHANGED = "unprocessed_content_hash_changed"
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


# Sentinel keys/labels shared by every CheckIssue grouping derivation (SQL and
# Python alike); their meanings are contracted in docs/contracts/web-api.md.
CHECK_ISSUE_GROUP_UNKNOWN_KEY = "(unknown)"
CHECK_ISSUE_GROUP_ROOT_KEY = "(root)"
CHECK_ISSUE_GROUP_EXTERNAL_KEY = "(external)"
CHECK_ISSUE_GROUP_ARTIST_ALBUM_SEPARATOR = "\x1f"  # unit separator; keeps artist/album keys collision-free
CHECK_ISSUE_GROUP_ARTIST_ALBUM_LABEL_SEPARATOR = " / "
CHECK_ISSUE_GROUP_UNKNOWN_ARTIST_ALBUM_LABEL = "Unknown Artist / Unknown Album"


@dataclass(frozen=True, slots=True)
class CheckIssue:
    """Calculated inconsistency between DB state and filesystem observations."""

    issue_type: CheckIssueType
    library_id: LibraryId
    path: str | None = None
    track_id: TrackId | None = None
    plan_id: PlanId | None = None
    companion_asset_id: CompanionAssetId | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        """Normalize Library-managed paths while allowing external paths."""
        if (
            self.path is not None
            and not PurePath(self.path).is_absolute()
            and not PureWindowsPath(self.path).is_absolute()
        ):
            object.__setattr__(self, "path", normalize_library_relative_path(self.path))
