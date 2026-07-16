"""
Summary: Defines typed Web resources for persisted Check inspection.
Why: Keeps Health reads separate from filesystem recomputation.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003  # Pydantic resolves timestamp schema types at runtime.
from uuid import UUID  # noqa: TC003  # Pydantic resolves UUID schema types at runtime.

from omym2.adapters.web.schemas.api_errors import ApiModel
from omym2.adapters.web.schemas.browsing import (
    FacetValueResource,  # noqa: TC001  # Pydantic resolves nested schema types at runtime.
    NonNegativeCount,  # noqa: TC001  # Pydantic resolves constrained alias at runtime.
    PageInfo,  # noqa: TC001  # Pydantic resolves nested schema types at runtime.
)
from omym2.domain.models.check_issue import (  # noqa: TC001  # Pydantic resolves enum schema types at runtime.
    CheckIssueGrouping,
    CheckIssueType,
)


class CheckIssueResource(ApiModel):
    """One persisted finding from the latest Check for its Library."""

    issue_type: CheckIssueType
    library_id: UUID
    path: str | None
    track_id: UUID | None
    plan_id: UUID | None
    companion_asset_id: UUID | None
    detail: str | None


class CheckIssuesData(ApiModel):
    """One persisted CheckIssue page plus freshness evidence."""

    items: tuple[CheckIssueResource, ...]
    page: PageInfo
    checked_at: datetime | None


class CheckIssueFacetSets(ApiModel):
    """CheckIssue type facets."""

    issue_type: tuple[FacetValueResource[CheckIssueType], ...]


class CheckIssueFacetsData(ApiModel):
    """CheckIssue facets, matching total, and freshness evidence."""

    facets: CheckIssueFacetSets
    total: NonNegativeCount
    checked_at: datetime | None


class CheckIssueGroupResource(ApiModel):
    """One CheckIssue group with its most common non-null path root."""

    key: str
    label: str
    count: NonNegativeCount
    common_path_root: str | None


class CheckIssueGroupsData(ApiModel):
    """One page of persisted CheckIssue groups."""

    group_by: CheckIssueGrouping
    items: tuple[CheckIssueGroupResource, ...]
    page: PageInfo
