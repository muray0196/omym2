"""
Summary: Provides deterministic runtime fakes for feature tests.
Why: Keeps usecase tests independent from wall-clock time and random IDs.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from omym2.shared.ids import ActionId, EventId, LibraryId, PlanId, RunId, TrackId

EMPTY_SEQUENCE_MESSAGE = "No deterministic IDs remain for this type."


@dataclass(frozen=True, slots=True)
class FixedClock:
    """Clock fake that always returns the same timestamp."""

    current_time: datetime

    def now(self) -> datetime:
        """Return the fixed timestamp."""
        return self.current_time


@dataclass(slots=True)
class SequenceIdGenerator:
    """IdGenerator fake that returns caller-supplied IDs in order."""

    library_ids: deque[LibraryId] = field(default_factory=deque)
    track_ids: deque[TrackId] = field(default_factory=deque)
    plan_ids: deque[PlanId] = field(default_factory=deque)
    action_ids: deque[ActionId] = field(default_factory=deque)
    run_ids: deque[RunId] = field(default_factory=deque)
    event_ids: deque[EventId] = field(default_factory=deque)

    def new_library_id(self) -> LibraryId:
        """Return the next deterministic Library ID."""
        return _pop_next(self.library_ids)

    def new_track_id(self) -> TrackId:
        """Return the next deterministic Track ID."""
        return _pop_next(self.track_ids)

    def new_plan_id(self) -> PlanId:
        """Return the next deterministic Plan ID."""
        return _pop_next(self.plan_ids)

    def new_action_id(self) -> ActionId:
        """Return the next deterministic PlanAction ID."""
        return _pop_next(self.action_ids)

    def new_run_id(self) -> RunId:
        """Return the next deterministic Run ID."""
        return _pop_next(self.run_ids)

    def new_event_id(self) -> EventId:
        """Return the next deterministic FileEvent ID."""
        return _pop_next(self.event_ids)


def _pop_next[IdT](values: deque[IdT]) -> IdT:
    """Return the next ID or fail with a clear test setup error."""
    try:
        return values.popleft()
    except IndexError as exc:
        raise AssertionError(EMPTY_SEQUENCE_MESSAGE) from exc
