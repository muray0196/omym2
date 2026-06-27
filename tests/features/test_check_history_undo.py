"""
Summary: Tests check, history, and undo behavior.
Why: Protects diagnostics and recovery without direct file mutation.
"""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from omym2.adapters.config.default_config import default_app_config
from omym2.domain.models.check_issue import CheckIssueType
from omym2.domain.models.file_event import FileEvent, FileEventStatus, FileEventType
from omym2.domain.models.file_scan_entry import FileScanEntry
from omym2.domain.models.file_snapshot import FileSnapshot
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction, PlanActionReason
from omym2.domain.models.run import Run, RunStatus
from omym2.domain.models.track import Track, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.config_fingerprint import calculate_config_fingerprint, calculate_path_policy_fingerprint
from omym2.features.apply.dto import ApplyOptions, ApplyPlanRequest
from omym2.features.apply.ports import ApplyPlanPorts
from omym2.features.apply.usecases.apply_plan import ApplyPlanUseCase
from omym2.features.check.dto import CheckLibraryRequest
from omym2.features.check.ports import CheckLibraryPorts
from omym2.features.check.usecases.check_library import CheckLibraryUseCase
from omym2.features.history.dto import GetRunDetailRequest, ListRunsRequest
from omym2.features.history.ports import HistoryPorts
from omym2.features.history.usecases.get_run_detail import GetRunDetailUseCase
from omym2.features.history.usecases.list_runs import ListRunsUseCase
from omym2.features.undo.dto import CreateUndoPlanRequest
from omym2.features.undo.ports import CreateUndoPlanPorts
from omym2.features.undo.usecases.create_undo_plan import CreateUndoPlanUseCase
from omym2.shared.ids import ActionId, EventId, LibraryId, PlanId, RunId, TrackId
from tests.fakes.in_memory_repositories import InMemoryUnitOfWork
from tests.fakes.runtime import FixedClock, SequenceIdGenerator

if TYPE_CHECKING:
    from omym2.domain.models.app_config import AppConfig
    from omym2.features.common_ports import FileSystemPath

ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567b"))
BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CHANGED_CONTENT_HASH = "changed-content"
CHANGED_METADATA_HASH = "changed-metadata"
CONFIG_HASH = calculate_config_fingerprint(default_app_config())
CONTENT_HASH = "content"
DUPLICATE_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567c"))
EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567e"))
EXTERNAL_SOURCE_PATH = "/incoming/Imported.flac"
FILE_EXTENSION = ".flac"
FILE_SIZE = 5
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
LIBRARY_ROOT = "/music/library"
METADATA_HASH = "metadata"
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567a"))
RESTORE_PATH = "Restore/Imported.flac"
RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567d"))
SECOND_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345680"))
SECOND_EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345681"))
SECOND_PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345682"))
SECOND_RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345683"))
SECOND_TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345684"))
SOURCE_PATH = "Original/Title.flac"
TARGET_PATH = "Artist/2026_Album/1-02_Title.flac"
TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345679"))
UNDO_PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345685"))
UNDO_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345686"))
UNDO_SECOND_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345687"))
UNDO_RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345688"))
UNDO_EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345689"))
UNMANAGED_PATH = "Loose/Copy.flac"

METADATA = TrackMetadata(title="Title", artist="Artist", album="Album", year=2026, track_number=2, disc_number=1)


