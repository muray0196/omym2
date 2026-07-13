"""
Summary: Tests atomic managed-resource and Operation success persistence.
Why: Prevents orphaned Plan success when a terminal Operation write fails.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

import pytest

from omym2.adapters.config.default_config import default_app_config
from omym2.adapters.db.sqlite.repositories import SQLiteOperationRepository
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.domain.models.file_scan_entry import FileScanEntry
from omym2.domain.models.file_snapshot import FileSnapshot
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.operation import Operation, OperationKind, OperationStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.config_fingerprint import calculate_path_policy_fingerprint
from omym2.domain.services.content_fingerprint import calculate_content_fingerprint
from omym2.domain.services.metadata_fingerprint import calculate_metadata_fingerprint
from omym2.features.add.dto import CreateAddPlanRequest
from omym2.features.add.ports import CreateAddPlanPorts
from omym2.features.add.usecases.create_add_plan import CreateAddPlanUseCase
from omym2.features.check.dto import CheckLibraryRequest
from omym2.features.check.ports import CheckLibraryPorts
from omym2.features.check.usecases.check_library import CheckLibraryUseCase
from omym2.features.organize.dto import CreateOrganizePlanRequest
from omym2.features.organize.ports import CreateOrganizePlanPorts
from omym2.features.organize.usecases.create_organize_plan import CreateOrganizePlanUseCase
from omym2.shared.ids import ActionId, CheckRunId, LibraryId, OperationId, PlanId
from tests.fakes.runtime import FixedClock, SequenceIdGenerator

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from omym2.domain.models.app_config import AppConfig
    from omym2.features.common_ports import FileSnapshotCaptureRequest, FileSystemPath

ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567b"))
BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CHECK_RUN_ID = CheckRunId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567c"))
FILE_CONTENT = b"audio"
FILE_SIZE = len(FILE_CONTENT)
IDEMPOTENCY_KEY = UUID("018f6a4f-3c2d-7b8a-9abc-def01234568f")
INCOMING_FILE = "/music/incoming/Title.flac"
INCOMING_ROOT = "/music/incoming"
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
LIBRARY_ROOT = "/music/library"
OPERATION_ID = OperationId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234568e"))
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567a"))
TERMINAL_SAVE_FAILURE_MESSAGE = "injected terminal Operation save failure"
UNEXPECTED_CONTENT_HASH_MESSAGE = "An empty Check fixture must not hash content."
UNEXPECTED_SNAPSHOT_MESSAGE = "An empty fixture must not capture file snapshots."
TRACK_METADATA = TrackMetadata(
    title="Title",
    artist="Artist",
    album="Album",
    year=2026,
    track_number=2,
    disc_number=1,
)


def test_add_plan_and_operation_success_roll_back_together(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed terminal write leaves the running Operation and no orphaned Plan."""
    database_path = tmp_path / "operation-atomicity.sqlite3"
    running = _running_operation()
    with SQLiteUnitOfWork(database_path) as uow:
        uow.libraries.save(_library())
        uow.operations.save(running)
        uow.commit()

    _inject_terminal_save_failure(monkeypatch)
    ports = CreateAddPlanPorts(
        uow=SQLiteUnitOfWork(database_path),
        file_scanner=_StaticScanner(),
        file_snapshot_reader=_StaticSnapshotReader(),
        file_presence=_MissingFilePresence(),
        config_store=_StaticConfigReader(),
        path_resolver=_SimplePathResolver(),
        clock=FixedClock(BASE_TIME),
        id_generator=SequenceIdGenerator(plan_ids=deque((PLAN_ID,)), action_ids=deque((ACTION_ID,))),
    )

    with pytest.raises(RuntimeError, match=TERMINAL_SAVE_FAILURE_MESSAGE):
        _ = CreateAddPlanUseCase(ports).execute(
            CreateAddPlanRequest(source_path=INCOMING_ROOT, operation_id=OPERATION_ID)
        )

    with SQLiteUnitOfWork(database_path) as uow:
        assert uow.plans.get(PLAN_ID) is None
        assert uow.plan_actions.get(ACTION_ID) is None
        assert uow.operations.lookup(OPERATION_ID) == running


