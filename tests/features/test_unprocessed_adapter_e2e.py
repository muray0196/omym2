"""
Summary: Tests unprocessed collection through concrete filesystem and SQLite adapters.
Why: Protects Stage 5 review, mutation, diagnostics, and reversal as one durable flow.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

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
from omym2.domain.models.app_config import AppConfig, CompanionsConfig, UnprocessedConfig
from omym2.domain.models.check_issue import CheckIssueType
from omym2.domain.models.file_event import FileEventStatus, FileEventType
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.operation import Operation
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanActionReason
from omym2.domain.models.run import Run, RunStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.config_fingerprint import calculate_path_policy_fingerprint
from omym2.features.add.dto import CreateAddPlanRequest
from omym2.features.add.ports import CreateAddPlanPorts
from omym2.features.add.usecases.create_add_plan import CreateAddPlanUseCase
from omym2.features.apply.dto import ApplyOptions, ApplyPlanRequest, ClaimApplyRequest
from omym2.features.apply.ports import ApplyPlanPorts
from omym2.features.apply.usecases.apply_plan import ApplyPlanUseCase
from omym2.features.apply.usecases.claim_apply import ClaimApplyUseCase
from omym2.features.check.dto import CheckLibraryRequest, CheckLibraryResult
from omym2.features.check.ports import CheckLibraryPorts
from omym2.features.check.usecases.check_library import CheckLibraryUseCase
from omym2.features.common_ports import Uuid7IdGenerator
from omym2.features.undo.dto import CreateUndoPlanRequest
from omym2.features.undo.ports import CreateUndoPlanPorts
from omym2.features.undo.usecases.create_undo_plan import CreateUndoPlanUseCase
from omym2.shared.ids import LibraryId, PlanId
from tests.fakes.runtime import FixedClock, MappingArtistNameResolver

if TYPE_CHECKING:
    from collections.abc import Mapping

    from omym2.domain.models.file_snapshot import FilesystemIdentity
    from omym2.features.common_ports import FileMover, FileSystemPath

PLAN_TIME = datetime(2026, 7, 16, 5, tzinfo=UTC)
APPLY_TIME = PLAN_TIME + timedelta(seconds=1)
CHECK_TIME = PLAN_TIME + timedelta(seconds=2)
UNDO_PLAN_TIME = PLAN_TIME + timedelta(seconds=3)
UNDO_APPLY_TIME = PLAN_TIME + timedelta(seconds=4)

LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012348001"))
AUDIO_CONTENT = b"stage-five-audio"
LYRICS_CONTENT = b"[00:00.00] stage five\n"
ARTWORK_CONTENT = b"stage-five-artwork"
NOTE_CONTENT = b"review me"
UNSUPPORTED_AUDIO_CONTENT = b"unsupported audio"
LOG_SIBLING_CONTENT = b"ordinary source file"
CHANGED_CONTENT = b"changed after collection"
LOG_CONTENT = b"internal diagnostics"
TARGET_SENTINEL_CONTENT = b"must not be overwritten"
UNPROCESSED_DIRECTORY = "Review Later"
EXPECTED_UNPROCESSED_COUNT = 3
EXPECTED_TOTAL_ACTION_COUNT = 4
RESULT_PREVIEW_LIMIT = 1


@dataclass(slots=True)
class MutableConfigStore:
    """Expose one mutable config so the test can disable future collection."""

    config: AppConfig

    def load(self) -> AppConfig:
        """Return the current persisted-config stand-in."""
        return self.config


@dataclass(frozen=True, slots=True)
class MetadataByContentReader:
    """Read deterministic metadata after the audio file changes location."""

    metadata_by_content: Mapping[bytes, TrackMetadata]

    def read(self, path: FileSystemPath) -> TrackMetadata:
        """Return metadata selected by immutable test bytes."""
        return self.metadata_by_content[Path(path).read_bytes()]


@dataclass(frozen=True, slots=True)
class UnprocessedSetup:
    """Concrete roots and adapters shared by one Stage 5 scenario."""

    database_file: Path
    library_root: Path
    source_root: Path
    audio: Path
    lyrics: Path
    artwork: Path
    note: Path
    unsupported_audio: Path
    log_sibling: Path
    log_file: Path
    config_store: MutableConfigStore
    metadata_reader: MetadataByContentReader
    internal_paths: tuple[Path, ...]

    def snapshot_reader(self, timestamp: datetime) -> FilesystemFileSnapshotReader:
        """Build the real metadata-aware snapshot adapter."""
        return FilesystemFileSnapshotReader(
            metadata_reader=self.metadata_reader,
            clock=FixedClock(timestamp),
        )

    def content_snapshot_reader(self, timestamp: datetime) -> FilesystemFileContentSnapshotReader:
        """Build the real content-only snapshot adapter."""
        return FilesystemFileContentSnapshotReader(clock=FixedClock(timestamp))


class SimulatedCrash(BaseException):
    """Escape Apply's handled I/O failures to model process loss."""


