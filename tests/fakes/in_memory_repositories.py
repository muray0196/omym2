"""
Summary: Provides in-memory repository fakes for usecase tests.
Why: Lets feature tests exercise ports before SQLite adapters exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Self

from omym2.domain.models.file_event import FileEventStatus
from omym2.domain.models.track import TrackGrouping
from omym2.shared.pagination import (
    INVALID_CURSOR_MESSAGE,
    CursorDecodeError,
    FacetValue,
    GroupCount,
    Page,
    paginate_group_counts,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime
    from types import TracebackType

    from omym2.domain.models.check_issue import CheckIssue, CheckIssueType
    from omym2.domain.models.check_run import CheckRun
    from omym2.domain.models.file_event import FileEvent
    from omym2.domain.models.library import Library
    from omym2.domain.models.plan import Plan, PlanStatus, PlanType
    from omym2.domain.models.plan_action import ActionStatus, PlanAction
    from omym2.domain.models.run import Run, RunStatus
    from omym2.domain.models.track import Track, TrackStatus
    from omym2.shared.ids import ActionId, CheckRunId, EventId, LibraryId, PlanId, RunId, TrackId
    from omym2.shared.pagination import PageRequest

UNKNOWN_TRACK_GROUP_LABEL = "(unknown)"
TRACK_GROUP_LABEL_SEPARATOR = " — "  # em dash joiner, matching SQLiteTrackRepository.group_page
UNSUPPORTED_TRACK_GROUPING_MESSAGE = "Unsupported Track grouping"
KEYSET_CURSOR_KEY_LENGTH = 2  # every Track/Track-group cursor key is a 2-tuple
CHECK_ISSUE_CURSOR_KEY_LENGTH = 1  # a CheckIssue cursor key is a single issue_seq value


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
class InMemoryCheckRunRepository:
    """In-memory CheckRunRepository fake."""

    records: dict[LibraryId, CheckRun] = field(default_factory=dict)

    def save(self, check_run: CheckRun) -> None:
        """Store or replace one Library's CheckRun."""
        self.records[check_run.library_id] = check_run

    def latest(self, library_id: LibraryId) -> CheckRun | None:
        """Return the latest CheckRun for one Library, if any."""
        return self.records.get(library_id)

    def earliest_checked_at(self) -> datetime | None:
        """Return the minimum checked_at across every Library's latest check run, or None if none exist."""
        checked_at_values = [check_run.checked_at for check_run in self.records.values()]
        return min(checked_at_values) if checked_at_values else None

    def delete_for_library(self, library_id: LibraryId) -> None:
        """Delete the CheckRun row for one Library."""
        _ = self.records.pop(library_id, None)


