"""
Summary: Tests Phase 9 apply execution behavior.
Why: Protects durable FileEvent order before Library file mutation.
"""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

import pytest

from omym2.domain.models.file_event import FileEvent, FileEventStatus
from omym2.domain.models.file_snapshot import FileSnapshot
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction, PlanActionReason
from omym2.domain.models.run import RunStatus
from omym2.domain.models.track import Track, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.features.apply.dto import ApplyOptions, ApplyPlanRequest
from omym2.features.apply.ports import ApplyPlanPorts
from omym2.features.apply.usecases.apply_plan import ApplyNotConfirmedError, ApplyPlanUseCase, PlanCannotBeAppliedError
from omym2.shared.ids import ActionId, EventId, LibraryId, PlanId, RunId, TrackId
from tests.fakes.in_memory_repositories import InMemoryUnitOfWork
from tests.fakes.runtime import FixedClock, SequenceIdGenerator

if TYPE_CHECKING:
    from omym2.features.common_ports import FileSystemPath

ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567b"))
BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CONFIG_HASH = "config-hash"
CONTENT_HASH = "content-hash"
EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567e"))
FILE_EXTENSION = ".flac"
FILE_SIZE = 5
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
LIBRARY_ROOT = "/music/library"
METADATA_HASH = "metadata-hash"
MOVE_FAILURE_MESSAGE = "move failed"
OTHER_LIBRARY_ROOT = "/music/moved-library"
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567a"))
RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567d"))
SECOND_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567c"))
SECOND_EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567f"))
SECOND_SOURCE_PATH = "/music/incoming/Second.flac"
SECOND_TARGET_PATH = "Artist/2026_Album/1-03_Second.flac"
SOURCE_PATH = "/music/incoming/Title.flac"
TARGET_PATH = "Artist/2026_Album/1-02_Title.flac"
TRACK_ARTIST = "Artist"
TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345679"))
TRACK_TITLE = "Title"

LIBRARY_SOURCE_PATH = "Unsorted/Title.flac"
LIBRARY_SOURCE_FILESYSTEM_PATH = f"{LIBRARY_ROOT}/{LIBRARY_SOURCE_PATH}"


def test_apply_creates_run_and_pending_file_event_before_file_move() -> None:
    """Apply persists Run, applying Plan, and pending FileEvent before moving."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan())
    uow.plan_actions.save(_move_action())
    ports, mover = _ports(
        uow,
        {SOURCE_PATH: _snapshot(SOURCE_PATH)},
        SequenceIdGenerator(
            run_ids=deque((RUN_ID,)),
            event_ids=deque((EVENT_ID,)),
            track_ids=deque((TRACK_ID,)),
        ),
    )

    run = ApplyPlanUseCase(ports).execute(_apply_request())

    assert run is not None
    assert run.status == RunStatus.SUCCEEDED
    assert mover.moves == [(SOURCE_PATH, f"{LIBRARY_ROOT}/{TARGET_PATH}")]
    assert mover.states_at_move == [("running", "applying", "pending")]
    assert _stored_plan(uow).status == PlanStatus.APPLIED
    assert _stored_action(uow).status == ActionStatus.APPLIED
    assert _stored_event(uow).status == FileEventStatus.SUCCEEDED
    track = _stored_track(uow)
    assert track.current_path == TARGET_PATH
    assert track.canonical_path == TARGET_PATH


def test_apply_marks_skip_action_applied_without_file_event() -> None:
    """Skip actions become applied without FileEvents or file moves."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan())
    uow.plan_actions.save(_skip_action())
    ports, mover = _ports(uow, {}, SequenceIdGenerator(run_ids=deque((RUN_ID,))))

    run = ApplyPlanUseCase(ports).execute(_apply_request())

    assert run is not None
    assert run.status == RunStatus.SUCCEEDED
    assert _stored_action(uow).status == ActionStatus.APPLIED
    assert uow.file_events.records == {}
    assert mover.moves == []


