"""
Summary: Tests companion workflows across concrete filesystem and SQLite adapters.
Why: Protects Stage 4 companion ownership, history, and Undo as one durable contract.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

import pytest

from omym2.adapters.config.default_config import default_app_config
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.adapters.fs.file_content_snapshot_reader import FilesystemFileContentSnapshotReader
from omym2.adapters.fs.file_mover import FilesystemFileMover
from omym2.adapters.fs.file_presence import FilesystemFilePresence
from omym2.adapters.fs.file_scanner import FilesystemFileScanner
from omym2.adapters.fs.file_snapshot_reader import FilesystemFileSnapshotReader
from omym2.adapters.fs.hash_calculator import FileContentHasher
from omym2.adapters.fs.path_resolver import FilesystemPathResolver
from omym2.adapters.fs.source_inventory_reader import FilesystemSourceInventoryReader
from omym2.domain.models.app_config import AppConfig, CompanionsConfig
from omym2.domain.models.check_issue import CheckIssueType
from omym2.domain.models.companion_asset import CompanionAssetKind, CompanionAssetStatus
from omym2.domain.models.file_event import FileEventStatus, FileEventType
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.operation import Operation, OperationStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction, PlanActionReason
from omym2.domain.models.run import Run, RunStatus
from omym2.domain.models.track import TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.config_fingerprint import calculate_path_policy_fingerprint
from omym2.features.add.dto import CreateAddPlanRequest
from omym2.features.add.ports import CreateAddPlanPorts
from omym2.features.add.usecases.create_add_plan import CreateAddPlanUseCase
from omym2.features.apply.dto import ApplyOptions, ApplyPlanRequest, ClaimApplyRequest
from omym2.features.apply.ports import ApplyPlanPorts
from omym2.features.apply.usecases.apply_plan import ApplyPlanUseCase
from omym2.features.apply.usecases.claim_apply import ClaimApplyUseCase
from omym2.features.check.dto import CheckLibraryRequest
from omym2.features.check.ports import CheckLibraryPorts
from omym2.features.check.usecases.check_library import CheckLibraryUseCase
from omym2.features.history.dto import GetRunHeaderRequest, ListRunEventsRequest, ListRunsRequest
from omym2.features.history.ports import HistoryPorts
from omym2.features.history.usecases.get_run_header import GetRunHeaderUseCase
from omym2.features.history.usecases.list_run_events import ListRunEventsUseCase
from omym2.features.history.usecases.list_runs import ListRunsUseCase
from omym2.features.undo.dto import CreateUndoPlanRequest
from omym2.features.undo.ports import CreateUndoPlanPorts
from omym2.features.undo.usecases.create_undo_plan import CreateUndoPlanUseCase
from omym2.shared.ids import (
    ActionId,
    CheckRunId,
    CompanionAssetId,
    EventId,
    LibraryId,
    OperationId,
    PlanId,
    RunId,
    TrackId,
)
from tests.fakes.runtime import FixedClock, MappingArtistNameResolver, SequenceIdGenerator

if TYPE_CHECKING:
    from collections.abc import Mapping

    from omym2.domain.models.file_snapshot import FilesystemIdentity
    from omym2.features.common_ports import FileMover, FileSystemPath

PLAN_TIME = datetime(2026, 7, 16, tzinfo=UTC)
ADD_APPLY_TIME = PLAN_TIME + timedelta(seconds=1)
CHECK_TIME = PLAN_TIME + timedelta(seconds=2)
UNDO_PLAN_TIME = PLAN_TIME + timedelta(seconds=3)
UNDO_APPLY_TIME = PLAN_TIME + timedelta(seconds=4)
RECOVERY_PLAN_TIME = PLAN_TIME + timedelta(seconds=3)
RECOVERY_APPLY_TIME = PLAN_TIME + timedelta(seconds=4)
FIRST_RECOVERY_UNDO_PLAN_TIME = PLAN_TIME + timedelta(seconds=5)
FIRST_RECOVERY_UNDO_APPLY_TIME = PLAN_TIME + timedelta(seconds=6)
SECOND_RECOVERY_UNDO_PLAN_TIME = PLAN_TIME + timedelta(seconds=7)
SECOND_RECOVERY_UNDO_APPLY_TIME = PLAN_TIME + timedelta(seconds=8)

AUDIO_ONE_CONTENT = b"first audio"
AUDIO_TWO_CONTENT = b"second audio"
LYRICS_CONTENT = b"[00:00.00] First lyrics\n"
ARTWORK_CONTENT = b"stage-four-artwork"
TARGET_SENTINEL_CONTENT = b"must not be overwritten"
FIRST_TRACK_NUMBER = 1
SECOND_TRACK_NUMBER = 2
METADATA_YEAR = 2026
DISC_NUMBER = 1
LYRICS_EXTENSION = ".lrc"
EXPECTED_ACTION_COUNT = 4
EXPECTED_AUDIO_COUNT = 2
EXPECTED_COMPANION_COUNT = 2
EXPECTED_CRASH_EVENT_COUNT = 3

LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012347001"))
ADD_PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012347002"))
ADD_ACTION_IDS: tuple[ActionId, ...] = tuple(
    ActionId(UUID(value))
    for value in (
        "018f6a4f-3c2d-7b8a-9abc-def012347003",
        "018f6a4f-3c2d-7b8a-9abc-def012347004",
        "018f6a4f-3c2d-7b8a-9abc-def012347005",
        "018f6a4f-3c2d-7b8a-9abc-def012347006",
    )
)
COMPANION_ASSET_IDS: tuple[CompanionAssetId, ...] = (
    CompanionAssetId(UUID("018f6a4f-3c2d-7b8a-9abc-def012347007")),
    CompanionAssetId(UUID("018f6a4f-3c2d-7b8a-9abc-def012347008")),
)
ADD_RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012347009"))
ADD_OPERATION_ID = OperationId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234700a"))
ADD_EVENT_IDS: tuple[EventId, ...] = tuple(
    EventId(UUID(value))
    for value in (
        "018f6a4f-3c2d-7b8a-9abc-def01234700b",
        "018f6a4f-3c2d-7b8a-9abc-def01234700c",
        "018f6a4f-3c2d-7b8a-9abc-def01234700d",
        "018f6a4f-3c2d-7b8a-9abc-def01234700e",
    )
)
TRACK_IDS: tuple[TrackId, ...] = (
    TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234700f")),
    TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012347010")),
)
CHECK_RUN_ID = CheckRunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012347011"))
UNDO_PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012347012"))
UNDO_ACTION_IDS: tuple[ActionId, ...] = tuple(
    ActionId(UUID(value))
    for value in (
        "018f6a4f-3c2d-7b8a-9abc-def012347013",
        "018f6a4f-3c2d-7b8a-9abc-def012347014",
        "018f6a4f-3c2d-7b8a-9abc-def012347015",
        "018f6a4f-3c2d-7b8a-9abc-def012347016",
    )
)
UNDO_RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012347017"))
UNDO_OPERATION_ID = OperationId(UUID("018f6a4f-3c2d-7b8a-9abc-def012347018"))
UNDO_EVENT_IDS: tuple[EventId, ...] = tuple(
    EventId(UUID(value))
    for value in (
        "018f6a4f-3c2d-7b8a-9abc-def012347019",
        "018f6a4f-3c2d-7b8a-9abc-def01234701a",
        "018f6a4f-3c2d-7b8a-9abc-def01234701b",
        "018f6a4f-3c2d-7b8a-9abc-def01234701c",
    )
)
RECOVERY_PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012347020"))
RECOVERY_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def012347021"))
RECOVERY_RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012347022"))
RECOVERY_OPERATION_ID = OperationId(UUID("018f6a4f-3c2d-7b8a-9abc-def012347023"))
RECOVERY_EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def012347024"))
ORIGINAL_RECOVERY_UNDO_PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012347025"))
ORIGINAL_RECOVERY_UNDO_ACTION_IDS: tuple[ActionId, ...] = tuple(
    ActionId(UUID(value))
    for value in (
        "018f6a4f-3c2d-7b8a-9abc-def012347026",
        "018f6a4f-3c2d-7b8a-9abc-def012347027",
        "018f6a4f-3c2d-7b8a-9abc-def012347028",
    )
)
ORIGINAL_RECOVERY_UNDO_RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012347029"))
ORIGINAL_RECOVERY_UNDO_OPERATION_ID = OperationId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234702a"))
ORIGINAL_RECOVERY_UNDO_EVENT_IDS: tuple[EventId, ...] = tuple(
    EventId(UUID(value))
    for value in (
        "018f6a4f-3c2d-7b8a-9abc-def01234702b",
        "018f6a4f-3c2d-7b8a-9abc-def01234702c",
        "018f6a4f-3c2d-7b8a-9abc-def01234702d",
    )
)
RECOVERED_UNDO_PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234702e"))
RECOVERED_UNDO_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234702f"))
RECOVERED_UNDO_RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012347030"))
RECOVERED_UNDO_OPERATION_ID = OperationId(UUID("018f6a4f-3c2d-7b8a-9abc-def012347031"))
RECOVERED_UNDO_EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def012347032"))


@dataclass(frozen=True, slots=True)
class StaticConfigStore:
    """Return one immutable config through the read-only config port."""

    config: AppConfig

    def load(self) -> AppConfig:
        """Return the configured Stage 4 settings."""
        return self.config


@dataclass(frozen=True, slots=True)
class MetadataByContentReader:
    """Read deterministic metadata after files move to different paths."""

    metadata_by_content: Mapping[bytes, TrackMetadata]

    def read(self, path: FileSystemPath) -> TrackMetadata:
        """Return metadata selected by immutable test file bytes."""
        return self.metadata_by_content[Path(path).read_bytes()]


@dataclass(frozen=True, slots=True)
class CompanionAdapterSetup:
    """Concrete storage roots and deterministic boundary fakes for one scenario."""

    database_file: Path
    library_root: Path
    incoming_root: Path
    first_audio: Path
    second_audio: Path
    lyrics: Path
    artwork: Path
    config_store: StaticConfigStore
    metadata_reader: MetadataByContentReader

    def snapshot_reader(self, timestamp: datetime) -> FilesystemFileSnapshotReader:
        """Return the real snapshot adapter with deterministic metadata and time."""
        return FilesystemFileSnapshotReader(
            metadata_reader=self.metadata_reader,
            clock=FixedClock(timestamp),
        )

    def content_snapshot_reader(self, timestamp: datetime) -> FilesystemFileContentSnapshotReader:
        """Return the real metadata-free snapshot adapter at a deterministic time."""
        return FilesystemFileContentSnapshotReader(clock=FixedClock(timestamp))


@dataclass(frozen=True, slots=True)
class ApplyIdentity:
    """Deterministic identity and timing for one claimed Apply."""

    run_id: RunId
    operation_id: OperationId
    event_ids: tuple[EventId, ...]
    track_ids: tuple[TrackId, ...]
    idempotency_key: UUID
    request_fingerprint: str
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class UndoFlowIdentity:
    """Deterministic Plan and Apply identities for one source Run reversal."""

    source_run_id: RunId
    plan_id: PlanId
    action_ids: tuple[ActionId, ...]
    apply_identity: ApplyIdentity


@dataclass(frozen=True, slots=True)
class CompanionRecoveryScenario:
    """Original partial Plan and later companion-only recovery Plan."""

    original_plan: Plan
    recovery_plan: Plan


ADD_APPLY_IDENTITY = ApplyIdentity(
    run_id=ADD_RUN_ID,
    operation_id=ADD_OPERATION_ID,
    event_ids=ADD_EVENT_IDS,
    track_ids=TRACK_IDS,
    idempotency_key=UUID("018f6a4f-3c2d-7b8a-9abc-def01234701d"),
    request_fingerprint="stage-four-companion-add-apply",
    timestamp=ADD_APPLY_TIME,
)
UNDO_APPLY_IDENTITY = ApplyIdentity(
    run_id=UNDO_RUN_ID,
    operation_id=UNDO_OPERATION_ID,
    event_ids=UNDO_EVENT_IDS,
    track_ids=(),
    idempotency_key=UUID("018f6a4f-3c2d-7b8a-9abc-def01234701e"),
    request_fingerprint="stage-four-companion-undo-apply",
    timestamp=UNDO_APPLY_TIME,
)
RECOVERY_APPLY_IDENTITY = ApplyIdentity(
    run_id=RECOVERY_RUN_ID,
    operation_id=RECOVERY_OPERATION_ID,
    event_ids=(RECOVERY_EVENT_ID,),
    track_ids=(),
    idempotency_key=UUID("018f6a4f-3c2d-7b8a-9abc-def012347033"),
    request_fingerprint="stage-four-companion-recovery-apply",
    timestamp=RECOVERY_APPLY_TIME,
)
ORIGINAL_RECOVERY_UNDO_APPLY_IDENTITY = ApplyIdentity(
    run_id=ORIGINAL_RECOVERY_UNDO_RUN_ID,
    operation_id=ORIGINAL_RECOVERY_UNDO_OPERATION_ID,
    event_ids=ORIGINAL_RECOVERY_UNDO_EVENT_IDS,
    track_ids=(),
    idempotency_key=UUID("018f6a4f-3c2d-7b8a-9abc-def012347034"),
    request_fingerprint="stage-four-original-run-undo-apply",
    timestamp=FIRST_RECOVERY_UNDO_APPLY_TIME,
)
RECOVERED_UNDO_APPLY_IDENTITY = ApplyIdentity(
    run_id=RECOVERED_UNDO_RUN_ID,
    operation_id=RECOVERED_UNDO_OPERATION_ID,
    event_ids=(RECOVERED_UNDO_EVENT_ID,),
    track_ids=(),
    idempotency_key=UUID("018f6a4f-3c2d-7b8a-9abc-def012347035"),
    request_fingerprint="stage-four-recovered-run-undo-apply",
    timestamp=FIRST_RECOVERY_UNDO_APPLY_TIME,
)
ORIGINAL_RECOVERY_UNDO_FLOW = UndoFlowIdentity(
    source_run_id=ADD_RUN_ID,
    plan_id=ORIGINAL_RECOVERY_UNDO_PLAN_ID,
    action_ids=ORIGINAL_RECOVERY_UNDO_ACTION_IDS,
    apply_identity=ORIGINAL_RECOVERY_UNDO_APPLY_IDENTITY,
)
RECOVERED_UNDO_FLOW = UndoFlowIdentity(
    source_run_id=RECOVERY_RUN_ID,
    plan_id=RECOVERED_UNDO_PLAN_ID,
    action_ids=(RECOVERED_UNDO_ACTION_ID,),
    apply_identity=RECOVERED_UNDO_APPLY_IDENTITY,
)


class SimulatedCrash(BaseException):
    """Escape Apply's handled filesystem failures to model process loss."""