@dataclass(slots=True)
class InMemoryCheckIssueRepository:
    """In-memory CheckIssueRepository fake."""

    records: dict[int, CheckIssue] = field(default_factory=dict)
    _next_issue_seq: int = field(default=1, init=False)

    def save_many(self, check_run_id: CheckRunId, issues: Sequence[CheckIssue]) -> None:
        """Store CheckIssues for one check run in insertion (issue_seq ASC) order."""
        del check_run_id
        for issue in issues:
            self.records[self._next_issue_seq] = issue
            self._next_issue_seq += 1

    def delete_for_library(self, library_id: LibraryId) -> None:
        """Delete every persisted CheckIssue for one Library."""
        for issue_seq in [seq for seq, issue in self.records.items() if issue.library_id == library_id]:
            del self.records[issue_seq]

    def query_page(
        self,
        library_id: LibraryId | None,
        *,
        issue_type: CheckIssueType | None,
        page: PageRequest,
    ) -> Page[CheckIssue]:
        """Return one keyset page of CheckIssues ordered issue_seq ASC."""
        entries = [
            (issue_seq, issue)
            for issue_seq, issue in sorted(self.records.items())
            if (library_id is None or issue.library_id == library_id)
            and (issue_type is None or issue.issue_type == issue_type)
        ]
        total = len(entries)

        if page.cursor_key is not None:
            if len(page.cursor_key) != CHECK_ISSUE_CURSOR_KEY_LENGTH:
                raise CursorDecodeError(INVALID_CURSOR_MESSAGE)
            (cursor_text,) = page.cursor_key
            try:
                cursor_issue_seq = int(cursor_text)
            except ValueError as error:
                raise CursorDecodeError(INVALID_CURSOR_MESSAGE) from error
            entries = [(issue_seq, issue) for issue_seq, issue in entries if issue_seq > cursor_issue_seq]

        page_entries = entries[: page.limit]
        has_more = len(entries) > page.limit
        page_items = tuple(issue for _, issue in page_entries)
        next_cursor_key = (str(page_entries[-1][0]),) if has_more else None
        return Page(items=page_items, next_cursor_key=next_cursor_key, total=total)

    def issue_type_facets(self, library_id: LibraryId | None) -> tuple[FacetValue, ...]:
        """Return CheckIssue issue_type facets, ordered count DESC then value ASC."""
        counts: dict[str, int] = {}
        for issue in self.records.values():
            if library_id is not None and issue.library_id != library_id:
                continue
            counts[issue.issue_type.value] = counts.get(issue.issue_type.value, 0) + 1
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return tuple(FacetValue(value=value, count=count) for value, count in ordered)

    def group_page(self, library_id: LibraryId | None, page: PageRequest) -> Page[GroupCount]:
        """Return one keyset page of CheckIssue groups by issue_type ordered count DESC then key ASC."""
        counts: dict[str, int] = {}
        for issue in self.records.values():
            if library_id is not None and issue.library_id != library_id:
                continue
            counts[issue.issue_type.value] = counts.get(issue.issue_type.value, 0) + 1
        groups = [GroupCount(key=value, label=value, count=count) for value, count in counts.items()]
        return paginate_group_counts(groups, page)


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

    def query_page(
        self,
        library_id: LibraryId | None,
        *,
        search: str | None,
        status: TrackStatus | None,
        page: PageRequest,
    ) -> Page[Track]:
        """Return one keyset page of Tracks ordered (current_path, track_id)."""
        tracks = [
            track
            for track in self.records.values()
            if (library_id is None or track.library_id == library_id)
            and (status is None or track.status == status)
            and (not search or _track_matches_search(track, search))
        ]
        tracks.sort(key=lambda track: (track.current_path, str(track.track_id)))
        total = len(tracks)

        if page.cursor_key is not None:
            if len(page.cursor_key) != KEYSET_CURSOR_KEY_LENGTH:
                raise CursorDecodeError(INVALID_CURSOR_MESSAGE)
            cursor_path, cursor_track_id = page.cursor_key
            tracks = [
                track for track in tracks if (track.current_path, str(track.track_id)) > (cursor_path, cursor_track_id)
            ]

        page_items = tuple(tracks[: page.limit])
        has_more = len(tracks) > page.limit
        next_cursor_key = (page_items[-1].current_path, str(page_items[-1].track_id)) if has_more else None
        return Page(items=page_items, next_cursor_key=next_cursor_key, total=total)

    def status_facets(self, library_id: LibraryId | None) -> tuple[FacetValue, ...]:
        """Return Track status facet counts, ordered count DESC then value ASC."""
        counts: dict[str, int] = {}
        for track in self.records.values():
            if library_id is not None and track.library_id != library_id:
                continue
            counts[track.status.value] = counts.get(track.status.value, 0) + 1
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return tuple(FacetValue(value=value, count=count) for value, count in ordered)

    def group_page(
        self,
        library_id: LibraryId | None,
        grouping: TrackGrouping,
        page: PageRequest,
    ) -> Page[GroupCount]:
        """Return one keyset page of Track groups ordered count DESC then key ASC."""
        if grouping is not TrackGrouping.ARTIST_ALBUM:
            unsupported_grouping_message = f"{UNSUPPORTED_TRACK_GROUPING_MESSAGE}: {grouping}"
            raise ValueError(unsupported_grouping_message)  # pyright: ignore[reportUnreachable]

        counts: dict[tuple[str, str], int] = {}
        for track in self.records.values():
            if library_id is not None and track.library_id != library_id:
                continue
            group_artist = track.metadata.album_artist or track.metadata.artist or UNKNOWN_TRACK_GROUP_LABEL
            group_album = track.metadata.album or UNKNOWN_TRACK_GROUP_LABEL
            counts[(group_artist, group_album)] = counts.get((group_artist, group_album), 0) + 1

        groups = [
            GroupCount(
                key=f"{group_artist}\x1f{group_album}",
                label=f"{group_artist}{TRACK_GROUP_LABEL_SEPARATOR}{group_album}",
                count=count,
            )
            for (group_artist, group_album), count in counts.items()
        ]
        return paginate_group_counts(groups, page)