def test_check_reports_db_filesystem_plan_and_pending_event_issues() -> None:
    """check reports drift without mutating repositories."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.tracks.save(_track(canonical_path=RESTORE_PATH))
    uow.plans.save(_plan())
    uow.plan_actions.save(_source_action())
    uow.runs.save(_run())
    uow.file_events.save(_pending_event())
    scanner = StaticScanner(
        (
            _scan_entry(_absolute(TARGET_PATH)),
            _scan_entry(_absolute(UNMANAGED_PATH)),
        )
    )
    snapshots = MappingSnapshotReader(
        {
            _absolute(TARGET_PATH): _snapshot(_absolute(TARGET_PATH), CHANGED_CONTENT_HASH, CHANGED_METADATA_HASH),
            _absolute(UNMANAGED_PATH): _snapshot(_absolute(UNMANAGED_PATH), CONTENT_HASH, METADATA_HASH),
        }
    )

    issues = CheckLibraryUseCase(_check_ports(uow, scanner, snapshots)).execute(CheckLibraryRequest())

    assert {
        CheckIssueType.CONTENT_HASH_CHANGED,
        CheckIssueType.METADATA_HASH_CHANGED,
        CheckIssueType.CURRENT_PATH_DIFFERS_FROM_CANONICAL_PATH,
        CheckIssueType.UNMANAGED_FILE_EXISTS,
        CheckIssueType.DUPLICATE_CANDIDATE,
        CheckIssueType.PLAN_SOURCE_CHANGED,
        CheckIssueType.PENDING_FILE_EVENT_EXISTS,
    } <= {issue.issue_type for issue in issues}
    assert uow.commit_count == 0


def test_check_reports_missing_file_and_library_state() -> None:
    """check reports missing DB files and non-current Library states."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(status=LibraryStatus.BLOCKED, path_policy_hash="old-policy"))
    uow.tracks.save(_track())
    snapshots = MappingSnapshotReader({}, missing_paths={_absolute(TARGET_PATH)})

    issues = CheckLibraryUseCase(_check_ports(uow, StaticScanner(()), snapshots)).execute(CheckLibraryRequest())

    assert CheckIssueType.DB_FILE_MISSING in {issue.issue_type for issue in issues}
    assert CheckIssueType.LIBRARY_BLOCKED in {issue.issue_type for issue in issues}
    assert CheckIssueType.LIBRARY_STALE in {issue.issue_type for issue in issues}


def test_history_lists_runs_newest_first_and_loads_detail() -> None:
    """history usecases query Runs and FileEvents through repositories."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.runs.save(_run(started_at=BASE_TIME))
    uow.runs.save(_run(run_id=SECOND_RUN_ID, started_at=BASE_TIME + timedelta(minutes=1)))
    uow.file_events.save(_event())
    ports = HistoryPorts(uow)

    runs = ListRunsUseCase(ports).execute(ListRunsRequest())
    detail = GetRunDetailUseCase(ports).execute(GetRunDetailRequest(RUN_ID))

    assert tuple(run.run_id for run in runs) == (SECOND_RUN_ID, RUN_ID)
    assert detail.run.run_id == RUN_ID
    assert tuple(event.event_id for event in detail.file_events) == (EVENT_ID,)


def test_undo_creates_plan_from_succeeded_events_in_reverse_order() -> None:
    """undo reverses succeeded FileEvents and preserves external restore targets."""
    uow = _uow_with_applied_run()
    id_generator = SequenceIdGenerator(
        plan_ids=deque((UNDO_PLAN_ID,)),
        action_ids=deque((UNDO_ACTION_ID, UNDO_SECOND_ACTION_ID)),
    )
    ports = _undo_ports(uow, id_generator=id_generator)

    plan = CreateUndoPlanUseCase(ports).execute(CreateUndoPlanRequest(RUN_ID))

    assert plan.plan_type == PlanType.UNDO
    assert plan.status == PlanStatus.READY
    assert plan.summary["action_count"] == "2"
    assert tuple(action.source_path for action in plan.actions) == (TARGET_PATH, RESTORE_PATH)
    assert tuple(action.target_path for action in plan.actions) == (EXTERNAL_SOURCE_PATH, SOURCE_PATH)
    assert tuple(action.track_id for action in plan.actions) == (TRACK_ID, SECOND_TRACK_ID)
    assert all(action.status == ActionStatus.PLANNED for action in plan.actions)
    assert uow.plans.get(UNDO_PLAN_ID) == plan


def test_apply_persists_generated_track_id_on_add_action_for_later_undo() -> None:
    """Apply stores the new Track identity on the action referenced by FileEvent."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.plans.save(_plan(status=PlanStatus.READY))
    uow.plan_actions.save(_source_action(source_path=EXTERNAL_SOURCE_PATH, target_path=TARGET_PATH, track_id=None))
    ports = ApplyPlanPorts(
        uow=uow,
        file_mover=RecordingFileMover(),
        file_snapshot_reader=MappingSnapshotReader({EXTERNAL_SOURCE_PATH: _snapshot(EXTERNAL_SOURCE_PATH)}),
        path_resolver=SimplePathResolver(),
        clock=FixedClock(BASE_TIME),
        id_generator=SequenceIdGenerator(
            run_ids=deque((RUN_ID,)),
            event_ids=deque((EVENT_ID,)),
            track_ids=deque((TRACK_ID,)),
        ),
    )

    _ = ApplyPlanUseCase(ports).execute(ApplyPlanRequest(PLAN_ID, options=ApplyOptions(yes=True)))

    action = uow.plan_actions.get(ACTION_ID)
    assert action is not None
    assert action.track_id == TRACK_ID


