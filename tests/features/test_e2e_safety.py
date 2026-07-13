"""
Summary: Tests safe end-to-end execution across concrete adapters.
Why: Protects reviewed actions, storage paths, and history evidence together.
"""

from __future__ import annotations

import os
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePath
from typing import TYPE_CHECKING
from uuid import UUID

from omym2.adapters.config.default_config import default_app_config
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.adapters.fs import file_mover as file_mover_module
from omym2.adapters.fs.file_mover import FilesystemFileMover
from omym2.adapters.fs.file_presence import FilesystemFilePresence
from omym2.adapters.fs.file_scanner import FilesystemFileScanner
from omym2.adapters.fs.file_snapshot_reader import FilesystemFileSnapshotReader
from omym2.adapters.fs.path_resolver import FilesystemPathResolver
from omym2.config import PLAN_ACTION_SORT_ORDER_START
from omym2.domain.models.app_config import AppConfig, PathPolicyConfig
from omym2.domain.models.file_event import FileEvent, FileEventStatus
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.operation import Operation
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction, PlanActionReason
from omym2.domain.models.run import RunStatus
from omym2.domain.models.track import Track, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.config_fingerprint import calculate_path_policy_fingerprint
from omym2.domain.services.content_fingerprint import calculate_content_fingerprint
from omym2.domain.services.metadata_fingerprint import calculate_metadata_fingerprint
from omym2.features.add.dto import CreateAddPlanRequest
from omym2.features.add.ports import CreateAddPlanPorts
from omym2.features.add.usecases.create_add_plan import CreateAddPlanUseCase
from omym2.features.apply.dto import ApplyOptions, ApplyPlanRequest, ClaimApplyRequest
from omym2.features.apply.ports import ApplyPlanPorts
from omym2.features.apply.usecases.apply_plan import ApplyPlanUseCase
from omym2.features.apply.usecases.claim_apply import ClaimApplyUseCase
from omym2.features.common_ports import ConfigRevisionMismatchError, ConfigSnapshot, ConfigSnapshotState
from omym2.features.history.dto import GetRunHeaderRequest, ListRunEventsRequest, ListRunsRequest
from omym2.features.history.ports import HistoryPorts
from omym2.features.history.usecases.get_run_header import GetRunHeaderUseCase
from omym2.features.history.usecases.list_run_events import ListRunEventsUseCase
from omym2.features.history.usecases.list_runs import ListRunsUseCase
from omym2.features.inspect.dto import InspectFileRequest
from omym2.features.inspect.ports import InspectFilePorts
from omym2.features.inspect.usecases.inspect_file import InspectFileUseCase
from omym2.shared.ids import ActionId, EventId, LibraryId, OperationId, PlanId, RunId, TrackId
from tests.fakes.runtime import FixedClock, SequenceIdGenerator

if TYPE_CHECKING:
    from collections.abc import Mapping

    import pytest

    from omym2.domain.models.file_snapshot import FilesystemIdentity
    from omym2.features.common_ports import FileMover, FileSystemPath

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
BLOCKED_CONTENT = b"blocked audio"
DUPLICATE_CONTENT = b"duplicate audio"
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
MOVE_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567b"))
OPERATION_ID = OperationId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345681"))
OPERATION_IDEMPOTENCY_KEY = UUID("018f6a4f-3c2d-7b8a-9abc-def012345682")
OPERATION_REQUEST_FINGERPRINT = "apply-plan-e2e-fingerprint"
DUPLICATE_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567c"))
BLOCKED_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567d"))
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567a"))
RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567e"))
EVENT_ID = EventId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567f"))
TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345679"))
DUPLICATE_TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345680"))
SUCCESS_CONTENT = b"successful audio"
SUCCESS_TARGET_PATH = "Artist/2026_Album/1-02_Title.flac"
MANAGED_SOURCE_PATH = "linked/song.flac"
MANAGED_TARGET_PATH = "safe/Moved.flac"
PLAN_CONFIG_HASH = "managed-path-security-plan"
REPLACED_SOURCE_BACKUP_NAME = "captured-song.flac"
REGISTERED_TRACK_PATH = "Artist/2026_Album/1-01_Existing.flac"
RECALCULATED_TARGET_TEMPLATE = "{artist}/{title}"
CONFIG_REVISION = "v1:e2e-safety"
SAVED_CONFIG_REVISION = "v1:e2e-safety-saved"