def _track_matches_search(track: Track, search: str) -> bool:
    needle = search.lower()
    haystacks = (
        track.metadata.title,
        track.metadata.artist,
        track.metadata.album,
        track.current_path,
        str(track.track_id),
    )
    return any(haystack is not None and needle in haystack.lower() for haystack in haystacks)


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

    def query_page(
        self,
        library_id: LibraryId | None,
        *,
        status: PlanStatus | None,
        plan_type: PlanType | None,
        page: PageRequest,
    ) -> Page[Plan]:
        """Return one keyset page of Plans ordered (created_at DESC, plan_id DESC)."""
        plans = [
            plan
            for plan in self.records.values()
            if (library_id is None or plan.library_id == library_id)
            and (status is None or plan.status == status)
            and (plan_type is None or plan.plan_type == plan_type)
        ]
        plans.sort(key=lambda plan: (plan.created_at, str(plan.plan_id)), reverse=True)
        total = len(plans)

        if page.cursor_key is not None:
            if len(page.cursor_key) != KEYSET_CURSOR_KEY_LENGTH:
                raise CursorDecodeError(INVALID_CURSOR_MESSAGE)
            cursor_created_at, cursor_plan_id = page.cursor_key
            plans = [
                plan
                for plan in plans
                if (plan.created_at.isoformat(), str(plan.plan_id)) < (cursor_created_at, cursor_plan_id)
            ]

        page_items = tuple(plans[: page.limit])
        has_more = len(plans) > page.limit
        next_cursor_key = (page_items[-1].created_at.isoformat(), str(page_items[-1].plan_id)) if has_more else None
        return Page(items=page_items, next_cursor_key=next_cursor_key, total=total)


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

    def query_page(
        self,
        plan_id: PlanId,
        *,
        status: ActionStatus | None,
        page: PageRequest,
    ) -> Page[PlanAction]:
        """Return one keyset page of a Plan's actions ordered (sort_order, action_id)."""
        actions = [
            action
            for action in self.records.values()
            if action.plan_id == plan_id and (status is None or action.status == status)
        ]
        actions.sort(key=lambda action: (action.sort_order, str(action.action_id)))
        total = len(actions)

        if page.cursor_key is not None:
            if len(page.cursor_key) != KEYSET_CURSOR_KEY_LENGTH:
                raise CursorDecodeError(INVALID_CURSOR_MESSAGE)
            cursor_sort_order_text, cursor_action_id = page.cursor_key
            try:
                cursor_sort_order = int(cursor_sort_order_text)
            except ValueError as error:
                raise CursorDecodeError(INVALID_CURSOR_MESSAGE) from error
            actions = [
                action
                for action in actions
                if (action.sort_order, str(action.action_id)) > (cursor_sort_order, cursor_action_id)
            ]

        page_items = tuple(actions[: page.limit])
        has_more = len(actions) > page.limit
        next_cursor_key = (str(page_items[-1].sort_order), str(page_items[-1].action_id)) if has_more else None
        return Page(items=page_items, next_cursor_key=next_cursor_key, total=total)

    def status_facets(self, plan_id: PlanId) -> tuple[FacetValue, ...]:
        """Return PlanAction status facets for one Plan, ordered count DESC then value ASC."""
        counts: dict[str, int] = {}
        for action in self.records.values():
            if action.plan_id != plan_id:
                continue
            counts[action.status.value] = counts.get(action.status.value, 0) + 1
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return tuple(FacetValue(value=value, count=count) for value, count in ordered)

    def action_type_facets(self, plan_id: PlanId) -> tuple[FacetValue, ...]:
        """Return PlanAction type facets for one Plan, ordered count DESC then value ASC."""
        counts: dict[str, int] = {}
        for action in self.records.values():
            if action.plan_id != plan_id:
                continue
            counts[action.action_type.value] = counts.get(action.action_type.value, 0) + 1
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return tuple(FacetValue(value=value, count=count) for value, count in ordered)

    def list_target_paths(self, plan_id: PlanId) -> tuple[str, ...]:
        """Return the non-null target_path values recorded for one Plan's actions."""
        actions = sorted(
            (action for action in self.records.values() if action.plan_id == plan_id),
            key=lambda action: (action.sort_order, str(action.action_id)),
        )
        return tuple(action.target_path for action in actions if action.target_path is not None)


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

    def query_page(
        self,
        library_id: LibraryId | None,
        *,
        status: RunStatus | None,
        page: PageRequest,
    ) -> Page[Run]:
        """Return one keyset page of Runs ordered (started_at DESC, run_id DESC)."""
        runs = [
            run
            for run in self.records.values()
            if (library_id is None or run.library_id == library_id) and (status is None or run.status == status)
        ]
        runs.sort(key=lambda run: (run.started_at, str(run.run_id)), reverse=True)
        total = len(runs)

        if page.cursor_key is not None:
            if len(page.cursor_key) != KEYSET_CURSOR_KEY_LENGTH:
                raise CursorDecodeError(INVALID_CURSOR_MESSAGE)
            cursor_started_at, cursor_run_id = page.cursor_key
            runs = [
                run
                for run in runs
                if (run.started_at.isoformat(), str(run.run_id)) < (cursor_started_at, cursor_run_id)
            ]

        page_items = tuple(runs[: page.limit])
        has_more = len(runs) > page.limit
        next_cursor_key = (page_items[-1].started_at.isoformat(), str(page_items[-1].run_id)) if has_more else None
        return Page(items=page_items, next_cursor_key=next_cursor_key, total=total)

    def status_facets(self, library_id: LibraryId | None) -> tuple[FacetValue, ...]:
        """Return Run status facet counts, ordered count DESC then value ASC."""
        counts: dict[str, int] = {}
        for run in self.records.values():
            if library_id is not None and run.library_id != library_id:
                continue
            counts[run.status.value] = counts.get(run.status.value, 0) + 1
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return tuple(FacetValue(value=value, count=count) for value, count in ordered)


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

    def list_pending_by_library(self, library_id: LibraryId) -> tuple[FileEvent, ...]:
        """Return PENDING FileEvents for a Library in durable sequence order."""
        return tuple(
            sorted(
                (
                    event
                    for event in self.records.values()
                    if event.library_id == library_id and event.status == FileEventStatus.PENDING
                ),
                key=lambda event: event.sequence_no,
            )
        )

    def save(self, event: FileEvent) -> None:
        """Store or replace one FileEvent."""
        self.records[event.event_id] = event

    def query_page(
        self,
        run_id: RunId,
        *,
        status: FileEventStatus | None,
        page: PageRequest,
    ) -> Page[FileEvent]:
        """Return one keyset page of a Run's FileEvents ordered (sequence_no, event_id)."""
        events = [
            event
            for event in self.records.values()
            if event.run_id == run_id and (status is None or event.status == status)
        ]
        events.sort(key=lambda event: (event.sequence_no, str(event.event_id)))
        total = len(events)

        if page.cursor_key is not None:
            if len(page.cursor_key) != KEYSET_CURSOR_KEY_LENGTH:
                raise CursorDecodeError(INVALID_CURSOR_MESSAGE)
            cursor_sequence_no_text, cursor_event_id = page.cursor_key
            try:
                cursor_sequence_no = int(cursor_sequence_no_text)
            except ValueError as error:
                raise CursorDecodeError(INVALID_CURSOR_MESSAGE) from error
            events = [
                event
                for event in events
                if (event.sequence_no, str(event.event_id)) > (cursor_sequence_no, cursor_event_id)
            ]

        page_items = tuple(events[: page.limit])
        has_more = len(events) > page.limit
        next_cursor_key = (str(page_items[-1].sequence_no), str(page_items[-1].event_id)) if has_more else None
        return Page(items=page_items, next_cursor_key=next_cursor_key, total=total)


@dataclass(slots=True)
class InMemoryUnitOfWork:
    """In-memory UnitOfWork fake with observable transaction calls."""

    libraries: InMemoryLibraryRepository = field(default_factory=InMemoryLibraryRepository)
    check_runs: InMemoryCheckRunRepository = field(default_factory=InMemoryCheckRunRepository)
    check_issues: InMemoryCheckIssueRepository = field(default_factory=InMemoryCheckIssueRepository)
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