def test_undo_uses_current_track_path_for_import_after_track_moved() -> None:
    """Undo resolves durable Track identity instead of replaying stale FileEvent target paths."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.tracks.save(_track(current_path=RESTORE_PATH))
    uow.tracks.save(_track(track_id=SECOND_TRACK_ID, current_path=TARGET_PATH))
    uow.plans.save(_plan(status=PlanStatus.APPLIED))
    uow.plan_actions.save(_source_action(source_path=EXTERNAL_SOURCE_PATH, target_path=TARGET_PATH, track_id=TRACK_ID))
    uow.runs.save(_run(status=RunStatus.SUCCEEDED))
    uow.file_events.save(_event(source_path=EXTERNAL_SOURCE_PATH, target_path=TARGET_PATH))
    ports = _undo_ports(
        uow,
        id_generator=SequenceIdGenerator(plan_ids=deque((UNDO_PLAN_ID,)), action_ids=deque((UNDO_ACTION_ID,))),
    )

    plan = CreateUndoPlanUseCase(ports).execute(CreateUndoPlanRequest(RUN_ID))

    assert plan.actions[0].source_path == RESTORE_PATH
    assert plan.actions[0].target_path == EXTERNAL_SOURCE_PATH
    assert plan.actions[0].track_id == TRACK_ID
    assert plan.actions[0].status == ActionStatus.PLANNED


def test_undo_blocks_occupied_restore_destination() -> None:
    """undo records target conflicts instead of overwriting destinations."""
    uow = _uow_with_applied_run(second_event=False)
    occupied_target = _absolute(SOURCE_PATH)
    ports = _undo_ports(
        uow,
        id_generator=SequenceIdGenerator(plan_ids=deque((UNDO_PLAN_ID,)), action_ids=deque((UNDO_ACTION_ID,))),
        file_presence=StaticFilePresence({occupied_target}),
    )

    plan = CreateUndoPlanUseCase(ports).execute(CreateUndoPlanRequest(RUN_ID))

    assert len(plan.actions) == 1
    assert plan.actions[0].status == ActionStatus.BLOCKED
    assert plan.actions[0].reason == PlanActionReason.TARGET_EXISTS


def test_apply_external_undo_restore_marks_track_removed() -> None:
    """Applying an external restore never stores the external path on Track."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.tracks.save(_track())
    uow.plans.save(_plan(plan_id=UNDO_PLAN_ID, plan_type=PlanType.UNDO, status=PlanStatus.READY))
    uow.plan_actions.save(
        _source_action(
            action_id=UNDO_ACTION_ID,
            plan_id=UNDO_PLAN_ID,
            source_path=TARGET_PATH,
            target_path=EXTERNAL_SOURCE_PATH,
            track_id=TRACK_ID,
        )
    )
    mover = RecordingFileMover()
    ports = ApplyPlanPorts(
        uow=uow,
        file_mover=mover,
        file_snapshot_reader=MappingSnapshotReader({_absolute(TARGET_PATH): _snapshot(_absolute(TARGET_PATH))}),
        path_resolver=SimplePathResolver(),
        clock=FixedClock(BASE_TIME),
        id_generator=SequenceIdGenerator(run_ids=deque((UNDO_RUN_ID,)), event_ids=deque((UNDO_EVENT_ID,))),
    )

    run = ApplyPlanUseCase(ports).execute(ApplyPlanRequest(UNDO_PLAN_ID, options=ApplyOptions(yes=True)))

    assert run is not None
    assert run.status == RunStatus.SUCCEEDED
    assert mover.moves == [(_absolute(TARGET_PATH), EXTERNAL_SOURCE_PATH)]
    track = uow.tracks.get(TRACK_ID)
    assert track is not None
    assert track.status == TrackStatus.REMOVED
    assert track.current_path == TARGET_PATH


class StaticConfigStore:
    """ConfigStore fake returning one AppConfig."""

    def __init__(self, config: AppConfig | None = None) -> None:
        """Store the config returned by load."""
        self._config: AppConfig = default_app_config() if config is None else config

    def load(self) -> AppConfig:
        """Return the configured AppConfig."""
        return self._config

    def save(self, config: AppConfig) -> None:
        """Replace the configured AppConfig."""
        self._config = config


