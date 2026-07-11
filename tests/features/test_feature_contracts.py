"""
Summary: Tests feature contracts and fakes.
Why: Protects port boundaries before concrete adapters are implemented.
"""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

import pytest

from omym2.adapters.config.default_config import default_app_config
from omym2.config import UUID_VERSION
from omym2.domain.models.file_event import FileEvent, FileEventStatus, FileEventType
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction
from omym2.domain.models.run import Run, RunStatus
from omym2.domain.models.track import Track, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.features.check.dto import CheckLibraryRequest
from omym2.features.check.ports import CheckLibraryPorts
from omym2.features.check.usecases.check_library import CheckLibraryUseCase
from omym2.features.common_ports import FileSnapshotCaptureRequest, FileSystemPath, Uuid7IdGenerator
from omym2.features.history.dto import GetRunHeaderRequest, ListRunsRequest
from omym2.features.history.ports import HistoryPorts
from omym2.features.history.usecases.get_run_header import GetRunHeaderUseCase, RunNotFoundError
from omym2.features.history.usecases.list_runs import ListRunsUseCase
from omym2.features.undo.dto import CreateUndoPlanRequest
from omym2.features.undo.ports import CreateUndoPlanPorts
from omym2.features.undo.usecases.create_undo_plan import CreateUndoPlanUseCase, UndoPlanError
from omym2.shared.ids import ActionId, EventId, LibraryId, PlanId, RunId, TrackId, is_uuid7
from tests.fakes.in_memory_repositories import InMemoryUnitOfWork
from tests.fakes.runtime import EMPTY_SEQUENCE_MESSAGE, FixedClock, SequenceIdGenerator

if TYPE_CHECKING:
    from collections.abc import Sequence

    from omym2.domain.models.app_config import AppConfig
    from omym2.domain.models.file_scan_entry import FileScanEntry
    from omym2.domain.models.file_snapshot import FileSnapshot

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CONFIG_HASH = "config-hash"
CONTENT_HASH = "content-hash"
ERROR_MESSAGE = "expected transaction failure"
EVENT_SEQUENCE_EARLY = 1
EVENT_SEQUENCE_LATE = 2
EVENT_SEQUENCE_THIRD = 3
EVENT_SEQUENCE_FOURTH = 4
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
UNEXPECTED_IO_MESSAGE = "Feature contract tests must not call I/O fakes."

LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345679"))
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567a"))
ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567b"))
LATE_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567c"))
RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567d"))
EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567e"))
LATE_EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567f"))
SECOND_RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345680"))
SECOND_RUN_EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345681"))
SUCCEEDED_EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345682"))
OTHER_LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345683"))
OTHER_RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345684"))
OTHER_EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345685"))


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
    """Repository fakes support the query shapes usecases need."""
    uow = InMemoryUnitOfWork()
    library = _library()
    track = _track()
    plan = _plan()
    action_late = _plan_action(LATE_ACTION_ID, SORT_ORDER_LATE)
    action_early = _plan_action(ACTION_ID, SORT_ORDER_EARLY)
    run = _run()
    event_late = _file_event(LATE_EVENT_ID, EVENT_SEQUENCE_LATE)
    event_early = _file_event(EVENT_ID, EVENT_SEQUENCE_EARLY)
    event_succeeded = _file_event(SUCCEEDED_EVENT_ID, EVENT_SEQUENCE_THIRD, run_id=SECOND_RUN_ID).mark_succeeded(
        BASE_TIME
    )
    event_second_run = _file_event(SECOND_RUN_EVENT_ID, EVENT_SEQUENCE_FOURTH, run_id=SECOND_RUN_ID)
    event_other_library = _file_event(
        OTHER_EVENT_ID, EVENT_SEQUENCE_EARLY, library_id=OTHER_LIBRARY_ID, run_id=OTHER_RUN_ID
    )

    uow.libraries.save(library)
    uow.tracks.save(track)
    uow.plans.save(plan)
    uow.plan_actions.save(action_late)
    uow.plan_actions.save(action_early)
    uow.runs.save(run)
    uow.file_events.save(event_late)
    uow.file_events.save(event_early)
    uow.file_events.save(event_succeeded)
    uow.file_events.save(event_second_run)
    uow.file_events.save(event_other_library)

    assert uow.libraries.get(LIBRARY_ID) == library
    assert uow.libraries.find_by_root_path(LIBRARY_ROOT) == library
    assert uow.tracks.list_by_library(LIBRARY_ID) == (track,)
    assert uow.plans.list_by_library(LIBRARY_ID) == (plan,)
    assert uow.plan_actions.list_by_plan(PLAN_ID) == (action_early, action_late)
    assert uow.runs.list_by_plan(PLAN_ID) == (run,)
    assert uow.runs.list_by_library(LIBRARY_ID) == (run,)
    assert uow.file_events.list_by_run(RUN_ID) == (event_early, event_late)
    assert uow.file_events.list_pending_by_library(LIBRARY_ID) == (event_early, event_late, event_second_run)
    assert uow.file_events.list_pending_by_library(OTHER_LIBRARY_ID) == (event_other_library,)


