"""
Summary: Mirrors persisted grouping derivations for in-memory test repositories.
Why: Keeps pure fake-only grouping support outside production modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from json import dumps
from pathlib import PurePosixPath, PureWindowsPath
from posixpath import dirname

from omym2.domain.models.check_issue import (
    CHECK_ISSUE_GROUP_ARTIST_ALBUM_LABEL_SEPARATOR,
    CHECK_ISSUE_GROUP_ARTIST_ALBUM_SEPARATOR,
    CHECK_ISSUE_GROUP_EXTERNAL_KEY,
    CHECK_ISSUE_GROUP_ROOT_KEY,
    CHECK_ISSUE_GROUP_UNKNOWN_ARTIST_ALBUM_LABEL,
    CHECK_ISSUE_GROUP_UNKNOWN_KEY,
    CheckIssue,
    CheckIssueGrouping,
    CheckIssueType,
)
from omym2.domain.models.track import (
    TRACK_GROUP_DISC_LABEL_PREFIX,
    TRACK_GROUP_LABEL_SEPARATOR,
    TRACK_GROUP_METADATA_WHITESPACE,
    TRACK_GROUP_UNKNOWN_KEY,
    TRACK_GROUP_UNNUMBERED_DISC_LABEL,
    Track,
    TrackGrouping,
)


@dataclass(frozen=True, slots=True)
class CheckIssueGroupKey:
    """Derived CheckIssue key and label for fake repository grouping."""

    key: str
    label: str


@dataclass(frozen=True, slots=True)
class TrackGroupKey:
    """Derived Track key and label for fake repository grouping."""

    key: str
    label: str


def derive_check_issue_group_key(issue: CheckIssue, grouping: CheckIssueGrouping) -> CheckIssueGroupKey:
    """Return the fake repository's exact CheckIssue group key and label."""
    if grouping is CheckIssueGrouping.ISSUE_TYPE:
        return CheckIssueGroupKey(issue.issue_type.value, issue.issue_type.value)
    if grouping is CheckIssueGrouping.SEVERITY:
        severity = check_issue_severity(issue.issue_type)
        return CheckIssueGroupKey(severity, severity)
    if grouping is CheckIssueGrouping.PATH_ROOT:
        path_root = common_path_root_for_check_issue(issue)
        key = CHECK_ISSUE_GROUP_UNKNOWN_KEY if path_root is None else path_root
        return CheckIssueGroupKey(key, key)
    if grouping is CheckIssueGrouping.ARTIST_ALBUM:
        return _check_artist_album_group(issue)
    if grouping is CheckIssueGrouping.SUGGESTED_COMMAND:
        return _suggested_command_group(issue)
    key = str(issue.library_id)
    return CheckIssueGroupKey(key, key)


def check_issue_severity(issue_type: CheckIssueType) -> str:
    """Return the persisted-query severity mirrored by the fake."""
    if issue_type in {
        CheckIssueType.DB_FILE_MISSING,
        CheckIssueType.CONTENT_HASH_CHANGED,
        CheckIssueType.COMPANION_FILE_MISSING,
        CheckIssueType.COMPANION_CONTENT_HASH_CHANGED,
        CheckIssueType.COMPANION_OWNER_MISSING,
        CheckIssueType.FAILED_COMPANION_SOURCE_EXISTS,
        CheckIssueType.UNPROCESSED_FILE_MISSING,
        CheckIssueType.UNPROCESSED_CONTENT_HASH_CHANGED,
    }:
        return "error"
    if issue_type is CheckIssueType.LIBRARY_STALE:
        return "info"
    return "warning"


def common_path_root_for_check_issue(issue: CheckIssue) -> str | None:
    """Return the fake repository's top-level path concentration label."""
    if issue.path is None or issue.path == "":
        return None
    if _is_external_absolute_path(issue.path):
        return CHECK_ISSUE_GROUP_EXTERNAL_KEY
    if dirname(issue.path) == "":
        return CHECK_ISSUE_GROUP_ROOT_KEY
    return f"{issue.path.split('/', maxsplit=1)[0]}/"


def derive_track_group_key(track: Track, grouping: TrackGrouping) -> TrackGroupKey:
    """Return a Track hierarchy key matching the SQLite repository."""
    artist = _track_artist(track)
    album = _track_album(track)
    if grouping is TrackGrouping.ARTIST:
        return TrackGroupKey(_json_key(artist), artist)
    year = track.metadata.year
    if grouping is TrackGrouping.ALBUM:
        label = album if year is None else f"{album}{TRACK_GROUP_LABEL_SEPARATOR}{year}"
        return TrackGroupKey(_json_key(artist, album, year), label)
    disc = track.metadata.disc_number
    disc_key: int | str = disc if disc is not None and disc > 0 else TRACK_GROUP_UNKNOWN_KEY
    label = (
        TRACK_GROUP_UNNUMBERED_DISC_LABEL
        if disc_key == TRACK_GROUP_UNKNOWN_KEY
        else f"{TRACK_GROUP_DISC_LABEL_PREFIX}{disc_key}"
    )
    return TrackGroupKey(_json_key(artist, album, year, disc_key), label)


