"""
Summary: Implements paged listing of persisted CheckIssues.
Why: Lets Web/CLI browsing read the latest check findings without recomputing them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.features.check.dto import ListCheckIssuesResult

if TYPE_CHECKING:
    from datetime import datetime

    from omym2.features.check.dto import ListCheckIssuesRequest
    from omym2.features.check.ports import CheckQueryPorts
    from omym2.features.common_ports import UnitOfWork
    from omym2.shared.ids import LibraryId


GROUP_FILTER_PAIRING_MESSAGE = "grouping and group_key must be provided together."


@dataclass(frozen=True, slots=True)
class ListCheckIssuesUseCase:
    """List persisted CheckIssues as one keyset page, ordered issue_seq ASC."""

    ports: CheckQueryPorts

    def execute(self, request: ListCheckIssuesRequest) -> ListCheckIssuesResult:
        """Return one page of CheckIssues plus the requested scope's checked_at."""
        if (request.grouping is None) != (request.group_key is None):
            raise ValueError(GROUP_FILTER_PAIRING_MESSAGE)
        with self.ports.uow as uow:
            page = uow.check_issues.query_page(
                request.library_id,
                search=request.search,
                issue_type=request.issue_type,
                grouping=request.grouping,
                group_key=request.group_key,
                page=request.page,
            )
            checked_at = checked_at_for_scope(uow, request.library_id)
        return ListCheckIssuesResult(page=page, checked_at=checked_at)


def checked_at_for_scope(uow: UnitOfWork, library_id: LibraryId | None) -> datetime | None:
    """Resolve checked_at for one Library or the aggregate scope across every Library.

    A specific `library_id` resolves to that Library's latest check run, or `None` if it
    has never been checked. The aggregate scope (`library_id=None`) resolves to the
    minimum checked_at across every Library that has a check run (staleness-conservative),
    or `None` if no Library has ever been checked.
    """
    if library_id is not None:
        check_run = uow.check_runs.latest(library_id)
        return None if check_run is None else check_run.checked_at
    return uow.check_runs.earliest_checked_at()
