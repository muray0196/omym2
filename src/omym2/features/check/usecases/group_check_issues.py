"""
Summary: Implements CheckIssue group-by listing.
Why: Lets Web browsing show CheckIssue counts grouped by issue_type with pagination.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.features.check.dto import GroupCheckIssuesRequest
    from omym2.features.check.ports import CheckQueryPorts
    from omym2.shared.pagination import GroupCount, Page


@dataclass(frozen=True, slots=True)
class GroupCheckIssuesUseCase:
    """List CheckIssue groups by issue_type as one keyset page, ordered count DESC then key ASC."""

    ports: CheckQueryPorts

    def execute(self, request: GroupCheckIssuesRequest) -> Page[GroupCount]:
        """Return one page of CheckIssue groups for the requested scope."""
        with self.ports.uow as uow:
            return uow.check_issues.group_page(request.library_id, request.page)
