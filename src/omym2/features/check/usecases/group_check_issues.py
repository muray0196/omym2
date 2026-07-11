"""
Summary: Implements CheckIssue group-by listing.
Why: Lets Web browsing show CheckIssue counts grouped by issue_type with pagination.
"""

from __future__ import annotations

from dataclasses import dataclass
from posixpath import dirname
from typing import TYPE_CHECKING

from omym2.domain.models.check_issue import CheckIssueGrouping, CheckIssueType

if TYPE_CHECKING:
    from omym2.domain.models.check_issue import CheckIssue
    from omym2.features.check.dto import GroupCheckIssuesRequest
    from omym2.features.check.ports import CheckQueryPorts
    from omym2.features.common_ports import CheckIssueGroup
    from omym2.shared.pagination import Page


CHECK_ISSUE_GROUP_UNKNOWN_KEY = "(unknown)"
CHECK_ISSUE_GROUP_ROOT_KEY = "(root)"
CHECK_ISSUE_GROUP_EXTERNAL_KEY = "(external)"
CHECK_ISSUE_GROUP_ARTIST_ALBUM_SEPARATOR = "\x1f"
CHECK_ISSUE_GROUP_ARTIST_ALBUM_LABEL_SEPARATOR = " / "
CHECK_ISSUE_GROUP_UNKNOWN_ARTIST_ALBUM_LABEL = "Unknown Artist / Unknown Album"


@dataclass(frozen=True, slots=True)
class CheckIssueGroupKey:
    """Derived key/label pair for one CheckIssue grouping."""

    key: str
    label: str


def derive_check_issue_group_key(issue: CheckIssue, grouping: CheckIssueGrouping) -> CheckIssueGroupKey:
    """Return the stable group key and display label for one persisted CheckIssue."""
    if grouping is CheckIssueGrouping.ISSUE_TYPE:
        return CheckIssueGroupKey(key=issue.issue_type.value, label=issue.issue_type.value)
    if grouping is CheckIssueGrouping.SEVERITY:
        severity = check_issue_severity(issue.issue_type)
        return CheckIssueGroupKey(key=severity, label=severity)
    if grouping is CheckIssueGrouping.PATH_ROOT:
        path_root = common_path_root_for_check_issue(issue)
        key = CHECK_ISSUE_GROUP_UNKNOWN_KEY if path_root is None else path_root
        return CheckIssueGroupKey(key=key, label=key)
    if grouping is CheckIssueGrouping.ARTIST_ALBUM:
        return _artist_album_group(issue)
    if grouping is CheckIssueGrouping.SUGGESTED_COMMAND:
        return _suggested_command_group(issue.issue_type)
    return CheckIssueGroupKey(key=str(issue.library_id), label=str(issue.library_id))


def check_issue_severity(issue_type: CheckIssueType) -> str:
    """Return the triage severity for one issue type."""
    if issue_type in (CheckIssueType.DB_FILE_MISSING, CheckIssueType.CONTENT_HASH_CHANGED):
        return "error"
    if issue_type is CheckIssueType.LIBRARY_STALE:
        return "info"
    return "warning"


def common_path_root_for_check_issue(issue: CheckIssue) -> str | None:
    """Return the top-level path concentration label without changing stored path identity."""
    if issue.path is None or issue.path == "":
        return None
    if issue.path.startswith("/"):
        return CHECK_ISSUE_GROUP_EXTERNAL_KEY
    parent = dirname(issue.path)
    if parent == "":
        return CHECK_ISSUE_GROUP_ROOT_KEY
    return f"{issue.path.split('/', maxsplit=1)[0]}/"


def _artist_album_group(issue: CheckIssue) -> CheckIssueGroupKey:
    """Group relative paths by their first two directory segments for triage."""
    if issue.path is None or issue.path == "":
        return CheckIssueGroupKey(
            key=CHECK_ISSUE_GROUP_UNKNOWN_KEY,
            label=CHECK_ISSUE_GROUP_UNKNOWN_ARTIST_ALBUM_LABEL,
        )
    if issue.path.startswith("/"):
        return CheckIssueGroupKey(key=CHECK_ISSUE_GROUP_EXTERNAL_KEY, label=CHECK_ISSUE_GROUP_EXTERNAL_KEY)

    directories = [segment for segment in issue.path.split("/")[:-1] if segment]
    if not directories:
        return CheckIssueGroupKey(key=CHECK_ISSUE_GROUP_ROOT_KEY, label=CHECK_ISSUE_GROUP_ROOT_KEY)

    artist = directories[0]
    album = directories[1] if len(directories) > 1 else CHECK_ISSUE_GROUP_ROOT_KEY
    return CheckIssueGroupKey(
        key=f"{artist}{CHECK_ISSUE_GROUP_ARTIST_ALBUM_SEPARATOR}{album}",
        label=f"{artist}{CHECK_ISSUE_GROUP_ARTIST_ALBUM_LABEL_SEPARATOR}{album}",
    )


def _suggested_command_group(issue_type: CheckIssueType) -> CheckIssueGroupKey:
    """Return the normalized command family that is appropriate for an issue type."""
    if issue_type in (
        CheckIssueType.DB_FILE_MISSING,
        CheckIssueType.CONTENT_HASH_CHANGED,
        CheckIssueType.METADATA_HASH_CHANGED,
    ):
        return CheckIssueGroupKey(key="refresh", label="omym2 refresh <file>")
    if issue_type is CheckIssueType.UNMANAGED_FILE_EXISTS:
        return CheckIssueGroupKey(key="add", label="omym2 add <path>")
    if issue_type in (
        CheckIssueType.CURRENT_PATH_DIFFERS_FROM_CANONICAL_PATH,
        CheckIssueType.DUPLICATE_CANDIDATE,
        CheckIssueType.PLAN_SOURCE_CHANGED,
    ):
        return CheckIssueGroupKey(key="organize", label="omym2 organize")
    if issue_type is CheckIssueType.PENDING_FILE_EVENT_EXISTS:
        return CheckIssueGroupKey(key="history", label="omym2 history")
    return CheckIssueGroupKey(key="check", label="omym2 check")


@dataclass(frozen=True, slots=True)
class GroupCheckIssuesUseCase:
    """List CheckIssue groups as one keyset page, ordered count DESC then key ASC."""

    ports: CheckQueryPorts

    def execute(self, request: GroupCheckIssuesRequest) -> Page[CheckIssueGroup]:
        """Return one page of CheckIssue groups for the requested scope."""
        with self.ports.uow as uow:
            return uow.check_issues.group_page(request.library_id, request.grouping, request.page)
