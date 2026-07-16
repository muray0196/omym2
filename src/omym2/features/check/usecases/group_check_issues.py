"""
Summary: Implements persisted CheckIssue group-by listing.
Why: Lets Web browsing page repository-derived CheckIssue groups.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.features.check.dto import GroupCheckIssuesRequest
    from omym2.features.check.ports import CheckQueryPorts
    from omym2.features.common_ports import CheckIssueGroup
    from omym2.shared.pagination import Page


@dataclass(frozen=True, slots=True)
class GroupCheckIssuesUseCase:
    """List CheckIssue groups as one keyset page."""

    ports: CheckQueryPorts

    def execute(self, request: GroupCheckIssuesRequest) -> Page[CheckIssueGroup]:
        """Return one page of CheckIssue groups for the requested scope."""
        with self.ports.uow as uow:
            return uow.check_issues.group_page(
                request.library_id,
                request.grouping,
                request.page,
                search=request.search,
                issue_type=request.issue_type,
            )
