"""
Summary: Tests apply execution behavior.
Why: Protects durable FileEvent order before Library file mutation.
"""

from __future__ import annotations

from collections import deque
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

import pytest

from omym2.domain.models.file_event import FileEvent, FileEventStatus
from omym2.domain.models.file_snapshot import FileSnapshot, FilesystemIdentity
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.operation import Operation, OperationKind, OperationStatus, RunCompletedResult
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction, PlanActionReason
from omym2.domain.models.run import Run, RunStatus
from omym2.domain.models.track import Track, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.features.apply.dto import ApplyOptions, ApplyPlanRequest
from omym2.features.apply.ports import ApplyPlanPorts
from omym2.features.apply.usecases.apply_plan import (
    INVALID_PATH_MOVE_FAILURE_MESSAGE,
    MOVE_FAILED_ERROR_CODE,
    MOVE_FAILED_MESSAGE,
    ApplyNotConfirmedError,
    ApplyPlanError,
    ApplyPlanUseCase,
)
from omym2.shared.ids import ActionId, EventId, LibraryId, OperationId, PlanId, RunId, TrackId
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
FILESYSTEM_IDENTITY = FilesystemIdentity(device_id=1, inode=2, size=FILE_SIZE, mtime_ns=3, ctime_ns=4)
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
LIBRARY_ROOT = "/music/library"
METADATA_HASH = "metadata-hash"
OPERATION_ID = OperationId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345681"))
OPERATION_IDEMPOTENCY_KEY = UUID("018f6a4f-3c2d-7b8a-9abc-def012345682")
OPERATION_REQUEST_FINGERPRINT = "apply-plan-fingerprint"
SUCCESSFUL_MOVE_COMMIT_COUNT = 5
OTHER_LIBRARY_ROOT = "/music/moved-library"
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567a"))
RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567d"))
SECOND_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567c"))
SECOND_EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567f"))
SECOND_SOURCE_PATH = "/music/incoming/Second.flac"
SECOND_TARGET_PATH = "Artist/2026_Album/1-03_Second.flac"
SENSITIVE_MOVE_FAILURE_DETAIL = "Permission denied while moving /home/alice/private-library/Secret.flac"
SOURCE_PATH = "/music/incoming/Title.flac"
TARGET_PATH = "Artist/2026_Album/1-02_Title.flac"
TRACK_ARTIST = "Artist"
TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345679"))
TRACK_TITLE = "Title"
USECASE_SCOPE_CALL_COUNT = 1

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

    run = ApplyPlanUseCase(ports).execute(_apply_request(uow))

    assert run is not None
    assert run.status == RunStatus.SUCCEEDED
    assert mover.moves == [(SOURCE_PATH, f"{LIBRARY_ROOT}/{TARGET_PATH}")]
    assert mover.source_roots == [None]
    assert mover.target_roots == [LIBRARY_ROOT]
    assert mover.expected_source_identities == [FILESYSTEM_IDENTITY]
    assert mover.states_at_move == [("running", "applying", "pending")]
    assert _stored_plan(uow).status == PlanStatus.APPLIED
    assert _stored_action(uow).status == ActionStatus.APPLIED
    assert _stored_event(uow).status == FileEventStatus.SUCCEEDED
    operation = _stored_operation(uow)
    assert operation.status == OperationStatus.SUCCEEDED
    assert isinstance(operation.result, RunCompletedResult)
    assert operation.result.run_id == RUN_ID
    assert uow.commit_count == SUCCESSFUL_MOVE_COMMIT_COUNT
    assert uow.usecase_scope_enter_count == USECASE_SCOPE_CALL_COUNT
    assert uow.usecase_scope_exit_count == USECASE_SCOPE_CALL_COUNT
    track = _stored_track(uow)
    assert track.current_path == TARGET_PATH
    assert track.canonical_path == TARGET_PATH
    assert track.size == FILE_SIZE
    assert track.mtime == BASE_TIME