@dataclass(frozen=True, slots=True)
class CrashOnLyricsMover:
    """Crash after a lyrics pending event while delegating earlier real moves."""

    database_file: Path
    delegate: FileMover = field(default_factory=FilesystemFileMover)

    def move(  # noqa: PLR0913  # Test wrapper mirrors the stable FileMover safety port.
        self,
        source: FileSystemPath,
        target: FileSystemPath,
        *,
        source_root: FileSystemPath | None = None,
        target_root: FileSystemPath | None = None,
        expected_source_identity: FilesystemIdentity | None = None,
        expected_source_content_hash: str | None = None,
    ) -> None:
        """Expose durable pending evidence before simulating process loss."""
        if Path(source).suffix == LYRICS_EXTENSION:
            with SQLiteUnitOfWork(self.database_file) as uow:
                plan = uow.plans.get(ADD_PLAN_ID)
                run = uow.runs.get(ADD_RUN_ID)
                events = tuple(uow.file_events.list_by_run(ADD_RUN_ID))
            assert plan is not None
            assert plan.status is PlanStatus.APPLYING
            assert run is not None
            assert run.status is RunStatus.RUNNING
            assert len(events) == EXPECTED_CRASH_EVENT_COUNT
            assert events[-1].event_type is FileEventType.MOVE_LYRICS_FILE
            assert events[-1].status is FileEventStatus.PENDING
            raise SimulatedCrash

        self.delegate.move(
            source,
            target,
            source_root=source_root,
            target_root=target_root,
            expected_source_identity=expected_source_identity,
            expected_source_content_hash=expected_source_content_hash,
        )