class StaticScanner:
    """FileScanner fake returning fixed entries."""

    def __init__(self, entries: tuple[FileScanEntry, ...]) -> None:
        """Store scan entries."""
        self._entries: tuple[FileScanEntry, ...] = entries

    def scan(self, root: FileSystemPath) -> tuple[FileScanEntry, ...]:
        """Return fixed entries without touching the filesystem."""
        del root
        return self._entries


class MappingSnapshotReader:
    """FileSnapshotReader fake keyed by filesystem path text."""

    def __init__(self, snapshots: dict[str, FileSnapshot], *, missing_paths: set[str] | None = None) -> None:
        """Store snapshots and paths that should appear missing."""
        self._snapshots: dict[str, FileSnapshot] = snapshots
        self._missing_paths: set[str] = set() if missing_paths is None else set(missing_paths)

    def capture(self, path: FileSystemPath) -> FileSnapshot:
        """Return the configured snapshot for a path."""
        path_text = str(path)
        if path_text in self._missing_paths:
            raise FileNotFoundError(path_text)
        return self._snapshots[path_text]


class StaticFilePresence:
    """FilePresence fake keyed by path text."""

    def __init__(self, existing_paths: set[str] | None = None) -> None:
        """Store paths reported as present."""
        self._existing_paths: set[str] = set() if existing_paths is None else set(existing_paths)

    def exists(self, path: FileSystemPath) -> bool:
        """Return whether the path is configured as present."""
        return str(path) in self._existing_paths


class SimplePathResolver:
    """PathResolver fake joining Library roots and logical paths."""

    def resolve_library_path(self, library_root: FileSystemPath, library_relative_path: str) -> str:
        """Return a filesystem path for a Library-relative path."""
        return f"{str(library_root).rstrip('/')}/{library_relative_path}"

    def relative_to_library(self, library_root: FileSystemPath, path: FileSystemPath) -> str:
        """Return a lexical Library-relative path."""
        return str(path).removeprefix(f"{str(library_root).rstrip('/')}/")


class RecordingFileMover:
    """FileMover fake that records moves."""

    def __init__(self) -> None:
        """Initialize recorded moves."""
        self.moves: list[tuple[str, str]] = []

    def move(self, source: FileSystemPath, target: FileSystemPath) -> None:
        """Record one move."""
        self.moves.append((str(source), str(target)))


def _check_ports(
    uow: InMemoryUnitOfWork,
    scanner: StaticScanner,
    snapshot_reader: MappingSnapshotReader,
) -> CheckLibraryPorts:
    return CheckLibraryPorts(
        uow=uow,
        file_scanner=scanner,
        file_snapshot_reader=snapshot_reader,
        config_store=StaticConfigStore(),
        path_resolver=SimplePathResolver(),
    )


def _undo_ports(
    uow: InMemoryUnitOfWork,
    *,
    id_generator: SequenceIdGenerator,
    file_presence: StaticFilePresence | None = None,
) -> CreateUndoPlanPorts:
    snapshots = {
        _absolute(TARGET_PATH): _snapshot(_absolute(TARGET_PATH)),
        _absolute(RESTORE_PATH): _snapshot(_absolute(RESTORE_PATH)),
    }
    return CreateUndoPlanPorts(
        uow=uow,
        file_snapshot_reader=MappingSnapshotReader(snapshots),
        file_presence=StaticFilePresence() if file_presence is None else file_presence,
        path_resolver=SimplePathResolver(),
        clock=FixedClock(BASE_TIME),
        id_generator=id_generator,
    )


def _uow_with_applied_run(*, second_event: bool = True) -> InMemoryUnitOfWork:
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library())
    uow.tracks.save(_track())
    uow.tracks.save(_track(track_id=SECOND_TRACK_ID, current_path=RESTORE_PATH))
    uow.plans.save(_plan(status=PlanStatus.APPLIED))
    uow.plan_actions.save(_source_action(track_id=SECOND_TRACK_ID))
    uow.plan_actions.save(
        _source_action(
            action_id=SECOND_ACTION_ID,
            source_path=EXTERNAL_SOURCE_PATH,
            target_path=TARGET_PATH,
            track_id=None,
        )
    )
    uow.runs.save(_run(status=RunStatus.SUCCEEDED))
    uow.file_events.save(_event(source_path=SOURCE_PATH, target_path=RESTORE_PATH, plan_action_id=ACTION_ID))
    if second_event:
        uow.file_events.save(
            _event(
                event_id=SECOND_EVENT_ID,
                source_path=EXTERNAL_SOURCE_PATH,
                target_path=TARGET_PATH,
                plan_action_id=SECOND_ACTION_ID,
                sequence_no=2,
            )
        )
    return uow