def test_apply_marks_skip_action_applied_without_file_event() -> None:
    """Skip actions become applied without FileEvents or file moves."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan())
    uow.plan_actions.save(_skip_action())
    ports, mover = _ports(uow, {}, SequenceIdGenerator(run_ids=deque((RUN_ID,))))

    run = ApplyPlanUseCase(ports).execute(_apply_request(uow))

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

    run = ApplyPlanUseCase(ports).execute(_apply_request(uow))

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

    run = ApplyPlanUseCase(ports).execute(_apply_request(uow))

    assert run is not None
    assert run.status == RunStatus.FAILED
    action = _stored_action(uow)
    assert action.status == ActionStatus.FAILED
    assert action.reason == PlanActionReason.SOURCE_CHANGED
    assert uow.file_events.records == {}
    assert mover.moves == []


def test_apply_requires_filesystem_identity_before_pending_event() -> None:
    """Matching hashes without an ephemeral source token cannot reach mutation."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan())
    uow.plan_actions.save(_move_action())
    ports, mover = _ports(
        uow,
        {SOURCE_PATH: _snapshot(SOURCE_PATH, filesystem_identity=None)},
        SequenceIdGenerator(run_ids=deque((RUN_ID,))),
    )

    run = ApplyPlanUseCase(ports).execute(_apply_request(uow))

    assert run.status == RunStatus.FAILED
    action = _stored_action(uow)
    assert action.status == ActionStatus.FAILED
    assert action.reason == PlanActionReason.SOURCE_CHANGED
    assert uow.file_events.records == {}
    assert mover.moves == []


@pytest.mark.parametrize(
    ("action_type", "content_hash_at_plan", "metadata_hash_at_plan"),
    [
        (ActionType.MOVE, None, METADATA_HASH),
        (ActionType.MOVE, CONTENT_HASH, None),
        (ActionType.REFRESH_METADATA, None, METADATA_HASH),
        (ActionType.REFRESH_METADATA, CONTENT_HASH, None),
        (ActionType.REFRESH_METADATA, "changed-content-hash", METADATA_HASH),
        (ActionType.REFRESH_METADATA, CONTENT_HASH, "changed-metadata-hash"),
    ],
)
def test_apply_requires_both_recorded_hashes_for_eligible_actions(
    action_type: ActionType,
    content_hash_at_plan: str | None,
    metadata_hash_at_plan: str | None,
) -> None:
    """Move and refresh actions fail before mutation when either hash is unusable."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan())
    uow.plan_actions.save(
        replace(
            _move_action(),
            action_type=action_type,
            content_hash_at_plan=content_hash_at_plan,
            metadata_hash_at_plan=metadata_hash_at_plan,
        )
    )
    ports, mover = _ports(
        uow,
        {SOURCE_PATH: _snapshot(SOURCE_PATH)},
        SequenceIdGenerator(run_ids=deque((RUN_ID,))),
    )

    run = ApplyPlanUseCase(ports).execute(_apply_request(uow))

    assert run.status == RunStatus.FAILED
    action = _stored_action(uow)
    assert action.status == ActionStatus.FAILED
    assert action.reason == PlanActionReason.SOURCE_CHANGED
    assert uow.file_events.records == {}
    assert mover.moves == []


def test_apply_metadata_precondition_failure_creates_no_file_event() -> None:
    """Changed source metadata fails before moving to a reviewed target."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan())
    uow.plan_actions.save(_move_action())
    ports, mover = _ports(
        uow,
        {SOURCE_PATH: _snapshot(SOURCE_PATH, metadata_hash="changed-metadata-hash")},
        SequenceIdGenerator(run_ids=deque((RUN_ID,))),
    )

    run = ApplyPlanUseCase(ports).execute(_apply_request(uow))

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

    run = ApplyPlanUseCase(ports).execute(_apply_request(uow))

    assert run is not None
    assert run.status == RunStatus.PARTIAL_FAILED
    assert _stored_plan(uow).status == PlanStatus.PARTIAL_FAILED
    assert _stored_action(uow).status == ActionStatus.APPLIED
    assert _stored_action(uow, SECOND_ACTION_ID).status == ActionStatus.FAILED
    assert _stored_event(uow).status == FileEventStatus.SUCCEEDED
    failed_event = _stored_event(uow, SECOND_EVENT_ID)
    assert failed_event.status == FileEventStatus.FAILED
    assert failed_event.error_code == MOVE_FAILED_ERROR_CODE
    assert failed_event.error_message == MOVE_FAILED_MESSAGE
    assert run.error_summary == MOVE_FAILED_MESSAGE
    assert SENSITIVE_MOVE_FAILURE_DETAIL not in failed_event.error_message
    assert SENSITIVE_MOVE_FAILURE_DETAIL not in run.error_summary
    assert _stored_operation(uow).status == OperationStatus.SUCCEEDED