def test_companion_add_check_history_and_undo_round_trip_with_concrete_adapters(tmp_path: Path) -> None:
    """Audio, lyrics, and shared artwork round-trip through durable concrete adapters."""
    setup = _setup(tmp_path)
    add_plan = _create_add_plan(setup)
    _assert_add_plan_contract(setup, add_plan)

    add_run = _execute_claimed_apply(
        _apply_ports(setup, ADD_APPLY_IDENTITY, FilesystemFileMover()),
        add_plan.plan_id,
        ADD_APPLY_IDENTITY,
    )

    assert add_run.status is RunStatus.SUCCEEDED
    _assert_add_filesystem_state(setup, add_plan)
    _assert_active_managed_state(setup, add_plan)

    check_result = CheckLibraryUseCase(_check_ports(setup)).execute(
        CheckLibraryRequest(trust_stat=False, library_id=LIBRARY_ID)
    )
    assert check_result.issues == ()
    assert check_result.check_run_ids == (CHECK_RUN_ID,)
    _assert_run_history(
        setup.database_file,
        ADD_RUN_ID,
        RunStatus.SUCCEEDED,
        ADD_EVENT_IDS,
        (
            FileEventType.MOVE_FILE,
            FileEventType.MOVE_FILE,
            FileEventType.MOVE_LYRICS_FILE,
            FileEventType.MOVE_ARTWORK_FILE,
        ),
    )

    undo_plan = _create_undo_plan(setup)
    _assert_undo_plan_contract(setup, add_plan, undo_plan)
    undo_run = _execute_claimed_apply(
        _apply_ports(setup, UNDO_APPLY_IDENTITY, FilesystemFileMover()),
        undo_plan.plan_id,
        UNDO_APPLY_IDENTITY,
    )

    assert undo_run.status is RunStatus.SUCCEEDED
    _assert_undo_filesystem_state(setup, add_plan)
    _assert_removed_managed_state(setup, add_plan)
    _assert_run_history(
        setup.database_file,
        UNDO_RUN_ID,
        RunStatus.SUCCEEDED,
        UNDO_EVENT_IDS,
        (
            FileEventType.MOVE_ARTWORK_FILE,
            FileEventType.MOVE_LYRICS_FILE,
            FileEventType.MOVE_FILE,
            FileEventType.MOVE_FILE,
        ),
    )
    history_ports = HistoryPorts(SQLiteUnitOfWork(setup.database_file))
    runs = ListRunsUseCase(history_ports).execute(ListRunsRequest(library_id=LIBRARY_ID))
    assert tuple(run.run_id for run in runs.items) == (UNDO_RUN_ID, ADD_RUN_ID)