def test_apply_succeeds_when_plan_has_no_eligible_move_actions() -> None:
    """Blocked-only Plans apply no files and keep blocked actions blocked."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(status=LibraryStatus.BLOCKED))
    uow.plans.save(_plan(plan_type=PlanType.ORGANIZE))
    uow.plan_actions.save(_blocked_action())
    ports, mover = _ports(uow, {}, SequenceIdGenerator(run_ids=deque((RUN_ID,))))

    run = ApplyPlanUseCase(ports).execute(_apply_request())

    assert run is not None
    assert run.status == RunStatus.SUCCEEDED
    assert _stored_plan(uow).status == PlanStatus.APPLIED
    assert _stored_action(uow).status == ActionStatus.BLOCKED
    assert _stored_library(uow).status == LibraryStatus.BLOCKED
    assert uow.file_events.records == {}
    assert mover.moves == []


def test_apply_precondition_failure_creates_no_file_event() -> None:
    """Changed source content fails the action before any mutation event."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan())
    uow.plan_actions.save(_move_action())
    ports, mover = _ports(
        uow,
        {SOURCE_PATH: _snapshot(SOURCE_PATH, content_hash="changed-content-hash")},
        SequenceIdGenerator(run_ids=deque((RUN_ID,))),
    )

    run = ApplyPlanUseCase(ports).execute(_apply_request())

    assert run is not None
    assert run.status == RunStatus.FAILED
    action = _stored_action(uow)
    assert action.status == ActionStatus.FAILED
    assert action.reason == PlanActionReason.SOURCE_CHANGED
    assert uow.file_events.records == {}
    assert mover.moves == []


def test_apply_marks_run_partial_failed_when_later_move_fails() -> None:
    """A failed second mutation leaves succeeded earlier evidence intact."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan())
    uow.plan_actions.save(_move_action())
    uow.plan_actions.save(_move_action(SECOND_ACTION_ID, SECOND_SOURCE_PATH, SECOND_TARGET_PATH, sort_order=2))
    ports, _ = _ports(
        uow,
        {
            SOURCE_PATH: _snapshot(SOURCE_PATH),
            SECOND_SOURCE_PATH: _snapshot(SECOND_SOURCE_PATH),
        },
        SequenceIdGenerator(
            run_ids=deque((RUN_ID,)),
            event_ids=deque((EVENT_ID, SECOND_EVENT_ID)),
            track_ids=deque((TRACK_ID,)),
        ),
        mover=RecordingFileMover(uow, failing_targets={f"{LIBRARY_ROOT}/{SECOND_TARGET_PATH}"}),
    )

    run = ApplyPlanUseCase(ports).execute(_apply_request())

    assert run is not None
    assert run.status == RunStatus.PARTIAL_FAILED
    assert _stored_plan(uow).status == PlanStatus.PARTIAL_FAILED
    assert _stored_action(uow).status == ActionStatus.APPLIED
    assert _stored_action(uow, SECOND_ACTION_ID).status == ActionStatus.FAILED
    assert _stored_event(uow).status == FileEventStatus.SUCCEEDED
    assert _stored_event(uow, SECOND_EVENT_ID).status == FileEventStatus.FAILED


def test_plan_cannot_be_applied_twice() -> None:
    """Terminal Plans are rejected without creating another Run."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan(status=PlanStatus.APPLIED))
    ports, _ = _ports(uow, {}, SequenceIdGenerator(run_ids=deque((RUN_ID,))))

    with pytest.raises(PlanCannotBeAppliedError):
        _ = ApplyPlanUseCase(ports).execute(_apply_request())

    assert uow.runs.records == {}
    assert uow.file_events.records == {}


def test_apply_requires_confirmation_option() -> None:
    """ApplyOptions.yes must confirm file mutation before a Run starts."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan())
    ports, _ = _ports(uow, {}, SequenceIdGenerator(run_ids=deque((RUN_ID,))))

    with pytest.raises(ApplyNotConfirmedError):
        _ = ApplyPlanUseCase(ports).execute(ApplyPlanRequest(PLAN_ID))

    assert uow.runs.records == {}
    assert uow.file_events.records == {}


def test_apply_expires_plan_when_library_root_changed_before_run() -> None:
    """A root mismatch before Run creation expires the Plan without FileEvents."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(root_path=OTHER_LIBRARY_ROOT))
    uow.plans.save(_plan())
    ports, _ = _ports(uow, {}, SequenceIdGenerator(run_ids=deque((RUN_ID,))))

    run = ApplyPlanUseCase(ports).execute(_apply_request())

    assert run is None
    assert _stored_plan(uow).status == PlanStatus.EXPIRED
    assert uow.runs.records == {}
    assert uow.file_events.records == {}