@dataclass(frozen=True, slots=True)
class CrashOnFirstUnprocessedMover:
    """Crash after the pending event for the first unprocessed action."""

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
        """Interrupt the first collection move while delegating audio safely."""
        if UNPROCESSED_DIRECTORY in Path(target).parts:
            raise SimulatedCrash
        self.delegate.move(
            source,
            target,
            source_root=source_root,
            target_root=target_root,
            expected_source_identity=expected_source_identity,
            expected_source_content_hash=expected_source_content_hash,
        )


def test_unprocessed_plan_apply_check_history_and_undo_round_trip(tmp_path: Path) -> None:
    """All reviewed leftovers survive disablement and reverse through durable evidence."""
    setup = _setup(tmp_path)
    plan = _create_add_plan(setup)
    _assert_plan_contract(setup, plan)

    setup.config_store.config = replace(
        setup.config_store.config,
        unprocessed=replace(setup.config_store.config.unprocessed, enabled=False),
    )
    run = _execute_apply(_apply_ports(setup, APPLY_TIME, FilesystemFileMover()), plan.plan_id, APPLY_TIME)

    assert run.status is RunStatus.SUCCEEDED
    _assert_collected_state(setup, plan)
    with SQLiteUnitOfWork(setup.database_file) as uow:
        events = tuple(uow.file_events.list_by_run(run.run_id))
        tracks = tuple(uow.tracks.list_by_library(LIBRARY_ID))
        assets = tuple(uow.companion_assets.list_by_library(LIBRARY_ID))
    assert tuple(event.event_type for event in events) == (
        FileEventType.MOVE_FILE,
        *((FileEventType.MOVE_UNPROCESSED_FILE,) * EXPECTED_UNPROCESSED_COUNT),
    )
    assert all(event.status is FileEventStatus.SUCCEEDED for event in events)
    assert len(tracks) == 1
    assert assets == ()

    check_result = _check(setup, CHECK_TIME)
    assert not {
        CheckIssueType.UNPROCESSED_FILE_MISSING,
        CheckIssueType.UNPROCESSED_CONTENT_HASH_CHANGED,
    }.intersection(issue.issue_type for issue in check_result.issues)

    undo_plan = _create_undo_plan(setup, run, UNDO_PLAN_TIME)
    assert undo_plan.plan_type is PlanType.UNDO
    assert undo_plan.status is PlanStatus.READY
    assert undo_plan.source_root_at_plan == str(setup.source_root)
    assert tuple(action.action_type for action in undo_plan.actions) == (
        *((ActionType.MOVE_UNPROCESSED,) * EXPECTED_UNPROCESSED_COUNT),
        ActionType.MOVE,
    )
    undo_run = _execute_apply(
        _apply_ports(setup, UNDO_APPLY_TIME, FilesystemFileMover()),
        undo_plan.plan_id,
        UNDO_APPLY_TIME,
    )

    assert undo_run.status is RunStatus.SUCCEEDED
    assert setup.audio.read_bytes() == AUDIO_CONTENT
    assert setup.note.read_bytes() == NOTE_CONTENT
    assert setup.unsupported_audio.read_bytes() == UNSUPPORTED_AUDIO_CONTENT
    assert setup.log_sibling.read_bytes() == LOG_SIBLING_CONTENT
    assert setup.lyrics.read_bytes() == LYRICS_CONTENT
    assert setup.artwork.read_bytes() == ARTWORK_CONTENT
    assert all(not Path(action.source_path or "").is_symlink() for action in undo_plan.actions)