def test_companion_apply_never_overwrites_and_retains_partial_failure_evidence(tmp_path: Path) -> None:
    """A late lyrics collision fails durably while independent artwork moves once."""
    setup = _setup(tmp_path)
    add_plan = _create_add_plan(setup)
    lyrics_action = _only_action(add_plan, ActionType.MOVE_LYRICS)
    assert lyrics_action.target_path is not None
    lyrics_target = _managed_path(setup, lyrics_action.target_path)
    lyrics_target.parent.mkdir(parents=True)
    _ = lyrics_target.write_bytes(TARGET_SENTINEL_CONTENT)

    run = _execute_claimed_apply(
        _apply_ports(setup, ADD_APPLY_IDENTITY, FilesystemFileMover()),
        add_plan.plan_id,
        ADD_APPLY_IDENTITY,
    )

    assert run.status is RunStatus.PARTIAL_FAILED
    assert lyrics_target.read_bytes() == TARGET_SENTINEL_CONTENT
    assert setup.lyrics.read_bytes() == LYRICS_CONTENT
    assert not setup.first_audio.exists()
    assert not setup.second_audio.exists()
    assert not setup.artwork.exists()
    with SQLiteUnitOfWork(setup.database_file) as uow:
        stored_plan = uow.plans.get(ADD_PLAN_ID)
        actions = tuple(uow.plan_actions.list_by_plan(ADD_PLAN_ID))
        events = tuple(uow.file_events.list_by_run(ADD_RUN_ID))
        assets = tuple(uow.companion_assets.list_by_library(LIBRARY_ID))
    assert stored_plan is not None
    assert stored_plan.status is PlanStatus.PARTIAL_FAILED
    assert tuple(action.status for action in actions) == (
        ActionStatus.APPLIED,
        ActionStatus.APPLIED,
        ActionStatus.FAILED,
        ActionStatus.APPLIED,
    )
    assert actions[2].reason is PlanActionReason.TARGET_EXISTS
    assert tuple(event.status for event in events) == (
        FileEventStatus.SUCCEEDED,
        FileEventStatus.SUCCEEDED,
        FileEventStatus.FAILED,
        FileEventStatus.SUCCEEDED,
    )
    assert events[2].error_code == PlanActionReason.TARGET_EXISTS.value
    assert tuple(asset.kind for asset in assets) == (CompanionAssetKind.ARTWORK,)
    assert sum(event.event_type is FileEventType.MOVE_ARTWORK_FILE for event in events) == 1


def test_companion_crash_leaves_pending_event_visible_to_history_and_check(tmp_path: Path) -> None:
    """A process-loss boundary retains inspectable pending companion evidence."""
    setup = _setup(tmp_path)
    add_plan = _create_add_plan(setup)
    mover = CrashOnLyricsMover(setup.database_file)

    with pytest.raises(SimulatedCrash):
        _ = _execute_claimed_apply(
            _apply_ports(setup, ADD_APPLY_IDENTITY, mover),
            add_plan.plan_id,
            ADD_APPLY_IDENTITY,
        )

    assert not setup.first_audio.exists()
    assert not setup.second_audio.exists()
    assert setup.lyrics.read_bytes() == LYRICS_CONTENT
    assert setup.artwork.read_bytes() == ARTWORK_CONTENT
    with SQLiteUnitOfWork(setup.database_file) as uow:
        plan = uow.plans.get(ADD_PLAN_ID)
        run = uow.runs.get(ADD_RUN_ID)
        operation = uow.operations.lookup(ADD_OPERATION_ID)
        actions = tuple(uow.plan_actions.list_by_plan(ADD_PLAN_ID))
        events = tuple(uow.file_events.list_by_run(ADD_RUN_ID))
        tracks = tuple(uow.tracks.list_by_library(LIBRARY_ID))
        assets = tuple(uow.companion_assets.list_by_library(LIBRARY_ID))
    assert plan is not None
    assert plan.status is PlanStatus.APPLYING
    assert run is not None
    assert run.status is RunStatus.RUNNING
    assert isinstance(operation, Operation)
    assert operation.status is OperationStatus.RUNNING
    assert tuple(action.status for action in actions) == (
        ActionStatus.APPLIED,
        ActionStatus.APPLIED,
        ActionStatus.PLANNED,
        ActionStatus.PLANNED,
    )
    assert tuple(event.status for event in events) == (
        FileEventStatus.SUCCEEDED,
        FileEventStatus.SUCCEEDED,
        FileEventStatus.PENDING,
    )
    assert len(tracks) == EXPECTED_AUDIO_COUNT
    assert assets == ()
    _assert_run_history(
        setup.database_file,
        ADD_RUN_ID,
        RunStatus.RUNNING,
        ADD_EVENT_IDS[:EXPECTED_CRASH_EVENT_COUNT],
        (
            FileEventType.MOVE_FILE,
            FileEventType.MOVE_FILE,
            FileEventType.MOVE_LYRICS_FILE,
        ),
    )

    result = CheckLibraryUseCase(_check_ports(setup)).execute(
        CheckLibraryRequest(trust_stat=False, library_id=LIBRARY_ID)
    )
    assert CheckIssueType.PENDING_FILE_EVENT_EXISTS in {issue.issue_type for issue in result.issues}


