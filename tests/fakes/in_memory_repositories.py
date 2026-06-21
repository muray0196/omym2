"""
Summary: Provides in-memory repository fakes for usecase tests.
Why: Lets feature tests exercise ports before SQLite adapters exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from types import TracebackType

    from omym2.domain.models.file_event import FileEvent
    from omym2.domain.models.library import Library
    from omym2.domain.models.plan import Plan
    from omym2.domain.models.plan_action import PlanAction
    from omym2.domain.models.run import Run
    from omym2.domain.models.track import Track
    from omym2.shared.ids import ActionId, EventId, LibraryId, PlanId, RunId, TrackId


@dataclass(slots=True)
class InMemoryLibraryRepository:
    """In-memory LibraryRepository fake."""

    records: dict[LibraryId, Library] = field(default_factory=dict)

    def get(self, library_id: LibraryId) -> Library | None:
        """Return one Library by ID."""
        return self.records.get(library_id)

    def find_by_root_path(self, root_path: str) -> Library | None:
        """Return the Library currently stored for a root path."""
        for library in self.records.values():
            if library.root_path == root_path:
                return library
        return None

    def list_all(self) -> tuple[Library, ...]:
        """Return all Libraries in insertion order."""
        return tuple(self.records.values())

    def save(self, library: Library) -> None:
        """Store or replace one Library."""
        self.records[library.library_id] = library


@dataclass(slots=True)
class InMemoryTrackRepository:
    """In-memory TrackRepository fake."""

    records: dict[TrackId, Track] = field(default_factory=dict)

    def get(self, track_id: TrackId) -> Track | None:
        """Return one Track by ID."""
        return self.records.get(track_id)

    def list_by_library(self, library_id: LibraryId) -> tuple[Track, ...]:
        """Return Tracks owned by a Library."""
        return tuple(track for track in self.records.values() if track.library_id == library_id)

    def find_by_content_hash(self, library_id: LibraryId, content_hash: str) -> tuple[Track, ...]:
        """Return Tracks with a matching content hash in one Library."""
        return tuple(
            track
            for track in self.records.values()
            if track.library_id == library_id and track.content_hash == content_hash
        )

    def save(self, track: Track) -> None:
        """Store or replace one Track."""
        self.records[track.track_id] = track


@dataclass(slots=True)
class InMemoryPlanRepository:
    """In-memory PlanRepository fake."""

    records: dict[PlanId, Plan] = field(default_factory=dict)

    def get(self, plan_id: PlanId) -> Plan | None:
        """Return one Plan by ID."""
        return self.records.get(plan_id)

    def list_by_library(self, library_id: LibraryId) -> tuple[Plan, ...]:
        """Return Plans owned by a Library."""
        return tuple(plan for plan in self.records.values() if plan.library_id == library_id)

    def save(self, plan: Plan) -> None:
        """Store or replace one Plan."""
        self.records[plan.plan_id] = plan


@dataclass(slots=True)
class InMemoryPlanActionRepository:
    """In-memory PlanActionRepository fake."""

    records: dict[ActionId, PlanAction] = field(default_factory=dict)

    def get(self, action_id: ActionId) -> PlanAction | None:
        """Return one PlanAction by ID."""
        return self.records.get(action_id)

    def list_by_plan(self, plan_id: PlanId) -> tuple[PlanAction, ...]:
        """Return PlanActions for a Plan in apply order."""
        return tuple(
            sorted(
                (action for action in self.records.values() if action.plan_id == plan_id),
                key=lambda action: action.sort_order,
            )
        )

    def save(self, action: PlanAction) -> None:
        """Store or replace one PlanAction."""
        self.records[action.action_id] = action


@dataclass(slots=True)
class InMemoryRunRepository:
    """In-memory RunRepository fake."""

    records: dict[RunId, Run] = field(default_factory=dict)

    def get(self, run_id: RunId) -> Run | None:
        """Return one Run by ID."""
        return self.records.get(run_id)

    def list_by_library(self, library_id: LibraryId) -> tuple[Run, ...]:
        """Return Runs owned by a Library."""
        return tuple(run for run in self.records.values() if run.library_id == library_id)

    def list_by_plan(self, plan_id: PlanId) -> tuple[Run, ...]:
        """Return Runs created for a Plan."""
        return tuple(run for run in self.records.values() if run.plan_id == plan_id)

    def save(self, run: Run) -> None:
        """Store or replace one Run."""
        self.records[run.run_id] = run


@dataclass(slots=True)
class InMemoryFileEventRepository:
    """In-memory FileEventRepository fake."""

    records: dict[EventId, FileEvent] = field(default_factory=dict)

    def get(self, event_id: EventId) -> FileEvent | None:
        """Return one FileEvent by ID."""
        return self.records.get(event_id)

    def list_by_run(self, run_id: RunId) -> tuple[FileEvent, ...]:
        """Return FileEvents for a Run in durable sequence order."""
        return tuple(
            sorted(
                (event for event in self.records.values() if event.run_id == run_id),
                key=lambda event: event.sequence_no,
            )
        )

    def save(self, event: FileEvent) -> None:
        """Store or replace one FileEvent."""
        self.records[event.event_id] = event


@dataclass(slots=True)
class InMemoryUnitOfWork:
    """In-memory UnitOfWork fake with observable transaction calls."""

    libraries: InMemoryLibraryRepository = field(default_factory=InMemoryLibraryRepository)
    tracks: InMemoryTrackRepository = field(default_factory=InMemoryTrackRepository)
    plans: InMemoryPlanRepository = field(default_factory=InMemoryPlanRepository)
    plan_actions: InMemoryPlanActionRepository = field(default_factory=InMemoryPlanActionRepository)
    runs: InMemoryRunRepository = field(default_factory=InMemoryRunRepository)
    file_events: InMemoryFileEventRepository = field(default_factory=InMemoryFileEventRepository)
    commit_count: int = 0
    rollback_count: int = 0

    def __enter__(self) -> Self:
        """Open the fake transaction boundary."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        """Rollback on exceptions so tests can assert transaction intent."""
        del exc, tb
        if exc_type is not None:
            self.rollback()
        return None

    def commit(self) -> None:
        """Record a commit call."""
        self.commit_count += 1

    def rollback(self) -> None:
        """Record a rollback call."""
        self.rollback_count += 1