def test_unprocessed_crash_retains_pending_history_and_check_evidence(tmp_path: Path) -> None:
    """Process loss after pending persistence remains visible without guessing outcome."""
    setup = _setup(tmp_path)
    plan = _create_add_plan(setup)
    ports = _apply_ports(setup, APPLY_TIME, CrashOnFirstUnprocessedMover())

    with pytest.raises(SimulatedCrash):
        _ = _execute_apply(ports, plan.plan_id, APPLY_TIME)

    with SQLiteUnitOfWork(setup.database_file) as uow:
        stored_plan = uow.plans.get(plan.plan_id)
        runs = tuple(uow.runs.list_by_plan(plan.plan_id))
        events = tuple(uow.file_events.list_by_run(runs[0].run_id))
    assert stored_plan is not None
    assert stored_plan.status is PlanStatus.APPLYING
    assert len(runs) == 1
    assert runs[0].status is RunStatus.RUNNING
    assert events[-1].event_type is FileEventType.MOVE_UNPROCESSED_FILE
    assert events[-1].status is FileEventStatus.PENDING
    result = _check(setup, CHECK_TIME)
    assert CheckIssueType.PENDING_FILE_EVENT_EXISTS in {issue.issue_type for issue in result.issues}


def test_unprocessed_check_reports_missing_then_changed_collected_file(tmp_path: Path) -> None:
    """Durable successful collection evidence detects target loss and content drift."""
    setup = _setup(tmp_path)
    plan = _create_add_plan(setup)
    run = _execute_apply(_apply_ports(setup, APPLY_TIME, FilesystemFileMover()), plan.plan_id, APPLY_TIME)
    assert run.status is RunStatus.SUCCEEDED
    note_action = next(
        action
        for action in plan.actions
        if action.action_type is ActionType.MOVE_UNPROCESSED and action.source_path == str(setup.note)
    )
    assert note_action.target_path is not None
    collected_note = Path(note_action.target_path)
    collected_note.unlink()

    missing = _check(setup, CHECK_TIME)
    assert any(
        issue.issue_type is CheckIssueType.UNPROCESSED_FILE_MISSING and issue.path == str(collected_note)
        for issue in missing.issues
    )

    _ = collected_note.write_bytes(CHANGED_CONTENT)
    changed = _check(setup, CHECK_TIME + timedelta(seconds=1))
    assert any(
        issue.issue_type is CheckIssueType.UNPROCESSED_CONTENT_HASH_CHANGED and issue.path == str(collected_note)
        for issue in changed.issues
    )
    undo_plan = _create_undo_plan(setup, run, UNDO_PLAN_TIME)
    note_inverse = next(
        action
        for action in undo_plan.actions
        if action.action_type is ActionType.MOVE_UNPROCESSED and action.target_path == str(setup.note)
    )
    assert note_inverse.status is ActionStatus.BLOCKED
    assert note_inverse.reason is PlanActionReason.SOURCE_CHANGED