@pytest.mark.parametrize(
    "original_audio_first",
    [True, False],
    ids=("original-audio-first", "recovered-companion-first"),
)
def test_failed_companion_recovery_and_original_audio_are_undoable_in_either_order(
    tmp_path: Path,
    *,
    original_audio_first: bool,
) -> None:
    """A reviewed companion-only recovery remains independently reversible in either order."""
    setup = _setup(tmp_path)
    scenario = _recover_failed_lyrics(setup)
    first_flow, second_flow = (
        (ORIGINAL_RECOVERY_UNDO_FLOW, RECOVERED_UNDO_FLOW)
        if original_audio_first
        else (RECOVERED_UNDO_FLOW, ORIGINAL_RECOVERY_UNDO_FLOW)
    )

    first_plan, first_run = _plan_and_apply_undo(
        setup,
        first_flow,
        FIRST_RECOVERY_UNDO_PLAN_TIME,
        FIRST_RECOVERY_UNDO_APPLY_TIME,
    )

    assert first_run.status is RunStatus.SUCCEEDED
    _assert_recovery_undo_plan(first_flow, first_plan)
    with SQLiteUnitOfWork(setup.database_file) as uow:
        owner_after_first = uow.tracks.get(TRACK_IDS[0])
    assert owner_after_first is not None
    assert owner_after_first.status is (TrackStatus.REMOVED if original_audio_first else TrackStatus.ACTIVE)

    second_plan, second_run = _plan_and_apply_undo(
        setup,
        second_flow,
        SECOND_RECOVERY_UNDO_PLAN_TIME,
        SECOND_RECOVERY_UNDO_APPLY_TIME,
    )

    assert second_run.status is RunStatus.SUCCEEDED
    _assert_recovery_undo_plan(second_flow, second_plan)
    _assert_undo_filesystem_state(setup, scenario.original_plan)
    _assert_removed_managed_state(setup, scenario.original_plan)
    _assert_run_history(
        setup.database_file,
        ORIGINAL_RECOVERY_UNDO_RUN_ID,
        RunStatus.SUCCEEDED,
        ORIGINAL_RECOVERY_UNDO_EVENT_IDS,
        (
            FileEventType.MOVE_ARTWORK_FILE,
            FileEventType.MOVE_FILE,
            FileEventType.MOVE_FILE,
        ),
    )
    _assert_run_history(
        setup.database_file,
        RECOVERED_UNDO_RUN_ID,
        RunStatus.SUCCEEDED,
        (RECOVERED_UNDO_EVENT_ID,),
        (FileEventType.MOVE_LYRICS_FILE,),
    )


def _setup(tmp_path: Path) -> CompanionAdapterSetup:
    database_file = tmp_path / "omym2.sqlite3"
    library_root = tmp_path / "library"
    incoming_root = tmp_path / "incoming"
    library_root.mkdir()
    incoming_root.mkdir()
    first_audio = incoming_root / "First.flac"
    second_audio = incoming_root / "Second.flac"
    lyrics = incoming_root / "First.lrc"
    artwork = incoming_root / "cover.jpg"
    _ = first_audio.write_bytes(AUDIO_ONE_CONTENT)
    _ = second_audio.write_bytes(AUDIO_TWO_CONTENT)
    _ = lyrics.write_bytes(LYRICS_CONTENT)
    _ = artwork.write_bytes(ARTWORK_CONTENT)
    config = replace(default_app_config(), companions=CompanionsConfig(enabled=True))
    setup = CompanionAdapterSetup(
        database_file=database_file,
        library_root=library_root,
        incoming_root=incoming_root,
        first_audio=first_audio,
        second_audio=second_audio,
        lyrics=lyrics,
        artwork=artwork,
        config_store=StaticConfigStore(config),
        metadata_reader=MetadataByContentReader(
            {
                AUDIO_ONE_CONTENT: _metadata("First", FIRST_TRACK_NUMBER),
                AUDIO_TWO_CONTENT: _metadata("Second", SECOND_TRACK_NUMBER),
            }
        ),
    )
    _register_library(setup)
    return setup


def _register_library(setup: CompanionAdapterSetup) -> None:
    config = setup.config_store.load()
    with SQLiteUnitOfWork(setup.database_file) as uow:
        uow.libraries.save(
            Library(
                library_id=LIBRARY_ID,
                root_path=str(setup.library_root),
                path_policy_hash=calculate_path_policy_fingerprint(
                    config.path_policy,
                    config.artist_ids,
                    config.metadata.album_year_resolution,
                    config.artist_names,
                ),
                registered_at=PLAN_TIME,
                status=LibraryStatus.REGISTERED,
                created_at=PLAN_TIME,
                updated_at=PLAN_TIME,
            )
        )
        uow.commit()


def _create_add_plan(setup: CompanionAdapterSetup) -> Plan:
    ports = CreateAddPlanPorts(
        uow=SQLiteUnitOfWork(setup.database_file),
        file_scanner=FilesystemFileScanner(),
        file_snapshot_reader=setup.snapshot_reader(PLAN_TIME),
        file_content_snapshot_reader=setup.content_snapshot_reader(PLAN_TIME),
        source_inventory_reader=FilesystemSourceInventoryReader(),
        file_presence=FilesystemFilePresence(),
        config_store=setup.config_store,
        artist_name_resolver=MappingArtistNameResolver(),
        path_resolver=FilesystemPathResolver(),
        clock=FixedClock(PLAN_TIME),
        id_generator=SequenceIdGenerator(
            plan_ids=deque((ADD_PLAN_ID,)),
            action_ids=deque(ADD_ACTION_IDS),
            companion_asset_ids=deque(COMPANION_ASSET_IDS),
        ),
        internal_excluded_paths=(),
        rotating_log_files=(),
    )
    return CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(str(setup.incoming_root)))