def test_inspect_plan_apply_and_history_use_recorded_paths_with_concrete_adapters(tmp_path: Path) -> None:
    """Recorded add actions drive apply even after current config changes."""
    setup = _setup_mixed_incoming_library(tmp_path)

    inspected = InspectFileUseCase(InspectFilePorts(setup.snapshot_reader, setup.config_store)).execute(
        InspectFileRequest(str(setup.success_file))
    )
    assert inspected.canonical_path == SUCCESS_TARGET_PATH

    plan = _create_mixed_plan(setup)
    _ = setup.config_store.save(
        AppConfig(path_policy=PathPolicyConfig(template=RECALCULATED_TARGET_TEMPLATE)),
        expected_config_revision=setup.config_store.read_snapshot().config_revision,
    )
    run = _apply_plan_with_asserting_mover(setup, plan.plan_id)

    assert run is not None
    assert run.status == RunStatus.SUCCEEDED
    assert not setup.success_file.exists()
    assert setup.library_root.joinpath(*SUCCESS_TARGET_PATH.split("/")).read_bytes() == SUCCESS_CONTENT
    assert not setup.library_root.joinpath("Artist", "Title.flac").exists()

    with SQLiteUnitOfWork(setup.database_file) as uow:
        stored_plan = uow.plans.get(plan.plan_id)
        assert stored_plan is not None
        assert stored_plan.status == PlanStatus.APPLIED
        actions = tuple(uow.plan_actions.list_by_plan(plan.plan_id))
        move_action = _action_by_source(actions, str(setup.success_file))
        skip_action = _action_by_source(actions, str(setup.duplicate_file))
        blocked_action = _action_by_source(actions, str(setup.blocked_file))
        events = tuple(uow.file_events.list_by_run(run.run_id))
        tracks = tuple(uow.tracks.list_by_library(LIBRARY_ID))

    assert move_action.status == ActionStatus.APPLIED
    assert move_action.target_path == SUCCESS_TARGET_PATH
    assert skip_action.action_type == ActionType.SKIP
    assert skip_action.status == ActionStatus.APPLIED
    assert skip_action.reason == PlanActionReason.DUPLICATE_HASH
    assert blocked_action.status == ActionStatus.BLOCKED
    assert blocked_action.reason == PlanActionReason.MISSING_REQUIRED_METADATA
    assert len(events) == 1
    assert events[0].status == FileEventStatus.SUCCEEDED
    assert events[0].target_path == SUCCESS_TARGET_PATH
    assert all(not PurePath(path).is_absolute() for path in _library_managed_paths(move_action, events[0], tracks))

    history_ports = HistoryPorts(SQLiteUnitOfWork(setup.database_file))
    runs = ListRunsUseCase(history_ports).execute(ListRunsRequest())
    header = GetRunHeaderUseCase(history_ports).execute(GetRunHeaderRequest(run.run_id))
    event_page = ListRunEventsUseCase(history_ports).execute(ListRunEventsRequest(run_id=run.run_id))

    assert tuple(item.run_id for item in runs.items) == (run.run_id,)
    assert header.status == RunStatus.SUCCEEDED
    assert tuple(event.event_id for event in event_page.items) == (EVENT_ID,)


def test_apply_precondition_failure_records_no_file_event_with_concrete_adapters(tmp_path: Path) -> None:
    """Changed source content fails before any Library music file mutation."""
    database_file = tmp_path / "omym2.sqlite3"
    library_root = tmp_path / "library"
    incoming_root = tmp_path / "incoming"
    library_root.mkdir()
    incoming_root.mkdir()
    source_file = incoming_root / "01 Title.flac"
    _ = source_file.write_bytes(SUCCESS_CONTENT)
    metadata_by_path = {str(source_file): _metadata(title="Title", track_number=2)}
    config_store = MutableConfigStore(default_app_config())
    snapshot_reader = FilesystemFileSnapshotReader(
        metadata_reader=MappingMetadataReader(metadata_by_path),
        clock=FixedClock(BASE_TIME),
    )
    _register_library(database_file, str(library_root))
    plan = CreateAddPlanUseCase(_add_ports(database_file, incoming_root, config_store, snapshot_reader)).execute(
        CreateAddPlanRequest(str(incoming_root))
    )
    _ = source_file.write_bytes(b"changed audio")

    run = _execute_claimed_apply(
        _apply_ports(database_file, snapshot_reader, FilesystemFileMover()),
        plan.plan_id,
    )

    assert run is not None
    assert run.status == RunStatus.FAILED
    assert source_file.exists()
    assert not library_root.joinpath(*SUCCESS_TARGET_PATH.split("/")).exists()
    with SQLiteUnitOfWork(database_file) as uow:
        actions = tuple(uow.plan_actions.list_by_plan(plan.plan_id))
        events = tuple(uow.file_events.list_by_run(run.run_id))
        stored_plan = uow.plans.get(plan.plan_id)

    assert stored_plan is not None
    assert stored_plan.status == PlanStatus.FAILED
    assert actions[0].status == ActionStatus.FAILED
    assert actions[0].reason == PlanActionReason.SOURCE_CHANGED
    assert events == ()