def test_unprocessed_apply_never_overwrites_a_target_created_after_review(tmp_path: Path) -> None:
    """A late collision fails durably while preserving both user-controlled files."""
    setup = _setup(tmp_path)
    plan = _create_add_plan(setup)
    note_action = next(
        action
        for action in plan.actions
        if action.action_type is ActionType.MOVE_UNPROCESSED and action.source_path == str(setup.note)
    )
    assert note_action.target_path is not None
    target = Path(note_action.target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_bytes(TARGET_SENTINEL_CONTENT)

    run = _execute_apply(_apply_ports(setup, APPLY_TIME, FilesystemFileMover()), plan.plan_id, APPLY_TIME)

    assert run.status is RunStatus.PARTIAL_FAILED
    assert setup.note.read_bytes() == NOTE_CONTENT
    assert target.read_bytes() == TARGET_SENTINEL_CONTENT
    with SQLiteUnitOfWork(setup.database_file) as uow:
        stored_action = uow.plan_actions.get(note_action.action_id)
        events = tuple(uow.file_events.list_by_run(run.run_id))
    assert stored_action is not None
    assert stored_action.status is ActionStatus.FAILED
    assert stored_action.reason is PlanActionReason.TARGET_EXISTS
    assert any(
        event.plan_action_id == note_action.action_id
        and event.event_type is FileEventType.MOVE_UNPROCESSED_FILE
        and event.status is FileEventStatus.FAILED
        for event in events
    )


def _setup(tmp_path: Path) -> UnprocessedSetup:
    database_file = tmp_path / "omym2.sqlite3"
    library_root = tmp_path / "library"
    source_root = tmp_path / "incoming"
    library_root.mkdir()
    source_root.mkdir()
    audio = source_root / "Song.flac"
    lyrics = source_root / "Song.lrc"
    artwork = source_root / "cover.jpg"
    note = source_root / "docs" / "note.txt"
    unsupported_audio = source_root / "raw" / "sample.unsupported"
    log_file = source_root / "logs" / "omym2.log"
    log_sibling = source_root / "logs" / "readme.txt"
    internal_config = source_root / "config"
    internal_data = source_root / "data"
    destination = source_root / UNPROCESSED_DIRECTORY
    for directory in (
        note.parent,
        unsupported_audio.parent,
        log_file.parent,
        internal_config,
        internal_data,
        destination,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    _ = audio.write_bytes(AUDIO_CONTENT)
    _ = lyrics.write_bytes(LYRICS_CONTENT)
    _ = artwork.write_bytes(ARTWORK_CONTENT)
    _ = note.write_bytes(NOTE_CONTENT)
    _ = unsupported_audio.write_bytes(UNSUPPORTED_AUDIO_CONTENT)
    _ = log_file.write_bytes(LOG_CONTENT)
    _ = log_file.with_name(f"{log_file.name}.1").write_bytes(LOG_CONTENT)
    _ = log_sibling.write_bytes(LOG_SIBLING_CONTENT)
    _ = (internal_config / "config.toml").write_text("internal", encoding="utf-8")
    _ = (internal_data / "state.sqlite3").write_bytes(b"internal")
    _ = (destination / "already-collected.bin").write_bytes(TARGET_SENTINEL_CONTENT)
    outside = tmp_path / "outside.txt"
    _ = outside.write_text("outside", encoding="utf-8")
    (source_root / "linked.txt").symlink_to(outside)

    config = replace(
        default_app_config(),
        companions=CompanionsConfig(enabled=False),
        unprocessed=UnprocessedConfig(
            enabled=True,
            directory=UNPROCESSED_DIRECTORY,
            result_preview_limit=RESULT_PREVIEW_LIMIT,
        ),
    )
    setup = UnprocessedSetup(
        database_file=database_file,
        library_root=library_root,
        source_root=source_root,
        audio=audio,
        lyrics=lyrics,
        artwork=artwork,
        note=note,
        unsupported_audio=unsupported_audio,
        log_sibling=log_sibling,
        log_file=log_file,
        config_store=MutableConfigStore(config),
        metadata_reader=MetadataByContentReader(
            {
                AUDIO_CONTENT: TrackMetadata(
                    title="Song",
                    artist="Artist",
                    album="Album",
                    year=2026,
                    track_number=1,
                    disc_number=1,
                )
            }
        ),
        internal_paths=(internal_config, internal_data, log_file),
    )
    _register_library(setup)
    return setup


def _register_library(setup: UnprocessedSetup) -> None:
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
                ),
                registered_at=PLAN_TIME,
                status=LibraryStatus.REGISTERED,
                created_at=PLAN_TIME,
                updated_at=PLAN_TIME,
            )
        )
        uow.commit()


def _create_add_plan(setup: UnprocessedSetup) -> Plan:
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
        id_generator=_id_generator(),
        internal_excluded_paths=setup.internal_paths,
        rotating_log_files=(setup.log_file,),
    )
    return CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(str(setup.source_root)))


def _apply_ports(setup: UnprocessedSetup, timestamp: datetime, mover: FileMover) -> ApplyPlanPorts:
    return ApplyPlanPorts(
        uow=SQLiteUnitOfWork(setup.database_file),
        file_mover=mover,
        file_snapshot_reader=setup.snapshot_reader(timestamp),
        file_content_snapshot_reader=setup.content_snapshot_reader(timestamp),
        path_resolver=FilesystemPathResolver(),
        clock=FixedClock(timestamp),
        id_generator=_id_generator(),
    )


def _execute_apply(ports: ApplyPlanPorts, plan_id: PlanId, timestamp: datetime) -> Run:
    claim = ClaimApplyUseCase(ports).execute(
        ClaimApplyRequest(
            plan_id=plan_id,
            idempotency_key=uuid4(),
            request_fingerprint=f"stage-five-{plan_id}",
        )
    )
    assert claim.is_new
    assert isinstance(claim.lookup, Operation)
    operation = claim.lookup
    assert operation.plan_id is not None
    assert operation.run_id is not None
    with ports.uow as uow:
        uow.operations.save(operation.mark_running(timestamp))
        uow.commit()
    return ApplyPlanUseCase(ports).execute(
        ApplyPlanRequest(
            plan_id=operation.plan_id,
            run_id=operation.run_id,
            operation_id=operation.operation_id,
            options=ApplyOptions(yes=True),
        )
    )