def _recover_failed_lyrics(setup: CompanionAdapterSetup) -> CompanionRecoveryScenario:
    original_plan = _create_add_plan(setup)
    lyrics_action = _only_action(original_plan, ActionType.MOVE_LYRICS)
    assert lyrics_action.target_path is not None
    lyrics_target = _managed_path(setup, lyrics_action.target_path)
    lyrics_target.parent.mkdir(parents=True)
    _ = lyrics_target.write_bytes(TARGET_SENTINEL_CONTENT)

    original_run = _execute_claimed_apply(
        _apply_ports(setup, ADD_APPLY_IDENTITY, FilesystemFileMover()),
        original_plan.plan_id,
        ADD_APPLY_IDENTITY,
    )

    assert original_run.status is RunStatus.PARTIAL_FAILED
    assert lyrics_target.read_bytes() == TARGET_SENTINEL_CONTENT
    assert setup.lyrics.read_bytes() == LYRICS_CONTENT
    with SQLiteUnitOfWork(setup.database_file) as uow:
        original_events = tuple(uow.file_events.list_by_run(ADD_RUN_ID))
    assert original_events[2].event_type is FileEventType.MOVE_LYRICS_FILE
    assert original_events[2].status is FileEventStatus.FAILED
    assert original_events[2].error_code == PlanActionReason.TARGET_EXISTS.value

    check_result = CheckLibraryUseCase(_check_ports(setup)).execute(
        CheckLibraryRequest(trust_stat=False, library_id=LIBRARY_ID)
    )
    recovery_issues = tuple(
        issue for issue in check_result.issues if issue.issue_type is CheckIssueType.FAILED_COMPANION_SOURCE_EXISTS
    )
    assert len(recovery_issues) == 1
    recovery_issue = recovery_issues[0]
    assert recovery_issue.path == str(setup.lyrics)
    assert recovery_issue.plan_id == ADD_PLAN_ID
    assert recovery_issue.companion_asset_id == COMPANION_ASSET_IDS[0]
    assert recovery_issue.detail == "add"

    lyrics_target.unlink()
    recovery_plan = _create_recovery_add_plan(setup)
    assert recovery_plan.plan_type is PlanType.ADD
    assert recovery_plan.status is PlanStatus.READY
    assert len(recovery_plan.actions) == 1
    recovery_action = recovery_plan.actions[0]
    assert recovery_action.action_type is ActionType.MOVE_LYRICS
    assert recovery_action.source_path == str(setup.lyrics)
    assert recovery_action.target_path == lyrics_action.target_path
    assert recovery_action.companion_asset_id == COMPANION_ASSET_IDS[0]
    assert recovery_action.track_id == TRACK_IDS[0]
    assert recovery_action.owner_action_id is None
    with SQLiteUnitOfWork(setup.database_file) as uow:
        recovery_dependencies = tuple(uow.plan_action_dependencies.list_by_action(recovery_action.action_id))
    assert recovery_dependencies == ()

    recovery_run = _execute_claimed_apply(
        _apply_ports(setup, RECOVERY_APPLY_IDENTITY, FilesystemFileMover()),
        recovery_plan.plan_id,
        RECOVERY_APPLY_IDENTITY,
    )

    assert recovery_run.status is RunStatus.SUCCEEDED
    assert not setup.lyrics.exists()
    assert lyrics_target.read_bytes() == LYRICS_CONTENT
    with SQLiteUnitOfWork(setup.database_file) as uow:
        assets = tuple(uow.companion_assets.list_by_library(LIBRARY_ID))
        all_events = tuple(uow.file_events.list_by_library(LIBRARY_ID))
    assert {asset.companion_asset_id for asset in assets} == set(COMPANION_ASSET_IDS)
    assert all(asset.status is CompanionAssetStatus.ACTIVE for asset in assets)
    assert (
        sum(
            event.event_type is FileEventType.MOVE_ARTWORK_FILE and event.status is FileEventStatus.SUCCEEDED
            for event in all_events
        )
        == 1
    )
    _assert_run_history(
        setup.database_file,
        RECOVERY_RUN_ID,
        RunStatus.SUCCEEDED,
        (RECOVERY_EVENT_ID,),
        (FileEventType.MOVE_LYRICS_FILE,),
    )
    return CompanionRecoveryScenario(original_plan=original_plan, recovery_plan=recovery_plan)


def _create_recovery_add_plan(setup: CompanionAdapterSetup) -> Plan:
    ports = CreateAddPlanPorts(
        uow=SQLiteUnitOfWork(setup.database_file),
        file_scanner=FilesystemFileScanner(),
        file_snapshot_reader=setup.snapshot_reader(RECOVERY_PLAN_TIME),
        file_content_snapshot_reader=setup.content_snapshot_reader(RECOVERY_PLAN_TIME),
        source_inventory_reader=FilesystemSourceInventoryReader(),
        file_presence=FilesystemFilePresence(),
        config_store=setup.config_store,
        artist_name_resolver=MappingArtistNameResolver(),
        path_resolver=FilesystemPathResolver(),
        clock=FixedClock(RECOVERY_PLAN_TIME),
        id_generator=SequenceIdGenerator(
            plan_ids=deque((RECOVERY_PLAN_ID,)),
            action_ids=deque((RECOVERY_ACTION_ID,)),
        ),
        internal_excluded_paths=(),
        rotating_log_files=(),
    )
    return CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(str(setup.incoming_root)))


def _apply_ports(
    setup: CompanionAdapterSetup,
    identity: ApplyIdentity,
    mover: FileMover,
) -> ApplyPlanPorts:
    return ApplyPlanPorts(
        uow=SQLiteUnitOfWork(setup.database_file),
        file_mover=mover,
        file_snapshot_reader=setup.snapshot_reader(identity.timestamp),
        file_content_snapshot_reader=setup.content_snapshot_reader(identity.timestamp),
        path_resolver=FilesystemPathResolver(),
        clock=FixedClock(identity.timestamp),
        id_generator=SequenceIdGenerator(
            run_ids=deque((identity.run_id,)),
            operation_ids=deque((identity.operation_id,)),
            event_ids=deque(identity.event_ids),
            track_ids=deque(identity.track_ids),
        ),
    )


def _execute_claimed_apply(ports: ApplyPlanPorts, plan_id: PlanId, identity: ApplyIdentity) -> Run:
    claim = ClaimApplyUseCase(ports).execute(
        ClaimApplyRequest(
            plan_id=plan_id,
            idempotency_key=identity.idempotency_key,
            request_fingerprint=identity.request_fingerprint,
        )
    )
    assert claim.is_new
    assert isinstance(claim.lookup, Operation)
    with ports.uow as uow:
        uow.operations.save(claim.lookup.mark_running(identity.timestamp))
        uow.commit()
    return ApplyPlanUseCase(ports).execute(
        ApplyPlanRequest(
            plan_id=plan_id,
            run_id=identity.run_id,
            operation_id=identity.operation_id,
            options=ApplyOptions(yes=True),
        )
    )


