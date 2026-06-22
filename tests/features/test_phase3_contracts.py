"""
Summary: Tests Phase 3 feature contracts and fakes.
Why: Protects port boundaries before concrete adapters are implemented.
"""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

import pytest

from omym2.config import UUID_VERSION
from omym2.domain.models.file_event import FileEvent, FileEventStatus, FileEventType
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction
from omym2.domain.models.run import Run, RunStatus
from omym2.domain.models.track import Track, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.features.add.dto import CreateAddPlanRequest
from omym2.features.add.ports import CreateAddPlanPorts
from omym2.features.add.usecases.create_add_plan import CreateAddPlanUseCase
from omym2.features.apply.dto import ApplyPlanRequest
from omym2.features.apply.ports import ApplyPlanPorts
from omym2.features.apply.usecases.apply_plan import ApplyPlanUseCase
from omym2.features.check.dto import CheckLibraryRequest
from omym2.features.check.ports import CheckLibraryPorts
from omym2.features.check.usecases.check_library import CheckLibraryUseCase
from omym2.features.common_ports import FileSystemPath, Uuid7IdGenerator
from omym2.features.history.dto import GetRunDetailRequest, ListRunsRequest
from omym2.features.history.ports import HistoryPorts
from omym2.features.history.usecases.get_run_detail import GetRunDetailUseCase
from omym2.features.history.usecases.list_runs import ListRunsUseCase
from omym2.features.inspect.dto import InspectFileRequest
from omym2.features.inspect.ports import InspectFilePorts
from omym2.features.inspect.usecases.inspect_file import InspectFileUseCase
from omym2.features.organize.dto import CreateOrganizePlanRequest
from omym2.features.organize.ports import CreateOrganizePlanPorts
from omym2.features.organize.usecases.create_organize_plan import CreateOrganizePlanUseCase
from omym2.features.refresh.dto import CreateRefreshPlanRequest
from omym2.features.refresh.ports import CreateRefreshPlanPorts
from omym2.features.refresh.usecases.create_refresh_plan import CreateRefreshPlanUseCase
from omym2.features.undo.dto import CreateUndoPlanRequest
from omym2.features.undo.ports import CreateUndoPlanPorts
from omym2.features.undo.usecases.create_undo_plan import CreateUndoPlanUseCase
from omym2.shared.ids import ActionId, EventId, LibraryId, PlanId, RunId, TrackId, is_uuid7
from tests.fakes.in_memory_repositories import InMemoryUnitOfWork
from tests.fakes.runtime import EMPTY_SEQUENCE_MESSAGE, FixedClock, SequenceIdGenerator

if TYPE_CHECKING:
    from collections.abc import Callable

    from omym2.domain.models.file_scan_entry import FileScanEntry
    from omym2.domain.models.file_snapshot import FileSnapshot

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CONFIG_HASH = "config-hash"
CONTENT_HASH = "content-hash"
ERROR_MESSAGE = "expected transaction failure"
EVENT_SEQUENCE_EARLY = 1
EVENT_SEQUENCE_LATE = 2
EXPECTED_ONE_CALL = 1
FILE_EXTENSION = ".flac"
LIBRARY_ROOT = "/music/library"
METADATA_HASH = "metadata-hash"
PLAN_SUMMARY = {"moves": "1"}
SORT_ORDER_EARLY = 1
SORT_ORDER_LATE = 2
SOURCE_PATH = "/incoming/song.flac"
TARGET_PATH = "Artist/Album/01_Title.flac"
TRACK_TITLE = "Title"
TRACK_ARTIST = "Artist"
UNEXPECTED_IO_MESSAGE = "Phase 3 skeleton tests must not call I/O fakes."

LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345679"))
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567a"))
ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567b"))
LATE_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567c"))
RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567d"))
EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567e"))
LATE_EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567f"))


def test_uuid7_id_generator_returns_documented_id_versions() -> None:
    """Uuid7IdGenerator creates UUIDv7 values for every stable ID type."""
    generator = Uuid7IdGenerator()

    generated_ids = (
        generator.new_library_id(),
        generator.new_track_id(),
        generator.new_plan_id(),
        generator.new_action_id(),
        generator.new_run_id(),
        generator.new_event_id(),
    )

    for generated_id in generated_ids:
        assert isinstance(generated_id, UUID)
        assert generated_id.version == UUID_VERSION
        assert is_uuid7(generated_id)


