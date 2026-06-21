"""
Summary: Defines history feature request and response data.
Why: Gives history usecases stable contracts before persistence exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.file_event import FileEvent
    from omym2.domain.models.run import Run
    from omym2.shared.ids import LibraryId, RunId


@dataclass(frozen=True, slots=True)
class ListRunsRequest:
    """Request to list Runs for a Library or the selected default Library."""

    library_id: LibraryId | None = None


@dataclass(frozen=True, slots=True)
class GetRunDetailRequest:
    """Request to load one Run with its durable file events."""

    run_id: RunId


@dataclass(frozen=True, slots=True)
class RunDetail:
    """Run detail response with events in sequence order."""

    run: Run
    file_events: tuple[FileEvent, ...]