def _check_ports(setup: CompanionAdapterSetup) -> CheckLibraryPorts:
    return CheckLibraryPorts(
        uow=SQLiteUnitOfWork(setup.database_file),
        file_scanner=FilesystemFileScanner(),
        file_snapshot_reader=setup.snapshot_reader(CHECK_TIME),
        file_content_snapshot_reader=setup.content_snapshot_reader(CHECK_TIME),
        source_inventory_reader=FilesystemSourceInventoryReader(),
        file_content_hasher=FileContentHasher(),
        config_store=setup.config_store,
        path_resolver=FilesystemPathResolver(),
        clock=FixedClock(CHECK_TIME),
        id_generator=SequenceIdGenerator(check_run_ids=deque((CHECK_RUN_ID,))),
    )


def _create_undo_plan(setup: CompanionAdapterSetup) -> Plan:
    ports = CreateUndoPlanPorts(
        uow=SQLiteUnitOfWork(setup.database_file),
        file_snapshot_reader=setup.snapshot_reader(UNDO_PLAN_TIME),
        file_content_snapshot_reader=setup.content_snapshot_reader(UNDO_PLAN_TIME),
        file_presence=FilesystemFilePresence(),
        path_resolver=FilesystemPathResolver(),
        clock=FixedClock(UNDO_PLAN_TIME),
        id_generator=SequenceIdGenerator(
            plan_ids=deque((UNDO_PLAN_ID,)),
            action_ids=deque(UNDO_ACTION_IDS),
        ),
    )
    return CreateUndoPlanUseCase(ports).execute(CreateUndoPlanRequest(ADD_RUN_ID))


def _plan_and_apply_undo(
    setup: CompanionAdapterSetup,
    flow: UndoFlowIdentity,
    plan_timestamp: datetime,
    apply_timestamp: datetime,
) -> tuple[Plan, Run]:
    plan = _create_recovery_undo_plan(setup, flow, plan_timestamp)
    apply_identity = replace(flow.apply_identity, timestamp=apply_timestamp)
    run = _execute_claimed_apply(
        _apply_ports(setup, apply_identity, FilesystemFileMover()),
        plan.plan_id,
        apply_identity,
    )
    return plan, run


def _create_recovery_undo_plan(
    setup: CompanionAdapterSetup,
    flow: UndoFlowIdentity,
    timestamp: datetime,
) -> Plan:
    ports = CreateUndoPlanPorts(
        uow=SQLiteUnitOfWork(setup.database_file),
        file_snapshot_reader=setup.snapshot_reader(timestamp),
        file_content_snapshot_reader=setup.content_snapshot_reader(timestamp),
        file_presence=FilesystemFilePresence(),
        path_resolver=FilesystemPathResolver(),
        clock=FixedClock(timestamp),
        id_generator=SequenceIdGenerator(
            plan_ids=deque((flow.plan_id,)),
            action_ids=deque(flow.action_ids),
        ),
    )
    return CreateUndoPlanUseCase(ports).execute(CreateUndoPlanRequest(flow.source_run_id))


def _assert_recovery_undo_plan(flow: UndoFlowIdentity, plan: Plan) -> None:
    assert plan.plan_id == flow.plan_id
    assert plan.source_run_id == flow.source_run_id
    assert plan.plan_type is PlanType.UNDO
    assert plan.status is PlanStatus.READY
    if flow is ORIGINAL_RECOVERY_UNDO_FLOW:
        assert tuple(action.action_type for action in plan.actions) == (
            ActionType.MOVE_ARTWORK,
            ActionType.MOVE,
            ActionType.MOVE,
        )
        assert tuple(action.reverses_event_id for action in plan.actions) == (
            ADD_EVENT_IDS[3],
            ADD_EVENT_IDS[1],
            ADD_EVENT_IDS[0],
        )
        return

    assert flow is RECOVERED_UNDO_FLOW
    assert len(plan.actions) == 1
    action = plan.actions[0]
    assert action.action_type is ActionType.MOVE_LYRICS
    assert action.reverses_event_id == RECOVERY_EVENT_ID
    assert action.companion_asset_id == COMPANION_ASSET_IDS[0]
    assert action.track_id == TRACK_IDS[0]
    assert action.owner_action_id is None


def _assert_add_plan_contract(setup: CompanionAdapterSetup, plan: Plan) -> None:
    assert plan.plan_type is PlanType.ADD
    assert plan.status is PlanStatus.READY
    assert plan.source_root_at_plan == str(setup.incoming_root)
    assert len(plan.actions) == EXPECTED_ACTION_COUNT
    assert tuple(action.action_type for action in plan.actions) == (
        ActionType.MOVE,
        ActionType.MOVE,
        ActionType.MOVE_LYRICS,
        ActionType.MOVE_ARTWORK,
    )
    first_audio, second_audio, lyrics, artwork = plan.actions
    assert lyrics.owner_action_id == first_audio.action_id
    assert artwork.owner_action_id == first_audio.action_id
    assert lyrics.companion_asset_id == COMPANION_ASSET_IDS[0]
    assert artwork.companion_asset_id == COMPANION_ASSET_IDS[1]
    with SQLiteUnitOfWork(setup.database_file) as uow:
        lyrics_dependencies = tuple(uow.plan_action_dependencies.list_by_action(lyrics.action_id))
        artwork_dependencies = tuple(uow.plan_action_dependencies.list_by_action(artwork.action_id))
        assets = tuple(uow.companion_assets.list_by_library(LIBRARY_ID))
    assert {dependency.depends_on_action_id for dependency in lyrics_dependencies} == {first_audio.action_id}
    assert {dependency.depends_on_action_id for dependency in artwork_dependencies} == {
        first_audio.action_id,
        second_audio.action_id,
    }
    assert assets == ()


def _assert_add_filesystem_state(setup: CompanionAdapterSetup, plan: Plan) -> None:
    source_content = {
        str(setup.first_audio): AUDIO_ONE_CONTENT,
        str(setup.second_audio): AUDIO_TWO_CONTENT,
        str(setup.lyrics): LYRICS_CONTENT,
        str(setup.artwork): ARTWORK_CONTENT,
    }
    assert all(not Path(source_path).exists() for source_path in source_content)
    for action in plan.actions:
        assert action.source_path is not None
        assert action.target_path is not None
        assert _managed_path(setup, action.target_path).read_bytes() == source_content[action.source_path]