def test_fixed_clock_and_sequence_id_generator_are_deterministic() -> None:
    """Runtime fakes return caller-supplied time and IDs."""
    id_generator = SequenceIdGenerator(
        library_ids=deque((LIBRARY_ID,)),
        track_ids=deque((TRACK_ID,)),
        plan_ids=deque((PLAN_ID,)),
        action_ids=deque((ACTION_ID,)),
        run_ids=deque((RUN_ID,)),
        event_ids=deque((EVENT_ID,)),
    )

    assert FixedClock(BASE_TIME).now() == BASE_TIME
    assert id_generator.new_library_id() == LIBRARY_ID
    assert id_generator.new_track_id() == TRACK_ID
    assert id_generator.new_plan_id() == PLAN_ID
    assert id_generator.new_action_id() == ACTION_ID
    assert id_generator.new_run_id() == RUN_ID
    assert id_generator.new_event_id() == EVENT_ID

    with pytest.raises(AssertionError, match=EMPTY_SEQUENCE_MESSAGE):
        _ = id_generator.new_library_id()


def test_in_memory_repositories_store_models_by_usecase_query_shape() -> None:
    """Repository fakes support the Phase 3 query shapes usecases need."""
    uow = InMemoryUnitOfWork()
    library = _library()
    track = _track()
    plan = _plan()
    action_late = _plan_action(LATE_ACTION_ID, SORT_ORDER_LATE)
    action_early = _plan_action(ACTION_ID, SORT_ORDER_EARLY)
    run = _run()
    event_late = _file_event(LATE_EVENT_ID, EVENT_SEQUENCE_LATE)
    event_early = _file_event(EVENT_ID, EVENT_SEQUENCE_EARLY)

    uow.libraries.save(library)
    uow.tracks.save(track)
    uow.plans.save(plan)
    uow.plan_actions.save(action_late)
    uow.plan_actions.save(action_early)
    uow.runs.save(run)
    uow.file_events.save(event_late)
    uow.file_events.save(event_early)

    assert uow.libraries.get(LIBRARY_ID) == library
    assert uow.libraries.find_by_root_path(LIBRARY_ROOT) == library
    assert uow.tracks.list_by_library(LIBRARY_ID) == (track,)
    assert uow.tracks.find_by_content_hash(LIBRARY_ID, CONTENT_HASH) == (track,)
    assert uow.plans.list_by_library(LIBRARY_ID) == (plan,)
    assert uow.plan_actions.list_by_plan(PLAN_ID) == (action_early, action_late)
    assert uow.runs.list_by_plan(PLAN_ID) == (run,)
    assert uow.runs.list_by_library(LIBRARY_ID) == (run,)
    assert uow.file_events.list_by_run(RUN_ID) == (event_early, event_late)


def test_in_memory_unit_of_work_records_commit_and_rollback_intent() -> None:
    """The UnitOfWork fake exposes transaction calls for later usecase tests."""
    uow = InMemoryUnitOfWork()

    with uow:
        uow.commit()

    assert uow.commit_count == EXPECTED_ONE_CALL

    with pytest.raises(RuntimeError, match=ERROR_MESSAGE), uow:
        raise RuntimeError(ERROR_MESSAGE)

    assert uow.rollback_count == EXPECTED_ONE_CALL