def test_apply_deleted_source_records_no_file_event_with_concrete_adapters(tmp_path: Path) -> None:
    """Deleted source files fail before any Library music file mutation."""
    database_file = tmp_path / "omym2.sqlite3"
    library_root = tmp_path / "library"
    incoming_root = tmp_path / "incoming"
    library_root.mkdir()
    incoming_root.mkdir()
    source_file = incoming_root / "01 Title.flac"
    _ = source_file.write_bytes(SUCCESS_CONTENT)
    metadata_by_path = {str(source_file): _metadata(title="Title", track_number=2)}
    config_store = MutableConfigStore(default_app_config())
    snapshot_reader = FilesystemFileSnapshotReader(
        metadata_reader=MappingMetadataReader(metadata_by_path),
        clock=FixedClock(BASE_TIME),
    )
    _register_library(database_file, str(library_root))
    plan = CreateAddPlanUseCase(_add_ports(database_file, incoming_root, config_store, snapshot_reader)).execute(
        CreateAddPlanRequest(str(incoming_root))
    )
    source_file.unlink()

    run = _execute_claimed_apply(
        _apply_ports(database_file, snapshot_reader, FilesystemFileMover()),
        plan.plan_id,
    )

    assert run is not None
    assert run.status == RunStatus.FAILED
    assert not source_file.exists()
    assert not library_root.joinpath(*SUCCESS_TARGET_PATH.split("/")).exists()
    with SQLiteUnitOfWork(database_file) as uow:
        actions = tuple(uow.plan_actions.list_by_plan(plan.plan_id))
        events = tuple(uow.file_events.list_by_run(run.run_id))
        stored_plan = uow.plans.get(plan.plan_id)

    assert stored_plan is not None
    assert stored_plan.status == PlanStatus.FAILED
    assert actions[0].status == ActionStatus.FAILED
    assert actions[0].reason == PlanActionReason.SOURCE_MISSING
    assert events == ()


def test_apply_rejects_managed_source_parent_symlink_without_outside_mutation(tmp_path: Path) -> None:
    """Apply records invalid_path instead of following a managed source parent outside."""
    database_file = tmp_path / "omym2.sqlite3"
    library_root = tmp_path / "library"
    outside_root = tmp_path / "outside"
    source_path = library_root / "linked" / "song.flac"
    outside_source = outside_root / source_path.name
    target_path = library_root / "safe" / "Moved.flac"
    library_root.mkdir()
    outside_root.mkdir()
    _ = outside_source.write_bytes(SUCCESS_CONTENT)
    (library_root / "linked").symlink_to(outside_root, target_is_directory=True)
    snapshot_reader = _managed_snapshot_reader(source_path)
    _register_library(database_file, str(library_root))
    _save_managed_move_plan(database_file, library_root)

    run = _execute_claimed_apply(
        _apply_ports(database_file, snapshot_reader, FilesystemFileMover()),
        PLAN_ID,
    )

    assert run.status == RunStatus.FAILED
    assert outside_source.read_bytes() == SUCCESS_CONTENT
    assert not target_path.exists()
    _assert_invalid_path_apply_evidence(database_file)


