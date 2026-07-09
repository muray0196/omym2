"""
Summary: Implements CheckIssue issue_type facet counts.
Why: Lets Web browsing show issue_type value/count breakdowns without pagination.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.features.check.dto import CheckIssueFacetsResult
from omym2.features.check.usecases.list_check_issues import checked_at_for_scope

if TYPE_CHECKING:
    from omym2.features.check.dto import CheckIssueFacetsRequest
    from omym2.features.check.ports import CheckQueryPorts


@dataclass(frozen=True, slots=True)
class GetCheckIssueFacetsUseCase:
    """Return CheckIssue issue_type facet counts for the requested Library scope."""

    ports: CheckQueryPorts

    def execute(self, request: CheckIssueFacetsRequest) -> CheckIssueFacetsResult:
        """Return issue_type facets plus the total CheckIssue count and the scope's checked_at.

        `total` is the sum of facet counts: every CheckIssue has exactly one issue_type, so
        the facet breakdown always partitions the full scope.
        """
        with self.ports.uow as uow:
            facets = uow.check_issues.issue_type_facets(request.library_id)
            checked_at = checked_at_for_scope(uow, request.library_id)
        return CheckIssueFacetsResult(
            facets=facets,
            total=sum(facet.count for facet in facets),
            checked_at=checked_at,
        )