def test_apply_marks_action_invalid_path_when_mover_rejects_target() -> None:
    """A mover-level boundary rejection persists as an invalid_path failure."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan())
    uow.plan_actions.save(_move_action())
    ports, _ = _ports(
        uow,
        {SOURCE_PATH: _snapshot(SOURCE_PATH)},
        SequenceIdGenerator(run_ids=deque((RUN_ID,)), event_ids=deque((EVENT_ID,))),
        mover=RecordingFileMover(uow, invalid_targets={f"{LIBRARY_ROOT}/{TARGET_PATH}"}),
    )

    run = ApplyPlanUseCase(ports).execute(_apply_request(uow))

    assert run is not None
    assert run.status == RunStatus.FAILED
    action = _stored_action(uow)
    assert action.status == ActionStatus.FAILED
    assert action.reason == PlanActionReason.INVALID_PATH
    event = _stored_event(uow)
    assert event.status == FileEventStatus.FAILED
    assert event.error_code == PlanActionReason.INVALID_PATH.value
    assert event.error_message == INVALID_PATH_MOVE_FAILURE_MESSAGE
    assert run.error_summary == INVALID_PATH_MOVE_FAILURE_MESSAGE
    assert SENSITIVE_MOVE_FAILURE_DETAIL not in event.error_message
    assert SENSITIVE_MOVE_FAILURE_DETAIL not in run.error_summary


def test_apply_rejects_execution_without_a_claimed_running_state() -> None:
    """Apply execution cannot bypass the atomic acceptance boundary."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan(status=PlanStatus.APPLIED))
    ports, _ = _ports(uow, {}, SequenceIdGenerator(run_ids=deque((RUN_ID,))))

    with pytest.raises(ApplyPlanError):
        _ = ApplyPlanUseCase(ports).execute(_unclaimed_apply_request())

    assert uow.runs.records == {}
    assert uow.file_events.records == {}


def test_apply_requires_confirmation_option() -> None:
    """ApplyOptions.yes must confirm file mutation before a Run starts."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan())
    ports, _ = _ports(uow, {}, SequenceIdGenerator(run_ids=deque((RUN_ID,))))

    with pytest.raises(ApplyNotConfirmedError):
        _ = ApplyPlanUseCase(ports).execute(_unclaimed_apply_request(confirmed=False))

    assert uow.runs.records == {}
    assert uow.file_events.records == {}
    assert uow.usecase_scope_enter_count == 0
    assert uow.usecase_scope_exit_count == 0


def test_apply_disposes_usecase_scope_when_unexpected_error_escapes() -> None:
    """An unexpected apply error still exits the outer UnitOfWork resource scope."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan())
    uow.plan_actions.save(_move_action())
    ports, _ = _ports(
        uow,
        {},
        SequenceIdGenerator(run_ids=deque((RUN_ID,))),
    )

    with pytest.raises(KeyError):
        _ = ApplyPlanUseCase(ports).execute(_apply_request(uow))

    assert uow.usecase_scope_enter_count == USECASE_SCOPE_CALL_COUNT
    assert uow.usecase_scope_exit_count == USECASE_SCOPE_CALL_COUNT