def test_apply_rejects_managed_target_parent_symlink_as_invalid_path(tmp_path: Path) -> None:
    """Apply normalizes an anchored target-parent symlink to invalid_path."""
    database_file = tmp_path / "omym2.sqlite3"
    library_root = tmp_path / "library"
    outside_root = tmp_path / "outside"
    source_path = library_root / "source" / "song.flac"
    target_path = library_root / "linked" / "Moved.flac"
    source_path.parent.mkdir(parents=True)
    outside_root.mkdir()
    _ = source_path.write_bytes(SUCCESS_CONTENT)
    (library_root / "linked").symlink_to(outside_root, target_is_directory=True)
    snapshot_reader = _managed_snapshot_reader(source_path)
    _register_library(database_file, str(library_root))
    _save_managed_move_plan(
        database_file,
        library_root,
        source_path="source/song.flac",
        target_path="linked/Moved.flac",
    )

    run = _execute_claimed_apply(
        _apply_ports(database_file, snapshot_reader, FilesystemFileMover()),
        PLAN_ID,
    )

    assert run.status == RunStatus.FAILED
    assert source_path.read_bytes() == SUCCESS_CONTENT
    assert not (outside_root / target_path.name).exists()
    _assert_invalid_path_apply_evidence(database_file)


def test_apply_fails_closed_when_descriptor_operations_are_unsupported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unsupported anchored operations become durable invalid_path evidence."""
    database_file = tmp_path / "omym2.sqlite3"
    library_root = tmp_path / "library"
    source_path = library_root / "source" / "song.flac"
    target_path = library_root / "safe" / "Moved.flac"
    source_path.parent.mkdir(parents=True)
    _ = source_path.write_bytes(SUCCESS_CONTENT)
    snapshot_reader = _managed_snapshot_reader(source_path)
    _register_library(database_file, str(library_root))
    _save_managed_move_plan(
        database_file,
        library_root,
        source_path="source/song.flac",
    )
    monkeypatch.setattr(file_mover_module, "_OPEN_SUPPORTS_DIR_FD", False)

    run = _execute_claimed_apply(
        _apply_ports(database_file, snapshot_reader, FilesystemFileMover()),
        PLAN_ID,
    )

    assert run.status == RunStatus.FAILED
    assert source_path.read_bytes() == SUCCESS_CONTENT
    assert not target_path.exists()
    _assert_invalid_path_apply_evidence(database_file)


def test_apply_records_source_missing_when_leaf_disappears_after_pending_event(tmp_path: Path) -> None:
    """A leaf removed after the pending commit produces durable source_missing evidence."""
    database_file = tmp_path / "omym2.sqlite3"
    library_root = tmp_path / "library"
    source_path = library_root / "source" / "song.flac"
    target_path = library_root / "safe" / "Moved.flac"
    source_path.parent.mkdir(parents=True)
    _ = source_path.write_bytes(SUCCESS_CONTENT)
    snapshot_reader = _managed_snapshot_reader(source_path)
    _register_library(database_file, str(library_root))
    _save_managed_move_plan(
        database_file,
        library_root,
        source_path="source/song.flac",
    )
    mover = AssertingFileMover(
        database_file,
        delegate=DeleteSourceBeforeMoveFileMover(),
    )

    run = _execute_claimed_apply(
        _apply_ports(database_file, snapshot_reader, mover),
        PLAN_ID,
    )

    assert run.status == RunStatus.FAILED
    assert not source_path.exists()
    assert not target_path.exists()
    with SQLiteUnitOfWork(database_file) as uow:
        actions = tuple(uow.plan_actions.list_by_plan(PLAN_ID))
        events = tuple(uow.file_events.list_by_run(RUN_ID))
    assert actions[0].status == ActionStatus.FAILED
    assert actions[0].reason == PlanActionReason.SOURCE_MISSING
    assert events[0].status == FileEventStatus.FAILED
    assert events[0].error_code == PlanActionReason.SOURCE_MISSING.value


def test_apply_rejects_same_bytes_exact_mtime_source_replacement_before_move(tmp_path: Path) -> None:
    """The mover requires the full filesystem token captured before the pending event."""
    database_file = tmp_path / "omym2.sqlite3"
    library_root = tmp_path / "library"
    source_path = library_root / "source" / "song.flac"
    target_path = library_root / "safe" / "Moved.flac"
    backup_path = source_path.with_name(REPLACED_SOURCE_BACKUP_NAME)
    source_path.parent.mkdir(parents=True)
    _ = source_path.write_bytes(SUCCESS_CONTENT)
    snapshot_reader = _managed_snapshot_reader(source_path)
    _register_library(database_file, str(library_root))
    _save_managed_move_plan(
        database_file,
        library_root,
        source_path="source/song.flac",
    )
    mover = ReplaceSourceBeforeMoveFileMover()

    run = _execute_claimed_apply(
        _apply_ports(database_file, snapshot_reader, mover),
        PLAN_ID,
    )

    assert run.status == RunStatus.FAILED
    assert source_path.read_bytes() == SUCCESS_CONTENT
    assert backup_path.read_bytes() == SUCCESS_CONTENT
    assert mover.expected_mtime_ns is not None
    assert source_path.stat().st_mtime_ns == mover.expected_mtime_ns
    assert not target_path.exists()
    _assert_invalid_path_apply_evidence(database_file)


def test_library_identity_survives_root_path_change_in_sqlite_storage(tmp_path: Path) -> None:
    """Relinking updates the runtime root without duplicating managed records."""
    database_file = tmp_path / "omym2.sqlite3"
    original_root = tmp_path / "library"
    moved_root = tmp_path / "moved-library"
    original_root.mkdir()
    moved_root.mkdir()
    _register_library(database_file, str(original_root))
    _register_duplicate_track(database_file)

    with SQLiteUnitOfWork(database_file) as uow:
        library = uow.libraries.get(LIBRARY_ID)
        assert library is not None
        uow.libraries.save(library.with_root_path(str(moved_root), BASE_TIME))
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        library_by_id = uow.libraries.get(LIBRARY_ID)
        library_by_old_root = uow.libraries.find_by_root_path(str(original_root))
        library_by_new_root = uow.libraries.find_by_root_path(str(moved_root))
        tracks = tuple(uow.tracks.list_by_library(LIBRARY_ID))

    assert library_by_id is not None
    assert library_by_id.library_id == LIBRARY_ID
    assert library_by_id.root_path == str(moved_root)
    assert library_by_old_root is None
    assert library_by_new_root == library_by_id
    assert tuple(track.track_id for track in tracks) == (DUPLICATE_TRACK_ID,)
    assert tracks[0].library_id == LIBRARY_ID
    assert tracks[0].current_path == REGISTERED_TRACK_PATH


class MutableConfigStore:
    """ConfigStore fake that can change between planning and apply."""

    def __init__(self, config: AppConfig) -> None:
        """Store the current config."""
        self._config: AppConfig = config
        self._config_revision: str = CONFIG_REVISION

    def read_snapshot(self) -> ConfigSnapshot:
        """Return current settings with their test revision."""
        return ConfigSnapshot(
            state=ConfigSnapshotState.VALID,
            config=self._config,
            config_revision=self._config_revision,
        )

    def load(self) -> AppConfig:
        """Return the current config."""
        return self._config

    def save(self, config: AppConfig, *, expected_config_revision: str) -> ConfigSnapshot:
        """Replace current settings only for the matching test revision."""
        if expected_config_revision != self._config_revision:
            raise ConfigRevisionMismatchError(expected_config_revision, self._config_revision)
        self._config = config
        self._config_revision = SAVED_CONFIG_REVISION
        return self.read_snapshot()


@dataclass(frozen=True, slots=True)
class MappingMetadataReader:
    """MetadataReader fake keyed by filesystem path text."""

    metadata_by_path: Mapping[str, TrackMetadata]

    def read(self, path: FileSystemPath) -> TrackMetadata:
        """Return metadata for the requested file."""
        return self.metadata_by_path[str(path)]


@dataclass(frozen=True, slots=True)
class AssertingFileMover:
    """FileMover wrapper that checks durable state before delegating."""

    database_file: Path
    delegate: FileMover = field(default_factory=FilesystemFileMover)

    def move(  # noqa: PLR0913  # Wrapper mirrors the stable FileMover safety port.
        self,
        source: FileSystemPath,
        target: FileSystemPath,
        *,
        source_root: FileSystemPath | None = None,
        target_root: FileSystemPath | None = None,
        expected_source_identity: FilesystemIdentity | None = None,
        expected_source_content_hash: str | None = None,
    ) -> None:
        """Assert pending FileEvent state exists before the filesystem mutation."""
        with SQLiteUnitOfWork(self.database_file) as uow:
            run = uow.runs.get(RUN_ID)
            plan = uow.plans.get(PLAN_ID)
            events = tuple(uow.file_events.list_by_run(RUN_ID))

        assert run is not None
        assert run.status == RunStatus.RUNNING
        assert plan is not None
        assert plan.status == PlanStatus.APPLYING
        assert len(events) == 1
        assert events[0].status == FileEventStatus.PENDING
        self.delegate.move(
            source,
            target,
            source_root=source_root,
            target_root=target_root,
            expected_source_identity=expected_source_identity,
            expected_source_content_hash=expected_source_content_hash,
        )


@dataclass(slots=True)
class ReplaceSourceBeforeMoveFileMover:
    """Replace a source after Apply captures it but before the concrete mover opens it."""

    delegate: FileMover = field(default_factory=FilesystemFileMover)
    expected_mtime_ns: int | None = field(default=None, init=False)

    def move(  # noqa: PLR0913  # Wrapper mirrors the stable FileMover safety port.
        self,
        source: FileSystemPath,
        target: FileSystemPath,
        *,
        source_root: FileSystemPath | None = None,
        target_root: FileSystemPath | None = None,
        expected_source_identity: FilesystemIdentity | None = None,
        expected_source_content_hash: str | None = None,
    ) -> None:
        """Install an indistinguishable replacement before delegating the mutation."""
        assert expected_source_identity is not None
        source_path = Path(source)
        content = source_path.read_bytes()
        _ = source_path.rename(source_path.with_name(REPLACED_SOURCE_BACKUP_NAME))
        _ = source_path.write_bytes(content)
        os.utime(
            source_path,
            ns=(expected_source_identity.mtime_ns, expected_source_identity.mtime_ns),
        )
        self.expected_mtime_ns = expected_source_identity.mtime_ns
        self.delegate.move(
            source,
            target,
            source_root=source_root,
            target_root=target_root,
            expected_source_identity=expected_source_identity,
            expected_source_content_hash=expected_source_content_hash,
        )


@dataclass(frozen=True, slots=True)
class DeleteSourceBeforeMoveFileMover:
    """Delete a source after the caller has verified pending FileEvent state."""

    delegate: FileMover = field(default_factory=FilesystemFileMover)

    def move(  # noqa: PLR0913  # Wrapper mirrors the stable FileMover safety port.
        self,
        source: FileSystemPath,
        target: FileSystemPath,
        *,
        source_root: FileSystemPath | None = None,
        target_root: FileSystemPath | None = None,
        expected_source_identity: FilesystemIdentity | None = None,
        expected_source_content_hash: str | None = None,
    ) -> None:
        """Delete the source leaf before delegating to the concrete mover."""
        Path(source).unlink()
        self.delegate.move(
            source,
            target,
            source_root=source_root,
            target_root=target_root,
            expected_source_identity=expected_source_identity,
            expected_source_content_hash=expected_source_content_hash,
        )


@dataclass(frozen=True, slots=True)
class MixedIncomingSetup:
    """Paths and adapters for the mixed e2e incoming workflow."""

    database_file: Path
    library_root: Path
    incoming_root: Path
    success_file: Path
    duplicate_file: Path
    blocked_file: Path
    config_store: MutableConfigStore
    snapshot_reader: FilesystemFileSnapshotReader


def _setup_mixed_incoming_library(tmp_path: Path) -> MixedIncomingSetup:
    database_file = tmp_path / "omym2.sqlite3"
    library_root = tmp_path / "library"
    incoming_root = tmp_path / "incoming"
    library_root.mkdir()
    incoming_root.mkdir()
    success_file = incoming_root / "01 Title.flac"
    duplicate_file = incoming_root / "02 Duplicate.flac"
    blocked_file = incoming_root / "03 Blocked.flac"
    _ = success_file.write_bytes(SUCCESS_CONTENT)
    _ = duplicate_file.write_bytes(DUPLICATE_CONTENT)
    _ = blocked_file.write_bytes(BLOCKED_CONTENT)
    metadata_by_path = {
        str(success_file): _metadata(title="Title", track_number=2),
        str(duplicate_file): _metadata(title="Duplicate", track_number=3),
        str(blocked_file): TrackMetadata(title="Blocked", album="Album", year=2026, track_number=4, disc_number=1),
    }
    config_store = MutableConfigStore(default_app_config())
    snapshot_reader = FilesystemFileSnapshotReader(
        metadata_reader=MappingMetadataReader(metadata_by_path),
        clock=FixedClock(BASE_TIME),
    )
    _register_library(database_file, str(library_root))
    _register_duplicate_track(database_file)
    return MixedIncomingSetup(
        database_file=database_file,
        library_root=library_root,
        incoming_root=incoming_root,
        success_file=success_file,
        duplicate_file=duplicate_file,
        blocked_file=blocked_file,
        config_store=config_store,
        snapshot_reader=snapshot_reader,
    )


def _create_mixed_plan(setup: MixedIncomingSetup):
    add_ports = CreateAddPlanPorts(
        uow=SQLiteUnitOfWork(setup.database_file),
        file_scanner=FilesystemFileScanner(),
        file_snapshot_reader=setup.snapshot_reader,
        file_presence=FilesystemFilePresence(),
        config_store=setup.config_store,
        path_resolver=FilesystemPathResolver(),
        clock=FixedClock(BASE_TIME),
        id_generator=SequenceIdGenerator(
            plan_ids=deque((PLAN_ID,)),
            action_ids=deque((MOVE_ACTION_ID, DUPLICATE_ACTION_ID, BLOCKED_ACTION_ID)),
        ),
    )
    return CreateAddPlanUseCase(add_ports).execute(CreateAddPlanRequest(str(setup.incoming_root)))


def _apply_plan_with_asserting_mover(setup: MixedIncomingSetup, plan_id: PlanId):
    apply_ports = ApplyPlanPorts(
        uow=SQLiteUnitOfWork(setup.database_file),
        file_mover=AssertingFileMover(setup.database_file),
        file_snapshot_reader=setup.snapshot_reader,
        path_resolver=FilesystemPathResolver(),
        clock=FixedClock(BASE_TIME),
        id_generator=SequenceIdGenerator(
            run_ids=deque((RUN_ID,)),
            event_ids=deque((EVENT_ID,)),
            track_ids=deque((TRACK_ID,)),
            operation_ids=deque((OPERATION_ID,)),
        ),
    )
    return _execute_claimed_apply(apply_ports, plan_id)


def _execute_claimed_apply(apply_ports: ApplyPlanPorts, plan_id: PlanId):
    claim = ClaimApplyUseCase(apply_ports).execute(
        ClaimApplyRequest(
            plan_id=plan_id,
            idempotency_key=OPERATION_IDEMPOTENCY_KEY,
            request_fingerprint=OPERATION_REQUEST_FINGERPRINT,
        )
    )
    assert claim.is_new
    assert isinstance(claim.lookup, Operation)
    with apply_ports.uow as uow:
        uow.operations.save(claim.lookup.mark_running(BASE_TIME))
        uow.commit()
    return ApplyPlanUseCase(apply_ports).execute(
        ApplyPlanRequest(
            plan_id=plan_id,
            run_id=RUN_ID,
            operation_id=OPERATION_ID,
            options=ApplyOptions(yes=True),
        )
    )


def _add_ports(
    database_file: Path,
    incoming_root: Path,
    config_store: MutableConfigStore,
    snapshot_reader: FilesystemFileSnapshotReader,
) -> CreateAddPlanPorts:
    del incoming_root
    return CreateAddPlanPorts(
        uow=SQLiteUnitOfWork(database_file),
        file_scanner=FilesystemFileScanner(),
        file_snapshot_reader=snapshot_reader,
        file_presence=FilesystemFilePresence(),
        config_store=config_store,
        path_resolver=FilesystemPathResolver(),
        clock=FixedClock(BASE_TIME),
        id_generator=SequenceIdGenerator(
            plan_ids=deque((PLAN_ID,)),
            action_ids=deque((MOVE_ACTION_ID,)),
        ),
    )


def _apply_ports(
    database_file: Path,
    snapshot_reader: FilesystemFileSnapshotReader,
    file_mover: FileMover,
) -> ApplyPlanPorts:
    return ApplyPlanPorts(
        uow=SQLiteUnitOfWork(database_file),
        file_mover=file_mover,
        file_snapshot_reader=snapshot_reader,
        path_resolver=FilesystemPathResolver(),
        clock=FixedClock(BASE_TIME),
        id_generator=SequenceIdGenerator(
            run_ids=deque((RUN_ID,)),
            event_ids=deque((EVENT_ID,)),
            operation_ids=deque((OPERATION_ID,)),
        ),
    )


def _managed_snapshot_reader(source_path: Path) -> FilesystemFileSnapshotReader:
    return FilesystemFileSnapshotReader(
        metadata_reader=MappingMetadataReader({str(source_path): _metadata(title="Managed", track_number=2)}),
        clock=FixedClock(BASE_TIME),
    )


def _save_managed_move_plan(
    database_file: Path,
    library_root: Path,
    *,
    source_path: str = MANAGED_SOURCE_PATH,
    target_path: str = MANAGED_TARGET_PATH,
) -> None:
    metadata = _metadata(title="Managed", track_number=2)
    with SQLiteUnitOfWork(database_file) as uow:
        uow.plans.save(
            Plan(
                plan_id=PLAN_ID,
                library_id=LIBRARY_ID,
                plan_type=PlanType.ORGANIZE,
                status=PlanStatus.READY,
                created_at=BASE_TIME,
                config_hash=PLAN_CONFIG_HASH,
                library_root_at_plan=str(library_root),
            )
        )
        uow.plan_actions.save(
            PlanAction(
                action_id=MOVE_ACTION_ID,
                plan_id=PLAN_ID,
                library_id=LIBRARY_ID,
                track_id=None,
                action_type=ActionType.MOVE,
                source_path=source_path,
                target_path=target_path,
                content_hash_at_plan=calculate_content_fingerprint(SUCCESS_CONTENT),
                metadata_hash_at_plan=calculate_metadata_fingerprint(metadata),
                status=ActionStatus.PLANNED,
                reason=None,
                sort_order=PLAN_ACTION_SORT_ORDER_START,
            )
        )
        uow.commit()


def _assert_invalid_path_apply_evidence(database_file: Path) -> None:
    with SQLiteUnitOfWork(database_file) as uow:
        actions = tuple(uow.plan_actions.list_by_plan(PLAN_ID))
        events = tuple(uow.file_events.list_by_run(RUN_ID))

    assert len(actions) == 1
    assert actions[0].status == ActionStatus.FAILED
    assert actions[0].reason == PlanActionReason.INVALID_PATH
    assert len(events) == 1
    assert events[0].status == FileEventStatus.FAILED
    assert events[0].error_code == PlanActionReason.INVALID_PATH.value


def _register_library(database_file: Path, library_root: str) -> None:
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(
            Library(
                library_id=LIBRARY_ID,
                root_path=library_root,
                path_policy_hash=calculate_path_policy_fingerprint(
                    default_app_config().path_policy,
                    default_app_config().artist_ids,
                ),
                registered_at=BASE_TIME,
                status=LibraryStatus.REGISTERED,
                created_at=BASE_TIME,
                updated_at=BASE_TIME,
            )
        )
        uow.commit()


def _register_duplicate_track(database_file: Path) -> None:
    metadata = _metadata(title="Duplicate", track_number=3)
    with SQLiteUnitOfWork(database_file) as uow:
        uow.tracks.save(
            Track(
                track_id=DUPLICATE_TRACK_ID,
                library_id=LIBRARY_ID,
                current_path=REGISTERED_TRACK_PATH,
                canonical_path=REGISTERED_TRACK_PATH,
                content_hash=calculate_content_fingerprint(DUPLICATE_CONTENT),
                metadata_hash=calculate_metadata_fingerprint(metadata),
                size=None,
                mtime=None,
                metadata=metadata,
                status=TrackStatus.ACTIVE,
                first_seen_at=BASE_TIME,
                last_seen_at=BASE_TIME,
                updated_at=BASE_TIME,
            )
        )
        uow.commit()


def _action_by_source(actions: tuple[PlanAction, ...], source_path: str) -> PlanAction:
    for action in actions:
        if action.source_path == source_path:
            return action
    raise AssertionError(source_path)


def _library_managed_paths(move_action: PlanAction, event: FileEvent, tracks: tuple[Track, ...]) -> tuple[str, ...]:
    track_paths = tuple(path for track in tracks for path in (track.current_path, track.canonical_path))
    assert move_action.target_path is not None
    return (move_action.target_path, event.target_path, *track_paths)


def _metadata(title: str, track_number: int) -> TrackMetadata:
    return TrackMetadata(
        title=title,
        artist="Artist",
        album="Album",
        year=2026,
        track_number=track_number,
        disc_number=1,
    )
