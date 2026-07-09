"""
Summary: Implements paged listing of one Run's durable FileEvents.
Why: Lets Web and CLI inspection browse a Run's FileEvents at scale, separately from its header.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.features.history.usecases.get_run_header import RUN_NOT_FOUND_MESSAGE, RunNotFoundError

if TYPE_CHECKING:
    from omym2.domain.models.file_event import FileEvent
    from omym2.features.history.dto import ListRunEventsRequest
    from omym2.features.history.ports import HistoryPorts
    from omym2.shared.pagination import Page


@dataclass(frozen=True, slots=True)
class ListRunEventsUseCase:
    """List one Run's durable FileEvents as one keyset page, ordered (sequence_no, event_id)."""

    ports: HistoryPorts

    def execute(self, request: ListRunEventsRequest) -> Page[FileEvent]:
        """Return one page of FileEvents for the Run, optionally filtered by status.

        Raises RunNotFoundError for an unknown Run ID before querying events.
        """
        with self.ports.uow as uow:
            if uow.runs.get(request.run_id) is None:
                raise RunNotFoundError(RUN_NOT_FOUND_MESSAGE)
            return uow.file_events.query_page(request.run_id, status=request.status, page=request.page)