def test_apply_marks_partial_failed_when_library_root_changes_after_run() -> None:
    """A root mismatch after one move stops later moves without a FileEvent."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan())
    uow.plan_actions.save(_move_action())
    uow.plan_actions.save(_move_action(SECOND_ACTION_ID, SECOND_SOURCE_PATH, SECOND_TARGET_PATH, sort_order=2))
    ports, _ = _ports(
        uow,
        {SOURCE_PATH: _snapshot(SOURCE_PATH)},
        SequenceIdGenerator(
            run_ids=deque((RUN_ID,)),
            event_ids=deque((EVENT_ID,)),
            track_ids=deque((TRACK_ID,)),
        ),
        mover=RecordingFileMover(uow, root_after_first_move=OTHER_LIBRARY_ROOT),
    )

    run = ApplyPlanUseCase(ports).execute(_apply_request())

    assert run is not None
    assert run.status == RunStatus.PARTIAL_FAILED
    assert _stored_plan(uow).status == PlanStatus.PARTIAL_FAILED
    assert _stored_action(uow).status == ActionStatus.APPLIED
    assert _stored_action(uow, SECOND_ACTION_ID).status == ActionStatus.PLANNED
    assert tuple(uow.file_events.records) == (EVENT_ID,)


def test_apply_registers_library_after_successful_organize_plan() -> None:
    """Successful organize moves register the Library when no blocks remain."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(status=LibraryStatus.UNREGISTERED))
    uow.tracks.save(_track())
    uow.plans.save(_plan(plan_type=PlanType.ORGANIZE))
    uow.plan_actions.save(_move_action(source_path=LIBRARY_SOURCE_PATH, track_id=TRACK_ID))
    ports, _ = _ports(
        uow,
        {LIBRARY_SOURCE_FILESYSTEM_PATH: _snapshot(LIBRARY_SOURCE_FILESYSTEM_PATH)},
        SequenceIdGenerator(run_ids=deque((RUN_ID,)), event_ids=deque((EVENT_ID,))),
    )

    run = ApplyPlanUseCase(ports).execute(_apply_request())

    assert run is not None
    assert run.status == RunStatus.SUCCEEDED
    library = _stored_library(uow)
    assert library.status == LibraryStatus.REGISTERED
    assert library.registered_at == BASE_TIME
    track = _stored_track(uow)
    assert track.current_path == TARGET_PATH
    assert track.track_id == TRACK_ID


class MappingSnapshotReader:
    """FileSnapshotReader fake keyed by filesystem path text."""

    def __init__(self, snapshots: dict[str, FileSnapshot]) -> None:
        """Store snapshots by path."""
        self._snapshots: dict[str, FileSnapshot] = snapshots

    def capture(self, path: FileSystemPath) -> FileSnapshot:
        """Return the configured snapshot for a path."""
        return self._snapshots[str(path)]


class SimplePathResolver:
    """PathResolver fake joining Library roots and logical paths."""

    def resolve_library_path(self, library_root: FileSystemPath, library_relative_path: str) -> str:
        """Return a filesystem path for a Library-relative path."""
        return f"{str(library_root).rstrip('/')}/{library_relative_path}"

    def relative_to_library(self, library_root: FileSystemPath, path: FileSystemPath) -> str:
        """Return a lexical Library-relative path for completeness."""
        return str(path).removeprefix(f"{str(library_root).rstrip('/')}/")


class RecordingFileMover:
    """FileMover fake that records durable state at mutation time."""

    def __init__(
        self,
        uow: InMemoryUnitOfWork,
        *,
        failing_targets: set[str] | None = None,
        root_after_first_move: str | None = None,
    ) -> None:
        """Store failure and root-change behavior for assertions."""
        self._uow: InMemoryUnitOfWork = uow
        self._failing_targets: set[str] = set() if failing_targets is None else set(failing_targets)
        self._root_after_first_move: str | None = root_after_first_move
        self.moves: list[tuple[str, str]] = []
        self.states_at_move: list[tuple[str, str, str]] = []

    def move(self, source: FileSystemPath, target: FileSystemPath) -> None:
        """Record move inputs and fail configured targets."""
        self.moves.append((str(source), str(target)))
        run = self._uow.runs.get(RUN_ID)
        plan = self._uow.plans.get(PLAN_ID)
        events = tuple(self._uow.file_events.records.values())
        assert run is not None
        assert plan is not None
        assert len(events) > 0
        self.states_at_move.append((run.status.value, plan.status.value, events[-1].status.value))

        if str(target) in self._failing_targets:
            raise OSError(MOVE_FAILURE_MESSAGE)

        if self._root_after_first_move is not None and len(self.moves) == 1:
            library = self._uow.libraries.get(LIBRARY_ID)
            assert library is not None
            self._uow.libraries.save(library.with_root_path(self._root_after_first_move, BASE_TIME))


def _ports(
    uow: InMemoryUnitOfWork,
    snapshots: dict[str, FileSnapshot],
    id_generator: SequenceIdGenerator,
    *,
    mover: RecordingFileMover | None = None,
) -> tuple[ApplyPlanPorts, RecordingFileMover]:
    file_mover = RecordingFileMover(uow) if mover is None else mover
    return (
        ApplyPlanPorts(
            uow=uow,
            file_mover=file_mover,
            file_snapshot_reader=MappingSnapshotReader(snapshots),
            path_resolver=SimplePathResolver(),
            clock=FixedClock(BASE_TIME),
            id_generator=id_generator,
        ),
        file_mover,
    )