def test_clean_organize_registration_and_operation_success_roll_back_together(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed terminal write cannot leave an orphaned registered Library."""
    database_path = tmp_path / "organize-operation-atomicity.sqlite3"
    running = _running_operation(OperationKind.ORGANIZE_PLAN)
    with SQLiteUnitOfWork(database_path) as uow:
        uow.operations.save(running)
        uow.commit()

    _inject_terminal_save_failure(monkeypatch)
    ports = CreateOrganizePlanPorts(
        uow=SQLiteUnitOfWork(database_path),
        file_scanner=_EmptyScanner(),
        file_snapshot_reader=_UnexpectedSnapshotReader(),
        config_store=_StaticConfigReader(),
        path_resolver=_SimplePathResolver(),
        clock=FixedClock(BASE_TIME),
        id_generator=SequenceIdGenerator(library_ids=deque((LIBRARY_ID,))),
    )

    with pytest.raises(RuntimeError, match=TERMINAL_SAVE_FAILURE_MESSAGE):
        _ = CreateOrganizePlanUseCase(ports).execute(
            CreateOrganizePlanRequest(
                trust_stat=False,
                library_root=LIBRARY_ROOT,
                operation_id=OPERATION_ID,
            )
        )

    with SQLiteUnitOfWork(database_path) as uow:
        assert uow.libraries.get(LIBRARY_ID) is None
        assert uow.operations.lookup(OPERATION_ID) == running


def test_check_run_and_operation_success_roll_back_together(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed terminal write cannot expose persisted Check evidence as successful work."""
    database_path = tmp_path / "check-operation-atomicity.sqlite3"
    running = _running_operation(OperationKind.CHECK)
    with SQLiteUnitOfWork(database_path) as uow:
        uow.libraries.save(_library())
        uow.operations.save(running)
        uow.commit()

    _inject_terminal_save_failure(monkeypatch)
    ports = CheckLibraryPorts(
        uow=SQLiteUnitOfWork(database_path),
        file_scanner=_EmptyScanner(),
        file_snapshot_reader=_UnexpectedSnapshotReader(),
        file_content_hasher=_UnexpectedContentHasher(),
        config_store=_StaticConfigReader(),
        path_resolver=_SimplePathResolver(),
        clock=FixedClock(BASE_TIME),
        id_generator=SequenceIdGenerator(check_run_ids=deque((CHECK_RUN_ID,))),
    )

    with pytest.raises(RuntimeError, match=TERMINAL_SAVE_FAILURE_MESSAGE):
        _ = CheckLibraryUseCase(ports).execute(
            CheckLibraryRequest(
                trust_stat=False,
                library_id=LIBRARY_ID,
                operation_id=OPERATION_ID,
            )
        )

    with SQLiteUnitOfWork(database_path) as uow:
        assert uow.check_runs.latest(LIBRARY_ID) is None
        assert uow.operations.lookup(OPERATION_ID) == running


def _inject_terminal_save_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    real_save = SQLiteOperationRepository.save

    def _fail_terminal_save(repository: SQLiteOperationRepository, operation: Operation) -> None:
        if operation.status is OperationStatus.SUCCEEDED:
            raise RuntimeError(TERMINAL_SAVE_FAILURE_MESSAGE)
        real_save(repository, operation)

    monkeypatch.setattr(SQLiteOperationRepository, "save", _fail_terminal_save)


def _running_operation(kind: OperationKind = OperationKind.ADD_PLAN) -> Operation:
    return Operation.queued(
        operation_id=OPERATION_ID,
        kind=kind,
        idempotency_key=IDEMPOTENCY_KEY,
        request_fingerprint=f"{kind.value}-request",
        requested_at=BASE_TIME,
        library_id=LIBRARY_ID if kind in {OperationKind.ADD_PLAN, OperationKind.CHECK} else None,
    ).mark_running(BASE_TIME)


def _library() -> Library:
    config = default_app_config()
    return Library(
        library_id=LIBRARY_ID,
        root_path=LIBRARY_ROOT,
        path_policy_hash=calculate_path_policy_fingerprint(config.path_policy, config.artist_ids),
        registered_at=BASE_TIME,
        status=LibraryStatus.REGISTERED,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


@dataclass(frozen=True, slots=True)
class _StaticConfigReader:
    def load(self) -> AppConfig:
        return default_app_config()


@dataclass(frozen=True, slots=True)
class _StaticScanner:
    def scan(self, root: FileSystemPath) -> tuple[FileScanEntry, ...]:
        assert root == INCOMING_ROOT
        return (FileScanEntry(INCOMING_FILE, FILE_SIZE, BASE_TIME, ".flac"),)


@dataclass(frozen=True, slots=True)
class _EmptyScanner:
    def scan(self, root: FileSystemPath) -> tuple[FileScanEntry, ...]:
        del root
        return ()


@dataclass(frozen=True, slots=True)
class _StaticSnapshotReader:
    def capture_many(self, requests: Sequence[FileSnapshotCaptureRequest]) -> tuple[FileSnapshot | None, ...]:
        assert tuple(request.path for request in requests) == (INCOMING_FILE,)
        return (
            FileSnapshot(
                path=INCOMING_FILE,
                size=FILE_SIZE,
                mtime=BASE_TIME,
                file_extension=".flac",
                content_hash=calculate_content_fingerprint(FILE_CONTENT),
                metadata_hash=calculate_metadata_fingerprint(TRACK_METADATA),
                metadata=TRACK_METADATA,
                filesystem_identity=None,
                captured_at=BASE_TIME,
            ),
        )


@dataclass(frozen=True, slots=True)
class _UnexpectedSnapshotReader:
    def capture_many(self, requests: Sequence[FileSnapshotCaptureRequest]) -> tuple[FileSnapshot | None, ...]:
        del requests
        raise AssertionError(UNEXPECTED_SNAPSHOT_MESSAGE)


@dataclass(frozen=True, slots=True)
class _UnexpectedContentHasher:
    def calculate(self, path: FileSystemPath) -> str:
        del path
        raise AssertionError(UNEXPECTED_CONTENT_HASH_MESSAGE)


@dataclass(frozen=True, slots=True)
class _MissingFilePresence:
    def exists(self, path: FileSystemPath) -> bool:
        del path
        return False


@dataclass(frozen=True, slots=True)
class _SimplePathResolver:
    def resolve_library_path(self, library_root: FileSystemPath, library_relative_path: str) -> str:
        return f"{str(library_root).rstrip('/')}/{library_relative_path}"

    def relative_to_library(self, library_root: FileSystemPath, path: FileSystemPath) -> str:
        return str(path).removeprefix(f"{str(library_root).rstrip('/')}/")