def test_apply_fails_claimed_run_when_library_root_changes_before_first_action() -> None:
    """A root mismatch after claim fails managed state without FileEvents."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan())
    uow.plan_actions.save(_skip_action())
    ports, _ = _ports(uow, {}, SequenceIdGenerator(run_ids=deque((RUN_ID,))))
    request = _apply_request(uow)
    uow.libraries.save(_library(root_path=OTHER_LIBRARY_ROOT))

    run = ApplyPlanUseCase(ports).execute(request)

    assert run.status == RunStatus.FAILED
    assert _stored_plan(uow).status == PlanStatus.FAILED
    assert _stored_action(uow).status == ActionStatus.PLANNED
    assert _stored_operation(uow).status == OperationStatus.FAILED
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

    run = ApplyPlanUseCase(ports).execute(_apply_request(uow))

    assert run is not None
    assert run.status == RunStatus.PARTIAL_FAILED
    assert _stored_plan(uow).status == PlanStatus.PARTIAL_FAILED
    assert _stored_action(uow).status == ActionStatus.APPLIED
    assert _stored_action(uow, SECOND_ACTION_ID).status == ActionStatus.PLANNED
    assert tuple(uow.file_events.records) == (EVENT_ID,)
    assert _stored_operation(uow).status == OperationStatus.FAILED


def test_apply_registers_library_after_successful_organize_plan() -> None:
    """Successful organize moves register the Library when no blocks remain."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(status=LibraryStatus.UNREGISTERED))
    uow.tracks.save(_track(size=FILE_SIZE, mtime=BASE_TIME))
    uow.plans.save(_plan(plan_type=PlanType.ORGANIZE))
    uow.plan_actions.save(_move_action(source_path=LIBRARY_SOURCE_PATH, track_id=TRACK_ID))
    ports, mover = _ports(
        uow,
        {LIBRARY_SOURCE_FILESYSTEM_PATH: _snapshot(LIBRARY_SOURCE_FILESYSTEM_PATH)},
        SequenceIdGenerator(run_ids=deque((RUN_ID,)), event_ids=deque((EVENT_ID,))),
    )

    run = ApplyPlanUseCase(ports).execute(_apply_request(uow))

    assert run is not None
    assert run.status == RunStatus.SUCCEEDED
    library = _stored_library(uow)
    assert library.status == LibraryStatus.REGISTERED
    assert library.registered_at == BASE_TIME
    track = _stored_track(uow)
    assert track.current_path == TARGET_PATH
    assert track.track_id == TRACK_ID
    assert isinstance(ports.file_snapshot_reader, MappingSnapshotReader)
    assert ports.file_snapshot_reader.captured_paths == [LIBRARY_SOURCE_FILESYSTEM_PATH]
    assert mover.source_roots == [LIBRARY_ROOT]


class MappingSnapshotReader:
    """FileSnapshotReader fake keyed by filesystem path text."""

    def __init__(self, snapshots: dict[str, FileSnapshot]) -> None:
        """Store snapshots by path."""
        self._snapshots: dict[str, FileSnapshot] = snapshots
        self.captured_paths: list[str] = []

    def capture(self, path: FileSystemPath) -> FileSnapshot:
        """Return the configured snapshot for a path."""
        path_text = str(path)
        self.captured_paths.append(path_text)
        return self._snapshots[path_text]


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
        invalid_targets: set[str] | None = None,
        root_after_first_move: str | None = None,
    ) -> None:
        """Store failure and root-change behavior for assertions."""
        self._uow: InMemoryUnitOfWork = uow
        self._failing_targets: set[str] = set() if failing_targets is None else set(failing_targets)
        self._invalid_targets: set[str] = set() if invalid_targets is None else set(invalid_targets)
        self._root_after_first_move: str | None = root_after_first_move
        self.moves: list[tuple[str, str]] = []
        self.source_roots: list[str | None] = []
        self.target_roots: list[str | None] = []
        self.expected_source_identities: list[FilesystemIdentity | None] = []
        self.states_at_move: list[tuple[str, str, str]] = []

    def move(
        self,
        source: FileSystemPath,
        target: FileSystemPath,
        *,
        source_root: FileSystemPath | None = None,
        target_root: FileSystemPath | None = None,
        expected_source_identity: FilesystemIdentity | None = None,
    ) -> None:
        """Record move inputs and fail configured targets."""
        self.moves.append((str(source), str(target)))
        self.source_roots.append(None if source_root is None else str(source_root))
        self.target_roots.append(None if target_root is None else str(target_root))
        self.expected_source_identities.append(expected_source_identity)
        run = self._uow.runs.get(RUN_ID)
        plan = self._uow.plans.get(PLAN_ID)
        events = tuple(self._uow.file_events.records.values())
        assert run is not None
        assert plan is not None
        assert len(events) > 0
        self.states_at_move.append((run.status.value, plan.status.value, events[-1].status.value))

        if str(target) in self._failing_targets:
            raise OSError(SENSITIVE_MOVE_FAILURE_DETAIL)

        if str(target) in self._invalid_targets:
            raise ValueError(SENSITIVE_MOVE_FAILURE_DETAIL)

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