def _check(setup: UnprocessedSetup, timestamp: datetime) -> CheckLibraryResult:
    ports = CheckLibraryPorts(
        uow=SQLiteUnitOfWork(setup.database_file),
        file_scanner=FilesystemFileScanner(),
        file_snapshot_reader=setup.snapshot_reader(timestamp),
        file_content_snapshot_reader=setup.content_snapshot_reader(timestamp),
        source_inventory_reader=FilesystemSourceInventoryReader(),
        file_content_hasher=FileContentHasher(),
        config_store=setup.config_store,
        path_resolver=FilesystemPathResolver(),
        clock=FixedClock(timestamp),
        id_generator=_id_generator(),
    )
    return CheckLibraryUseCase(ports).execute(CheckLibraryRequest(trust_stat=False, library_id=LIBRARY_ID))


def _create_undo_plan(setup: UnprocessedSetup, run: Run, timestamp: datetime) -> Plan:
    ports = CreateUndoPlanPorts(
        uow=SQLiteUnitOfWork(setup.database_file),
        file_snapshot_reader=setup.snapshot_reader(timestamp),
        file_content_snapshot_reader=setup.content_snapshot_reader(timestamp),
        file_presence=FilesystemFilePresence(),
        path_resolver=FilesystemPathResolver(),
        clock=FixedClock(timestamp),
        id_generator=_id_generator(),
    )
    return CreateUndoPlanUseCase(ports).execute(CreateUndoPlanRequest(run.run_id))


def _assert_plan_contract(setup: UnprocessedSetup, plan: Plan) -> None:
    assert plan.plan_type is PlanType.ADD
    assert plan.status is PlanStatus.READY
    assert plan.source_root_at_plan == str(setup.source_root)
    assert len(plan.actions) == EXPECTED_TOTAL_ACTION_COUNT
    assert plan.summary["unprocessed_actions"] == str(EXPECTED_UNPROCESSED_COUNT)
    assert plan.summary["unprocessed_preview_limit"] == str(RESULT_PREVIEW_LIMIT)
    assert plan.actions[0].action_type is ActionType.MOVE
    leftovers = tuple(action for action in plan.actions if action.action_type is ActionType.MOVE_UNPROCESSED)
    assert len(leftovers) == EXPECTED_UNPROCESSED_COUNT
    assert all(action.track_id is None for action in leftovers)
    assert all(action.metadata_hash_at_plan is None for action in leftovers)
    assert all(action.content_hash_at_plan is not None for action in leftovers)
    assert all(action.status is ActionStatus.PLANNED for action in leftovers)
    assert {action.source_path for action in leftovers} == {
        str(setup.note),
        str(setup.unsupported_audio),
        str(setup.log_sibling),
    }
    assert str(setup.lyrics) not in {action.source_path for action in plan.actions}
    assert str(setup.artwork) not in {action.source_path for action in plan.actions}
    assert str(setup.log_file) not in {action.source_path for action in plan.actions}


def _assert_collected_state(setup: UnprocessedSetup, plan: Plan) -> None:
    source_content = {
        str(setup.note): NOTE_CONTENT,
        str(setup.unsupported_audio): UNSUPPORTED_AUDIO_CONTENT,
        str(setup.log_sibling): LOG_SIBLING_CONTENT,
    }
    for action in plan.actions:
        if action.action_type is not ActionType.MOVE_UNPROCESSED:
            continue
        assert action.source_path is not None
        assert action.target_path is not None
        assert not Path(action.source_path).exists()
        assert Path(action.target_path).read_bytes() == source_content[action.source_path]
    assert setup.lyrics.read_bytes() == LYRICS_CONTENT
    assert setup.artwork.read_bytes() == ARTWORK_CONTENT
    assert setup.log_file.read_bytes() == LOG_CONTENT
    assert setup.log_file.with_name(f"{setup.log_file.name}.1").read_bytes() == LOG_CONTENT


def _id_generator() -> Uuid7IdGenerator:
    return Uuid7IdGenerator()