def track_group_member_sort_key(track: Track) -> tuple[int, int, str, str]:
    """Return the grouped Track ordering mirrored by the fake."""
    track_number = track.metadata.track_number
    title = track.metadata.title or ""
    if track_number is not None and track_number > 0:
        return (0, track_number, title, str(track.track_id))
    return (1, 0, title, str(track.track_id))


def _check_artist_album_group(issue: CheckIssue) -> CheckIssueGroupKey:
    if issue.path is None or issue.path == "":
        return CheckIssueGroupKey(CHECK_ISSUE_GROUP_UNKNOWN_KEY, CHECK_ISSUE_GROUP_UNKNOWN_ARTIST_ALBUM_LABEL)
    if _is_external_absolute_path(issue.path):
        return CheckIssueGroupKey(CHECK_ISSUE_GROUP_EXTERNAL_KEY, CHECK_ISSUE_GROUP_EXTERNAL_KEY)
    directories = issue.path.split("/")[:-1]
    if not directories:
        return CheckIssueGroupKey(CHECK_ISSUE_GROUP_ROOT_KEY, CHECK_ISSUE_GROUP_ROOT_KEY)
    artist = directories[0]
    album = directories[1] if len(directories) > 1 else CHECK_ISSUE_GROUP_ROOT_KEY
    return CheckIssueGroupKey(
        f"{artist}{CHECK_ISSUE_GROUP_ARTIST_ALBUM_SEPARATOR}{album}",
        f"{artist}{CHECK_ISSUE_GROUP_ARTIST_ALBUM_LABEL_SEPARATOR}{album}",
    )


def _suggested_command_group(issue: CheckIssue) -> CheckIssueGroupKey:  # noqa: PLR0911  # Closed fake catalog.
    issue_type = issue.issue_type
    if issue_type in {
        CheckIssueType.DB_FILE_MISSING,
        CheckIssueType.CONTENT_HASH_CHANGED,
        CheckIssueType.METADATA_HASH_CHANGED,
        CheckIssueType.COMPANION_FILE_MISSING,
        CheckIssueType.COMPANION_CONTENT_HASH_CHANGED,
    }:
        return CheckIssueGroupKey("refresh", "omym2 refresh <file>")
    if issue_type is CheckIssueType.UNMANAGED_FILE_EXISTS:
        return CheckIssueGroupKey("add", "omym2 add <path>")
    if issue_type is CheckIssueType.FAILED_COMPANION_SOURCE_EXISTS:
        if issue.detail == "add":
            return CheckIssueGroupKey("add", "omym2 add <path>")
        if issue.detail == "organize":
            return CheckIssueGroupKey("organize", "omym2 organize")
        return CheckIssueGroupKey("check", "omym2 check")
    if issue_type in {
        CheckIssueType.CURRENT_PATH_DIFFERS_FROM_CANONICAL_PATH,
        CheckIssueType.COMPANION_CURRENT_PATH_DIFFERS_FROM_CANONICAL_PATH,
        CheckIssueType.COMPANION_OWNER_MISSING,
        CheckIssueType.UNMANAGED_COMPANION_EXISTS,
        CheckIssueType.DUPLICATE_CANDIDATE,
        CheckIssueType.PLAN_SOURCE_CHANGED,
    }:
        return CheckIssueGroupKey("organize", "omym2 organize")
    if issue_type in {
        CheckIssueType.PENDING_FILE_EVENT_EXISTS,
        CheckIssueType.UNPROCESSED_FILE_MISSING,
        CheckIssueType.UNPROCESSED_CONTENT_HASH_CHANGED,
    }:
        return CheckIssueGroupKey("history", "omym2 history")
    return CheckIssueGroupKey("check", "omym2 check")


def _is_external_absolute_path(path: str) -> bool:
    return PurePosixPath(path).is_absolute() or PureWindowsPath(path).is_absolute()


def _track_artist(track: Track) -> str:
    for candidate in (track.metadata.album_artist, track.metadata.artist):
        if candidate is not None and candidate.strip(TRACK_GROUP_METADATA_WHITESPACE) != "":
            return candidate
    return TRACK_GROUP_UNKNOWN_KEY


def _track_album(track: Track) -> str:
    album = track.metadata.album
    if album is None or album.strip(TRACK_GROUP_METADATA_WHITESPACE) == "":
        return TRACK_GROUP_UNKNOWN_KEY
    return album


def _json_key(*values: int | str | None) -> str:
    return dumps(values, ensure_ascii=False, separators=(",", ":"))
