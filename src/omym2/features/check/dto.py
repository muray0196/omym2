"""
Summary: Defines check feature request and response data.
Why: Gives check usecases stable contracts for both recompute-and-persist and read-only browsing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from omym2.domain.models.check_issue import CheckIssueGrouping
from omym2.shared.pagination import PageRequest

if TYPE_CHECKING:
    from datetime import datetime

    from omym2.domain.models.check_issue import CheckIssue, CheckIssueType
    from omym2.shared.ids import LibraryId
    from omym2.shared.pagination import FacetValue, Page


@dataclass(frozen=True, slots=True)
class CheckLibraryRequest:
    """Request to recompute and persist check findings for one Library or every known Library."""

    trust_stat: bool
    library_id: LibraryId | None = None


@dataclass(frozen=True, slots=True)
class CheckLibraryResult:
    """Findings from one recompute-and-persist check run, plus when it ran."""

    issues: tuple[CheckIssue, ...]
    checked_at: datetime


@dataclass(frozen=True, slots=True)
class ListCheckIssuesRequest:
    """Request one keyset page of persisted CheckIssues for a Library or every known Library.

    `grouping` and `group_key` are an optional drill-down pair. When both are
    supplied, they select one server-derived issue group while retaining the
    normal issue-type filter and keyset pagination.
    """

    library_id: LibraryId | None = None
    search: str | None = None
    issue_type: CheckIssueType | None = None
    grouping: CheckIssueGrouping | None = None
    group_key: str | None = None
    page: PageRequest = field(default_factory=PageRequest)


@dataclass(frozen=True, slots=True)
class ListCheckIssuesResult:
    """One page of persisted CheckIssues plus the scope's checked_at."""

    page: Page[CheckIssue]
    checked_at: datetime | None


@dataclass(frozen=True, slots=True)
class CheckIssueFacetsRequest:
    """Request CheckIssue issue_type facet counts within a Library/search scope."""

    library_id: LibraryId | None = None
    search: str | None = None


@dataclass(frozen=True, slots=True)
class CheckIssueFacetsResult:
    """CheckIssue issue_type facet counts plus the total count and the scope's checked_at."""

    facets: tuple[FacetValue, ...]
    total: int
    checked_at: datetime | None


@dataclass(frozen=True, slots=True)
class GroupCheckIssuesRequest:
    """Request one keyset page of CheckIssue groups for a Library or every known Library."""

    library_id: LibraryId | None = None
    search: str | None = None
    issue_type: CheckIssueType | None = None
    grouping: CheckIssueGrouping = CheckIssueGrouping.ISSUE_TYPE
    page: PageRequest = field(default_factory=PageRequest)