def _library(
    *,
    status: LibraryStatus = LibraryStatus.REGISTERED,
    path_policy_hash: str | None = None,
) -> Library:
    return Library(
        library_id=LIBRARY_ID,
        root_path=LIBRARY_ROOT,
        path_policy_hash=calculate_path_policy_fingerprint(default_app_config().path_policy)
        if path_policy_hash is None
        else path_policy_hash,
        registered_at=BASE_TIME,
        status=status,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _track(
    *,
    track_id: TrackId = TRACK_ID,
    current_path: str = TARGET_PATH,
    canonical_path: str = TARGET_PATH,
    status: TrackStatus = TrackStatus.ACTIVE,
) -> Track:
    return Track(
        track_id=track_id,
        library_id=LIBRARY_ID,
        current_path=current_path,
        canonical_path=canonical_path,
        content_hash=CONTENT_HASH,
        metadata_hash=METADATA_HASH,
        metadata=METADATA,
        status=status,
        first_seen_at=BASE_TIME,
        last_seen_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _plan(
    *,
    plan_id: PlanId = PLAN_ID,
    plan_type: PlanType = PlanType.ADD,
    status: PlanStatus = PlanStatus.READY,
) -> Plan:
    return Plan(
        plan_id=plan_id,
        library_id=LIBRARY_ID,
        plan_type=plan_type,
        status=status,
        created_at=BASE_TIME,
        config_hash=CONFIG_HASH,
        library_root_at_plan=LIBRARY_ROOT,
        summary={"action_count": "1"},
    )


def _source_action(
    *,
    action_id: ActionId = ACTION_ID,
    plan_id: PlanId = PLAN_ID,
    source_path: str = TARGET_PATH,
    target_path: str = RESTORE_PATH,
    track_id: TrackId | None = TRACK_ID,
) -> PlanAction:
    return PlanAction(
        action_id=action_id,
        plan_id=plan_id,
        library_id=LIBRARY_ID,
        track_id=track_id,
        action_type=ActionType.MOVE,
        source_path=source_path,
        target_path=target_path,
        content_hash_at_plan=CONTENT_HASH,
        metadata_hash_at_plan=METADATA_HASH,
        status=ActionStatus.PLANNED,
        reason=None,
        sort_order=1,
    )


def _run(
    *,
    run_id: RunId = RUN_ID,
    status: RunStatus = RunStatus.RUNNING,
    started_at: datetime = BASE_TIME,
) -> Run:
    return Run(
        run_id=run_id,
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        status=status,
        started_at=started_at,
    )


def _event(
    *,
    event_id: EventId = EVENT_ID,
    source_path: str = SOURCE_PATH,
    target_path: str = TARGET_PATH,
    plan_action_id: ActionId = ACTION_ID,
    sequence_no: int = 1,
) -> FileEvent:
    return FileEvent(
        event_id=event_id,
        library_id=LIBRARY_ID,
        run_id=RUN_ID,
        plan_action_id=plan_action_id,
        event_type=FileEventType.MOVE_FILE,
        source_path=source_path,
        target_path=target_path,
        status=FileEventStatus.SUCCEEDED,
        started_at=BASE_TIME,
        completed_at=BASE_TIME,
        error_code=None,
        error_message=None,
        sequence_no=sequence_no,
    )


def _pending_event() -> FileEvent:
    return FileEvent(
        event_id=EVENT_ID,
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
        sequence_no=1,
    )


def _scan_entry(path: str) -> FileScanEntry:
    return FileScanEntry(path=path, size=FILE_SIZE, mtime=BASE_TIME, file_extension=FILE_EXTENSION)


def _snapshot(
    path: str,
    content_hash: str = CONTENT_HASH,
    metadata_hash: str = METADATA_HASH,
) -> FileSnapshot:
    return FileSnapshot(
        path=path,
        size=FILE_SIZE,
        mtime=BASE_TIME,
        file_extension=FILE_EXTENSION,
        content_hash=content_hash,
        metadata_hash=metadata_hash,
        metadata=METADATA,
        captured_at=BASE_TIME,
    )


def _absolute(relative_path: str) -> str:
    return f"{LIBRARY_ROOT}/{relative_path}"