def _assert_active_managed_state(setup: CompanionAdapterSetup, plan: Plan) -> None:
    with SQLiteUnitOfWork(setup.database_file) as uow:
        tracks = tuple(uow.tracks.list_by_library(LIBRARY_ID))
        assets = tuple(uow.companion_assets.list_by_library(LIBRARY_ID))
    assert len(tracks) == EXPECTED_AUDIO_COUNT
    assert all(track.status is TrackStatus.ACTIVE for track in tracks)
    assert {track.current_path for track in tracks} == {
        action.target_path for action in plan.actions if action.action_type is ActionType.MOVE
    }
    assert len(assets) == EXPECTED_COMPANION_COUNT
    assert all(asset.status is CompanionAssetStatus.ACTIVE for asset in assets)
    assert {asset.kind for asset in assets} == {CompanionAssetKind.LYRICS, CompanionAssetKind.ARTWORK}
    assert {asset.current_path for asset in assets} == {
        action.target_path for action in plan.actions if action.action_type is not ActionType.MOVE
    }


def _assert_undo_plan_contract(setup: CompanionAdapterSetup, add_plan: Plan, undo_plan: Plan) -> None:
    assert undo_plan.plan_type is PlanType.UNDO
    assert undo_plan.status is PlanStatus.READY
    assert undo_plan.source_run_id == ADD_RUN_ID
    assert undo_plan.source_root_at_plan == str(setup.incoming_root)
    assert tuple(action.action_type for action in undo_plan.actions) == (
        ActionType.MOVE_ARTWORK,
        ActionType.MOVE_LYRICS,
        ActionType.MOVE,
        ActionType.MOVE,
    )
    assert tuple(action.reverses_event_id for action in undo_plan.actions) == tuple(reversed(ADD_EVENT_IDS))
    artwork_inverse, lyrics_inverse, second_audio_inverse, first_audio_inverse = undo_plan.actions
    assert artwork_inverse.companion_asset_id == COMPANION_ASSET_IDS[1]
    assert lyrics_inverse.companion_asset_id == COMPANION_ASSET_IDS[0]
    assert artwork_inverse.owner_action_id == first_audio_inverse.action_id
    assert lyrics_inverse.owner_action_id == first_audio_inverse.action_id
    with SQLiteUnitOfWork(setup.database_file) as uow:
        first_dependencies = tuple(uow.plan_action_dependencies.list_by_action(first_audio_inverse.action_id))
        second_dependencies = tuple(uow.plan_action_dependencies.list_by_action(second_audio_inverse.action_id))
    assert {dependency.depends_on_action_id for dependency in first_dependencies} == {
        artwork_inverse.action_id,
        lyrics_inverse.action_id,
    }
    assert {dependency.depends_on_action_id for dependency in second_dependencies} == {artwork_inverse.action_id}
    assert tuple(action.source_path for action in undo_plan.actions) == tuple(
        action.target_path for action in reversed(add_plan.actions)
    )
    assert tuple(action.target_path for action in undo_plan.actions) == tuple(
        action.source_path for action in reversed(add_plan.actions)
    )


def _assert_undo_filesystem_state(setup: CompanionAdapterSetup, add_plan: Plan) -> None:
    assert setup.first_audio.read_bytes() == AUDIO_ONE_CONTENT
    assert setup.second_audio.read_bytes() == AUDIO_TWO_CONTENT
    assert setup.lyrics.read_bytes() == LYRICS_CONTENT
    assert setup.artwork.read_bytes() == ARTWORK_CONTENT
    for action in add_plan.actions:
        assert action.target_path is not None
        assert not _managed_path(setup, action.target_path).exists()


def _assert_removed_managed_state(setup: CompanionAdapterSetup, add_plan: Plan) -> None:
    expected_asset_paths = {
        action.companion_asset_id: action.target_path
        for action in add_plan.actions
        if action.companion_asset_id is not None
    }
    with SQLiteUnitOfWork(setup.database_file) as uow:
        tracks = tuple(uow.tracks.list_by_library(LIBRARY_ID))
        assets = tuple(uow.companion_assets.list_by_library(LIBRARY_ID))
    assert len(tracks) == EXPECTED_AUDIO_COUNT
    assert all(track.status is TrackStatus.REMOVED for track in tracks)
    assert len(assets) == EXPECTED_COMPANION_COUNT
    assert all(asset.status is CompanionAssetStatus.REMOVED for asset in assets)
    assert all(asset.current_path == expected_asset_paths[asset.companion_asset_id] for asset in assets)
    assert all(asset.canonical_path == expected_asset_paths[asset.companion_asset_id] for asset in assets)


def _assert_run_history(
    database_file: Path,
    run_id: RunId,
    status: RunStatus,
    event_ids: tuple[EventId, ...],
    event_types: tuple[FileEventType, ...],
) -> None:
    ports = HistoryPorts(SQLiteUnitOfWork(database_file))
    header = GetRunHeaderUseCase(ports).execute(GetRunHeaderRequest(run_id))
    events = ListRunEventsUseCase(ports).execute(ListRunEventsRequest(run_id=run_id))
    assert header.status is status
    assert tuple(event.event_id for event in events.items) == event_ids
    assert tuple(event.event_type for event in events.items) == event_types
    expected_statuses = (
        (*((FileEventStatus.SUCCEEDED,) * (len(event_ids) - 1)), FileEventStatus.PENDING)
        if status is RunStatus.RUNNING
        else (FileEventStatus.SUCCEEDED,) * len(event_ids)
    )
    assert tuple(event.status for event in events.items) == expected_statuses
    expected_companion_ids = tuple(
        COMPANION_ASSET_IDS[0]
        if event_type is FileEventType.MOVE_LYRICS_FILE
        else COMPANION_ASSET_IDS[1]
        if event_type is FileEventType.MOVE_ARTWORK_FILE
        else None
        for event_type in event_types
    )
    assert tuple(event.companion_asset_id for event in events.items) == expected_companion_ids


def _only_action(plan: Plan, action_type: ActionType) -> PlanAction:
    matches = tuple(action for action in plan.actions if action.action_type is action_type)
    assert len(matches) == 1
    return matches[0]


def _managed_path(setup: CompanionAdapterSetup, relative_path: str) -> Path:
    return setup.library_root.joinpath(*relative_path.split("/"))


def _metadata(title: str, track_number: int) -> TrackMetadata:
    return TrackMetadata(
        title=title,
        artist="Artist",
        album="Album",
        year=METADATA_YEAR,
        track_number=track_number,
        disc_number=DISC_NUMBER,
    )