def _track(
    *,
    size: int | None = None,
    mtime: datetime | None = None,
) -> Track:
    return Track(
        track_id=TRACK_ID,
        library_id=LIBRARY_ID,
        current_path=LIBRARY_SOURCE_PATH,
        canonical_path=TARGET_PATH,
        content_hash=CONTENT_HASH,
        metadata_hash=METADATA_HASH,
        size=size,
        mtime=mtime,
        metadata=_metadata(),
        status=TrackStatus.ACTIVE,
        first_seen_at=BASE_TIME,
        last_seen_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _snapshot(
    path: str,
    *,
    content_hash: str = CONTENT_HASH,
    metadata_hash: str = METADATA_HASH,
    filesystem_identity: FilesystemIdentity | None = FILESYSTEM_IDENTITY,
) -> FileSnapshot:
    return FileSnapshot(
        path=path,
        size=FILE_SIZE,
        mtime=BASE_TIME,
        file_extension=FILE_EXTENSION,
        content_hash=content_hash,
        metadata_hash=metadata_hash,
        metadata=_metadata(),
        filesystem_identity=filesystem_identity,
        captured_at=BASE_TIME,
    )


def _metadata() -> TrackMetadata:
    return TrackMetadata(title=TRACK_TITLE, artist=TRACK_ARTIST)


def _apply_request(uow: InMemoryUnitOfWork) -> ApplyPlanRequest:
    plan = uow.plans.get(PLAN_ID)
    assert plan is not None
    run = Run(
        run_id=RUN_ID,
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        status=RunStatus.RUNNING,
        started_at=BASE_TIME,
    )
    operation = Operation.queued(
        operation_id=OPERATION_ID,
        kind=OperationKind.APPLY_PLAN,
        idempotency_key=OPERATION_IDEMPOTENCY_KEY,
        request_fingerprint=OPERATION_REQUEST_FINGERPRINT,
        requested_at=BASE_TIME,
        library_id=LIBRARY_ID,
        plan_id=PLAN_ID,
        run_id=RUN_ID,
    )
    assert uow.claim_apply(PLAN_ID, run, operation)
    uow.commit()
    uow.operations.save(operation.mark_running(BASE_TIME))
    uow.commit()
    return _unclaimed_apply_request()


def _unclaimed_apply_request(*, confirmed: bool = True) -> ApplyPlanRequest:
    return ApplyPlanRequest(
        plan_id=PLAN_ID,
        run_id=RUN_ID,
        operation_id=OPERATION_ID,
        options=ApplyOptions(yes=confirmed),
    )


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


def _stored_operation(uow: InMemoryUnitOfWork) -> Operation:
    operation = uow.operations.lookup(OPERATION_ID)
    assert isinstance(operation, Operation)
    return operation


def _stored_library(uow: InMemoryUnitOfWork) -> Library:
    library = uow.libraries.get(LIBRARY_ID)
    assert library is not None
    return library


def _stored_track(uow: InMemoryUnitOfWork) -> Track:
    track = uow.tracks.get(TRACK_ID)
    assert track is not None
    return track