def _library(
    *,
    root_path: str = LIBRARY_ROOT,
    status: LibraryStatus = LibraryStatus.REGISTERED,
) -> Library:
    return Library(
        library_id=LIBRARY_ID,
        root_path=root_path,
        path_policy_hash=CONFIG_HASH,
        registered_at=BASE_TIME if status == LibraryStatus.REGISTERED else None,
        status=status,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _plan(
    *,
    plan_type: PlanType = PlanType.ADD,
    status: PlanStatus = PlanStatus.READY,
) -> Plan:
    return Plan(
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        plan_type=plan_type,
        status=status,
        created_at=BASE_TIME,
        config_hash=CONFIG_HASH,
        library_root_at_plan=LIBRARY_ROOT,
        summary={"action_count": "1"},
    )


def _move_action(
    action_id: ActionId = ACTION_ID,
    source_path: str = SOURCE_PATH,
    target_path: str = TARGET_PATH,
    *,
    track_id: TrackId | None = None,
    sort_order: int = 1,
) -> PlanAction:
    return PlanAction(
        action_id=action_id,
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        track_id=track_id,
        action_type=ActionType.MOVE,
        source_path=source_path,
        target_path=target_path,
        content_hash_at_plan=CONTENT_HASH,
        metadata_hash_at_plan=METADATA_HASH,
        status=ActionStatus.PLANNED,
        reason=None,
        sort_order=sort_order,
    )


def _skip_action() -> PlanAction:
    return PlanAction(
        action_id=ACTION_ID,
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        track_id=TRACK_ID,
        action_type=ActionType.SKIP,
        source_path=SOURCE_PATH,
        target_path=TARGET_PATH,
        content_hash_at_plan=CONTENT_HASH,
        metadata_hash_at_plan=METADATA_HASH,
        status=ActionStatus.PLANNED,
        reason=PlanActionReason.DUPLICATE_HASH,
        sort_order=1,
    )


def _blocked_action() -> PlanAction:
    return PlanAction(
        action_id=ACTION_ID,
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        track_id=None,
        action_type=ActionType.MOVE,
        source_path=SOURCE_PATH,
        target_path=TARGET_PATH,
        content_hash_at_plan=CONTENT_HASH,
        metadata_hash_at_plan=METADATA_HASH,
        status=ActionStatus.BLOCKED,
        reason=PlanActionReason.TARGET_EXISTS,
        sort_order=1,
    )


def _track() -> Track:
    return Track(
        track_id=TRACK_ID,
        library_id=LIBRARY_ID,
        current_path=LIBRARY_SOURCE_PATH,
        canonical_path=TARGET_PATH,
        content_hash=CONTENT_HASH,
        metadata_hash=METADATA_HASH,
        metadata=_metadata(),
        status=TrackStatus.ACTIVE,
        first_seen_at=BASE_TIME,
        last_seen_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _snapshot(path: str, *, content_hash: str = CONTENT_HASH) -> FileSnapshot:
    return FileSnapshot(
        path=path,
        size=FILE_SIZE,
        mtime=BASE_TIME,
        file_extension=FILE_EXTENSION,
        content_hash=content_hash,
        metadata_hash=METADATA_HASH,
        metadata=_metadata(),
        captured_at=BASE_TIME,
    )


def _metadata() -> TrackMetadata:
    return TrackMetadata(title=TRACK_TITLE, artist=TRACK_ARTIST)


def _apply_request() -> ApplyPlanRequest:
    return ApplyPlanRequest(PLAN_ID, options=ApplyOptions(yes=True))


def _stored_plan(uow: InMemoryUnitOfWork) -> Plan:
    plan = uow.plans.get(PLAN_ID)
    assert plan is not None
    return plan


def _stored_action(uow: InMemoryUnitOfWork, action_id: ActionId = ACTION_ID) -> PlanAction:
    action = uow.plan_actions.get(action_id)
    assert action is not None
    return action


def _stored_event(uow: InMemoryUnitOfWork, event_id: EventId = EVENT_ID) -> FileEvent:
    event = uow.file_events.get(event_id)
    assert event is not None
    return event


def _stored_library(uow: InMemoryUnitOfWork) -> Library:
    library = uow.libraries.get(LIBRARY_ID)
    assert library is not None
    return library


def _stored_track(uow: InMemoryUnitOfWork) -> Track:
    track = uow.tracks.get(TRACK_ID)
    assert track is not None
    return track