def test_in_memory_unit_of_work_records_commit_and_rollback_intent() -> None:
    """The UnitOfWork fake exposes transaction calls for later usecase tests."""
    uow = InMemoryUnitOfWork()

    with uow:
        uow.commit()

    assert uow.commit_count == EXPECTED_ONE_CALL

    with pytest.raises(RuntimeError, match=ERROR_MESSAGE), uow:
        raise RuntimeError(ERROR_MESSAGE)

    assert uow.rollback_count == EXPECTED_ONE_CALL


def test_diagnostics_and_recovery_usecases_handle_empty_repository_contracts() -> None:
    """Diagnostics and recovery usecases are instantiable through their ports."""
    uow = InMemoryUnitOfWork()
    scanner = NoopFileScanner()
    snapshot_reader = NoopFileSnapshotReader()
    content_hasher = NoopFileContentHasher()
    config_store = StaticConfigStore()
    path_resolver = NoopPathResolver()
    file_presence = NoopFilePresence()
    clock = FixedClock(BASE_TIME)
    id_generator = SequenceIdGenerator()

    assert (
        CheckLibraryUseCase(
            CheckLibraryPorts(
                uow,
                scanner,
                snapshot_reader,
                content_hasher,
                config_store,
                path_resolver,
                clock,
                id_generator,
            )
        )
        .execute(CheckLibraryRequest(trust_stat=False))
        .issues
        == ()
    )
    assert ListRunsUseCase(HistoryPorts(uow)).execute(ListRunsRequest()).items == ()

    with pytest.raises(RunNotFoundError):
        _ = GetRunHeaderUseCase(HistoryPorts(uow)).execute(GetRunHeaderRequest(RUN_ID))

    with pytest.raises(UndoPlanError):
        _ = CreateUndoPlanUseCase(
            CreateUndoPlanPorts(uow, snapshot_reader, file_presence, path_resolver, clock, id_generator)
        ).execute(CreateUndoPlanRequest(RUN_ID))


class NoopFileScanner:
    """FileScanner fake that proves skeletons do not scan yet."""

    def scan(self, root: FileSystemPath) -> tuple[FileScanEntry, ...]:
        """Fail if a skeleton unexpectedly reaches filesystem discovery."""
        del root
        raise AssertionError(UNEXPECTED_IO_MESSAGE)


class NoopFileSnapshotReader:
    """FileSnapshotReader fake that proves skeletons do not capture yet."""

    def capture(
        self,
        path: FileSystemPath,
        *,
        observation: FileScanEntry | None = None,
    ) -> FileSnapshot:
        """Fail if a skeleton unexpectedly reaches file observation."""
        del path, observation
        raise AssertionError(UNEXPECTED_IO_MESSAGE)

    def capture_many(
        self,
        requests: Sequence[FileSnapshotCaptureRequest],
    ) -> tuple[FileSnapshot | None, ...]:
        """Allow empty batches while rejecting any unexpected filesystem observation."""
        if len(requests) > 0:
            raise AssertionError(UNEXPECTED_IO_MESSAGE)
        return ()


class NoopFileContentHasher:
    """FileContentHasher fake that proves empty checks do not hash."""

    def calculate(self, path: FileSystemPath) -> str:
        """Fail if an empty repository unexpectedly reaches content hashing."""
        del path
        raise AssertionError(UNEXPECTED_IO_MESSAGE)


class NoopFilePresence:
    """FilePresence fake that proves empty repository undo does not inspect paths."""

    def exists(self, path: FileSystemPath) -> bool:
        """Fail if empty repository undo unexpectedly checks a path."""
        del path
        raise AssertionError(UNEXPECTED_IO_MESSAGE)


class NoopPathResolver:
    """PathResolver fake that proves empty repository checks do not resolve paths."""

    def resolve_library_path(self, library_root: FileSystemPath, library_relative_path: str) -> str:
        """Fail if empty repository logic unexpectedly resolves a path."""
        del library_root, library_relative_path
        raise AssertionError(UNEXPECTED_IO_MESSAGE)

    def relative_to_library(self, library_root: FileSystemPath, path: FileSystemPath) -> str:
        """Fail if empty repository logic unexpectedly relativizes a path."""
        del library_root, path
        raise AssertionError(UNEXPECTED_IO_MESSAGE)


class StaticConfigStore:
    """ConfigStore fake that returns defaults."""

    def load(self) -> AppConfig:
        """Return the default AppConfig."""
        return default_app_config()

    def save(self, config: AppConfig) -> None:
        """Accept config saves for protocol completeness."""
        del config


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
        size=None,
        mtime=None,
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


def _file_event(
    event_id: EventId,
    sequence_no: int,
    *,
    library_id: LibraryId = LIBRARY_ID,
    run_id: RunId = RUN_ID,
) -> FileEvent:
    return FileEvent(
        event_id=event_id,
        library_id=library_id,
        run_id=run_id,
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