def test_phase3_usecase_skeletons_define_contracts_without_behavior() -> None:
    """Usecase skeletons are instantiable but defer vertical-slice behavior."""
    uow = InMemoryUnitOfWork()
    scanner = NoopFileScanner()
    snapshot_reader = NoopFileSnapshotReader()
    mover = NoopFileMover()
    clock = FixedClock(BASE_TIME)
    id_generator = SequenceIdGenerator()

    exercises: tuple[Callable[[], object], ...] = (
        lambda: CreateOrganizePlanUseCase(
            CreateOrganizePlanPorts(uow, scanner, snapshot_reader, clock, id_generator)
        ).execute(CreateOrganizePlanRequest(library_root=LIBRARY_ROOT)),
        lambda: CreateAddPlanUseCase(CreateAddPlanPorts(uow, scanner, snapshot_reader, clock, id_generator)).execute(
            CreateAddPlanRequest(SOURCE_PATH)
        ),
        lambda: ApplyPlanUseCase(ApplyPlanPorts(uow, mover, snapshot_reader, clock, id_generator)).execute(
            ApplyPlanRequest(PLAN_ID)
        ),
        lambda: CreateRefreshPlanUseCase(CreateRefreshPlanPorts(uow, snapshot_reader, clock, id_generator)).execute(
            CreateRefreshPlanRequest(library_id=LIBRARY_ID)
        ),
        lambda: CheckLibraryUseCase(CheckLibraryPorts(uow, scanner, snapshot_reader)).execute(
            CheckLibraryRequest(LIBRARY_ID)
        ),
        lambda: ListRunsUseCase(HistoryPorts(uow)).execute(ListRunsRequest(LIBRARY_ID)),
        lambda: GetRunDetailUseCase(HistoryPorts(uow)).execute(GetRunDetailRequest(RUN_ID)),
        lambda: CreateUndoPlanUseCase(CreateUndoPlanPorts(uow, clock, id_generator)).execute(
            CreateUndoPlanRequest(RUN_ID)
        ),
        lambda: InspectFileUseCase(InspectFilePorts(snapshot_reader)).execute(InspectFileRequest(SOURCE_PATH)),
    )

    for exercise in exercises:
        with pytest.raises(NotImplementedError):
            _ = exercise()


class NoopFileScanner:
    """FileScanner fake that proves skeletons do not scan yet."""

    def scan(self, root: FileSystemPath) -> tuple[FileScanEntry, ...]:
        """Fail if a skeleton unexpectedly reaches filesystem discovery."""
        del root
        raise AssertionError(UNEXPECTED_IO_MESSAGE)


class NoopFileSnapshotReader:
    """FileSnapshotReader fake that proves skeletons do not capture yet."""

    def capture(self, path: FileSystemPath) -> FileSnapshot:
        """Fail if a skeleton unexpectedly reaches file observation."""
        del path
        raise AssertionError(UNEXPECTED_IO_MESSAGE)


class NoopFileMover:
    """FileMover fake that proves skeletons do not mutate files yet."""

    def move(self, source: FileSystemPath, target: FileSystemPath) -> None:
        """Fail if a skeleton unexpectedly reaches file mutation."""
        del source, target
        raise AssertionError(UNEXPECTED_IO_MESSAGE)


def _library() -> Library:
    return Library(
        library_id=LIBRARY_ID,
        root_path=LIBRARY_ROOT,
        path_policy_hash=CONFIG_HASH,
        registered_at=BASE_TIME,
        status=LibraryStatus.REGISTERED,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _track() -> Track:
    return Track(
        track_id=TRACK_ID,
        library_id=LIBRARY_ID,
        current_path=TARGET_PATH,
        canonical_path=TARGET_PATH,
        content_hash=CONTENT_HASH,
        metadata_hash=METADATA_HASH,
        metadata=TrackMetadata(title=TRACK_TITLE, artist=TRACK_ARTIST),
        status=TrackStatus.ACTIVE,
        first_seen_at=BASE_TIME,
        last_seen_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _plan() -> Plan:
    return Plan(
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        plan_type=PlanType.ADD,
        status=PlanStatus.READY,
        created_at=BASE_TIME,
        config_hash=CONFIG_HASH,
        library_root_at_plan=LIBRARY_ROOT,
        summary=PLAN_SUMMARY,
    )


def _plan_action(action_id: ActionId, sort_order: int) -> PlanAction:
    return PlanAction(
        action_id=action_id,
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        track_id=TRACK_ID,
        action_type=ActionType.MOVE,
        source_path=SOURCE_PATH,
        target_path=TARGET_PATH,
        content_hash_at_plan=CONTENT_HASH,
        metadata_hash_at_plan=METADATA_HASH,
        status=ActionStatus.PLANNED,
        reason=None,
        sort_order=sort_order,
    )


def _run() -> Run:
    return Run(
        run_id=RUN_ID,
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        status=RunStatus.RUNNING,
        started_at=BASE_TIME,
    )


def _file_event(event_id: EventId, sequence_no: int) -> FileEvent:
    return FileEvent(
        event_id=event_id,
        library_id=LIBRARY_ID,
        run_id=RUN_ID,
        plan_action_id=ACTION_ID,
        event_type=FileEventType.MOVE_FILE,
        source_path=SOURCE_PATH,
        target_path=TARGET_PATH,
        status=FileEventStatus.PENDING,
        started_at=BASE_TIME,
        completed_at=None,
        error_code=None,
        error_message=None,
        sequence_no=sequence_no,
    )
