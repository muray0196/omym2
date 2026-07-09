"""
Summary: Implements Run listing as one keyset page.
Why: Lets CLI and Web inspection browse apply attempts at scale.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.run import Run
    from omym2.features.history.dto import ListRunsRequest
    from omym2.features.history.ports import HistoryPorts
    from omym2.shared.pagination import Page


@dataclass(frozen=True, slots=True)
class ListRunsUseCase:
    """List apply Runs as one keyset page, newest first."""

    ports: HistoryPorts

    def execute(self, request: ListRunsRequest) -> Page[Run]:
        """Return one page of Runs for the requested scope and status filter.

        Ordered (started_at DESC, run_id DESC). Fetch is per-Library when
        request.library_id is set, otherwise scoped across every known
        Library.
        """
        with self.ports.uow as uow:
            return uow.runs.query_page(request.library_id, status=request.status, page=request.page)
