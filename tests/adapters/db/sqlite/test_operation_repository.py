"""
Summary: Tests durable Operation SQLite persistence and migration constraints.
Why: Ensures polling, idempotency, reconciliation, and retention survive process boundaries safely.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast
from uuid import UUID

import pytest

from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.db.sqlite import migration_runner
from omym2.adapters.db.sqlite.migration_runner import migrate_database
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.operation import (
    CheckCompletedResult,
    Operation,
    OperationError,
    OperationErrorCode,
    OperationKind,
    OperationProgress,
    OperationRemediation,
    OperationStatus,
    OperationTombstone,
    PlanCreatedResult,
    RegisteredWithoutPlanResult,
    RunCompletedResult,
)
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.run import Run, RunStatus
from omym2.shared.ids import CheckRunId, LibraryId, OperationId, PlanId, RunId

if TYPE_CHECKING:
    from pathlib import Path

BASE_TIME = datetime(2026, 7, 13, tzinfo=UTC)
STARTED_TIME = BASE_TIME + timedelta(seconds=1)
COMPLETED_TIME = STARTED_TIME + timedelta(seconds=1)
RESULT_EXPIRY_TIME = COMPLETED_TIME + timedelta(hours=24)
TOMBSTONE_EXPIRY_TIME = COMPLETED_TIME + timedelta(days=30)
LATER_TIME = TOMBSTONE_EXPIRY_TIME + timedelta(seconds=1)
IDEMPOTENCY_KEY = UUID("1e53732d-4b41-4833-b27a-e3f58bcfc764")
SECOND_IDEMPOTENCY_KEY = UUID("720c188c-41d0-4cb3-a2fe-5fa7ad1af0b7")
THIRD_IDEMPOTENCY_KEY = UUID("62b844c8-6194-4aeb-9905-c7b039946950")
OPERATION_ID = OperationId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345686"))
SECOND_OPERATION_ID = OperationId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345687"))
THIRD_OPERATION_ID = OperationId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345688"))
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567a"))
RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567d"))
CHECK_RUN_ID = CheckRunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345684"))
REQUEST_FINGERPRINT = "request-fingerprint"
SECOND_REQUEST_FINGERPRINT = "second-request-fingerprint"
THIRD_REQUEST_FINGERPRINT = "third-request-fingerprint"
CONFIG_HASH = "config-hash"
LIBRARY_ROOT = "/music/library"
ISSUE_COUNT = 2
TRACK_COUNT = 3
COMPLETED_UNITS = 2
TOTAL_UNITS = 5
OPERATION_MIGRATION_NAME = "202607130001_operations.sql"
OPERATION_RETENTION_MIGRATION_NAME = "202607140001_operation_retention_tombstones.sql"
TERMINAL_ERROR_MESSAGE = "The Operation stopped without a result."
LEGACY_FIXTURE_MISMATCH_MESSAGE = "The packaged Operation migration no longer matches the legacy fixture."

REQUIRED_OPERATION_INDEXES = {
    "idx_operations_plan",
    "idx_operations_result_expiry",
    "idx_operations_run",
    "idx_operations_status_updated",
    "idx_operations_tombstone_expiry",
    "uq_operations_idempotency_key",
    "uq_operations_single_active",
}
REQUIRED_OPERATION_COLUMNS = {
    "operation_id",
    "library_id",
    "plan_id",
    "run_id",
    "kind",
    "status",
    "idempotency_key",
    "request_fingerprint",
    "stage_code",
    "completed_units",
    "total_units",
    "progress_message",
    "result_kind",
    "result_json",
    "error_code",
    "error_json",
    "requested_at",
    "started_at",
    "updated_at",
    "completed_at",
    "result_expires_at",
    "tombstone_expires_at",
}


def test_operation_migration_preserves_existing_managed_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The forward Operation migration leaves previously managed rows unchanged."""
    database_file = default_application_paths(tmp_path).database_file
    packaged_migrations = migration_runner.load_packaged_migrations()
    prior_migrations = tuple(
        migration for migration in packaged_migrations if migration.name < OPERATION_MIGRATION_NAME
    )

    with monkeypatch.context() as patched:
        patched.setattr(migration_runner, "load_packaged_migrations", lambda: prior_migrations)
        with SQLiteUnitOfWork(database_file) as uow:
            uow.libraries.save(_library())
            uow.commit()

    migrate_database(database_file)

    assert "operations" in _table_names(database_file)
    assert _operation_column_names(database_file) == REQUIRED_OPERATION_COLUMNS
    assert _index_names(database_file) >= REQUIRED_OPERATION_INDEXES
    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.libraries.get(LIBRARY_ID) == _library()


@pytest.mark.parametrize(
    ("kind", "result"),
    [
        (OperationKind.ADD_PLAN, PlanCreatedResult(PLAN_ID)),
        (OperationKind.ORGANIZE_PLAN, RegisteredWithoutPlanResult(LIBRARY_ID, TRACK_COUNT)),
        (OperationKind.CHECK, CheckCompletedResult((CHECK_RUN_ID,), ISSUE_COUNT)),
        (OperationKind.APPLY_PLAN, RunCompletedResult(RUN_ID)),
    ],
)
def test_sqlite_operation_repository_round_trips_typed_results(
    tmp_path: Path,
    kind: OperationKind,
    result: PlanCreatedResult | RegisteredWithoutPlanResult | CheckCompletedResult | RunCompletedResult,
) -> None:
    """Every result discriminant restores the exact typed Operation payload."""
    database_file = default_application_paths(tmp_path).database_file
    succeeded = (
        _queued(kind)
        .mark_running(STARTED_TIME)
        .mark_succeeded(
            result=result,
            completed_at=COMPLETED_TIME,
            result_expires_at=RESULT_EXPIRY_TIME,
            tombstone_expires_at=TOMBSTONE_EXPIRY_TIME,
        )
    )

    with SQLiteUnitOfWork(database_file) as uow:
        _save_associations(uow)
        uow.operations.save(succeeded)
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.operations.lookup(OPERATION_ID) == succeeded
        assert uow.operations.find_by_idempotency_key(IDEMPOTENCY_KEY) == succeeded
        assert uow.operations.find_active() is None


def test_operation_retention_migration_upgrades_original_constraint_and_preserves_terminal_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing strict terminal rows survive migration and can become tombstones."""
    database_file = default_application_paths(tmp_path).database_file
    packaged_migrations = migration_runner.load_packaged_migrations()
    legacy_migrations = tuple(
        migration_runner.SQLiteMigration(
            name=migration.name,
            sql=_original_operation_constraint(migration.sql),
        )
        if migration.name == OPERATION_MIGRATION_NAME
        else migration
        for migration in packaged_migrations
        if migration.name < OPERATION_RETENTION_MIGRATION_NAME
    )
    error = OperationError(
        code=OperationErrorCode.OPERATION_FAILED,
        message=TERMINAL_ERROR_MESSAGE,
        retryable=False,
    )
    interrupted_error = OperationError(
        code=OperationErrorCode.OPERATION_INTERRUPTED,
        message=TERMINAL_ERROR_MESSAGE,
        retryable=False,
    )
    terminal_operations = (
        _queued(OperationKind.CHECK)
        .mark_running(STARTED_TIME)
        .mark_succeeded(
            result=CheckCompletedResult((CHECK_RUN_ID,), ISSUE_COUNT),
            completed_at=COMPLETED_TIME,
            result_expires_at=RESULT_EXPIRY_TIME,
            tombstone_expires_at=TOMBSTONE_EXPIRY_TIME,
        ),
        _queued(
            OperationKind.CHECK,
            operation_id=SECOND_OPERATION_ID,
            idempotency_key=SECOND_IDEMPOTENCY_KEY,
            request_fingerprint=SECOND_REQUEST_FINGERPRINT,
        )
        .mark_running(STARTED_TIME)
        .mark_failed(
            error=error,
            completed_at=COMPLETED_TIME,
            result_expires_at=RESULT_EXPIRY_TIME,
            tombstone_expires_at=TOMBSTONE_EXPIRY_TIME,
        ),
        _queued(
            OperationKind.CHECK,
            operation_id=THIRD_OPERATION_ID,
            idempotency_key=THIRD_IDEMPOTENCY_KEY,
            request_fingerprint=THIRD_REQUEST_FINGERPRINT,
        )
        .mark_running(STARTED_TIME)
        .mark_interrupted(
            error=interrupted_error,
            completed_at=COMPLETED_TIME,
            result_expires_at=RESULT_EXPIRY_TIME,
            tombstone_expires_at=TOMBSTONE_EXPIRY_TIME,
        ),
    )

    with monkeypatch.context() as patched:
        patched.setattr(migration_runner, "load_packaged_migrations", lambda: legacy_migrations)
        with SQLiteUnitOfWork(database_file) as uow:
            uow.libraries.save(_library())
            for operation in terminal_operations:
                uow.operations.save(operation)
            uow.commit()

    with SQLiteUnitOfWork(database_file) as uow, pytest.raises(sqlite3.IntegrityError):
        _ = uow.operations.expire_terminal_payloads(RESULT_EXPIRY_TIME)

    rows_before_migration = _operation_rows(database_file)

    migrate_database(database_file)

    assert OPERATION_RETENTION_MIGRATION_NAME in _applied_migrations(database_file)
    assert _operation_rows(database_file) == rows_before_migration
    assert _operation_column_names(database_file) == REQUIRED_OPERATION_COLUMNS
    assert _index_names(database_file) >= REQUIRED_OPERATION_INDEXES

    with SQLiteUnitOfWork(database_file) as uow:
        assert (
            tuple(uow.operations.lookup(operation.operation_id) for operation in terminal_operations)
            == terminal_operations
        )
        assert uow.operations.expire_terminal_payloads(RESULT_EXPIRY_TIME) == len(terminal_operations)
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        assert tuple(uow.operations.lookup(operation.operation_id) for operation in terminal_operations) == tuple(
            OperationTombstone(
                operation_id=operation.operation_id,
                idempotency_key=operation.idempotency_key,
                kind=operation.kind,
                request_fingerprint=operation.request_fingerprint,
                tombstone_expires_at=TOMBSTONE_EXPIRY_TIME,
            )
            for operation in terminal_operations
        )


def test_sqlite_operation_repository_round_trips_progress_errors_and_candidates(tmp_path: Path) -> None:
    """Interrupted snapshots retain detail but are not repeatedly reconciled."""
    database_file = default_application_paths(tmp_path).database_file
    progress = OperationProgress(
        stage_code="inspect_files",
        completed_units=COMPLETED_UNITS,
        total_units=TOTAL_UNITS,
        message="Inspecting files",
    )
    running = _queued(OperationKind.CHECK).mark_running(STARTED_TIME).update_progress(progress, STARTED_TIME)
    interruption = OperationError(
        code=OperationErrorCode.OPERATION_INTERRUPTED,
        message="The worker stopped before completion.",
        retryable=False,
        remediation=OperationRemediation(label="Open Health", route="/health", command="omym2 check"),
    )
    interrupted = running.mark_interrupted(
        error=interruption,
        completed_at=COMPLETED_TIME,
        result_expires_at=RESULT_EXPIRY_TIME,
        tombstone_expires_at=TOMBSTONE_EXPIRY_TIME,
    )

    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.operations.save(interrupted)
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.operations.lookup(OPERATION_ID) == interrupted
        assert uow.operations.list_reconciliation_candidates() == ()


@pytest.mark.parametrize(
    ("plan_applying", "run_running", "is_candidate"),
    [
        (True, False, True),
        (False, True, True),
        (False, False, False),
    ],
)
def test_sqlite_operation_repository_reconciles_interrupted_apply_only_with_unfinished_managed_state(
    tmp_path: Path,
    *,
    plan_applying: bool,
    run_running: bool,
    is_candidate: bool,
) -> None:
    """Interrupted Apply remains eligible only while its Plan or Run still needs repair."""
    database_file = default_application_paths(tmp_path).database_file
    plan = _plan().mark_applying() if plan_applying else _plan().mark_failed()
    run = _run() if run_running else _run().mark_failed(COMPLETED_TIME, TERMINAL_ERROR_MESSAGE)
    error = OperationError(
        code=OperationErrorCode.OPERATION_INTERRUPTED,
        message=TERMINAL_ERROR_MESSAGE,
        retryable=False,
    )
    interrupted = (
        Operation.queued(
            operation_id=OPERATION_ID,
            kind=OperationKind.APPLY_PLAN,
            idempotency_key=IDEMPOTENCY_KEY,
            request_fingerprint=REQUEST_FINGERPRINT,
            requested_at=BASE_TIME,
            library_id=LIBRARY_ID,
            plan_id=PLAN_ID,
            run_id=RUN_ID,
        )
        .mark_running(STARTED_TIME)
        .mark_interrupted(
            error=error,
            completed_at=COMPLETED_TIME,
            result_expires_at=RESULT_EXPIRY_TIME,
            tombstone_expires_at=TOMBSTONE_EXPIRY_TIME,
        )
    )

    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.plans.save(plan)
        uow.runs.save(run)
        uow.operations.save(interrupted)
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        candidates = uow.operations.list_reconciliation_candidates()

    assert (candidates == (interrupted,)) is is_candidate


def test_sqlite_operation_repository_enforces_global_idempotency_and_single_active_row(tmp_path: Path) -> None:
    """SQLite rejects a reused idempotency key and a second queued/running Operation."""
    database_file = default_application_paths(tmp_path).database_file
    queued = _queued(OperationKind.CHECK)

    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.operations.save(queued)
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.operations.find_active() == queued
        with pytest.raises(sqlite3.IntegrityError):
            uow.operations.save(
                _queued(
                    OperationKind.CHECK,
                    operation_id=SECOND_OPERATION_ID,
                    idempotency_key=SECOND_IDEMPOTENCY_KEY,
                    request_fingerprint=SECOND_REQUEST_FINGERPRINT,
                )
            )

    succeeded = queued.mark_running(STARTED_TIME).mark_succeeded(
        result=CheckCompletedResult((CHECK_RUN_ID,), ISSUE_COUNT),
        completed_at=COMPLETED_TIME,
        result_expires_at=RESULT_EXPIRY_TIME,
        tombstone_expires_at=TOMBSTONE_EXPIRY_TIME,
    )
    duplicate_key = (
        _queued(
            OperationKind.CHECK,
            operation_id=SECOND_OPERATION_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            request_fingerprint=SECOND_REQUEST_FINGERPRINT,
        )
        .mark_running(STARTED_TIME)
        .mark_succeeded(
            result=CheckCompletedResult((CHECK_RUN_ID,), ISSUE_COUNT),
            completed_at=COMPLETED_TIME,
            result_expires_at=RESULT_EXPIRY_TIME,
            tombstone_expires_at=TOMBSTONE_EXPIRY_TIME,
        )
    )
    with SQLiteUnitOfWork(database_file) as uow:
        uow.operations.save(succeeded)
        uow.commit()
    with SQLiteUnitOfWork(database_file) as uow, pytest.raises(sqlite3.IntegrityError):
        uow.operations.save(duplicate_key)


def test_sqlite_operation_migration_rejects_invalid_progress_pairs(tmp_path: Path) -> None:
    """The schema rejects malformed progress even when a caller bypasses the domain model."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.operations.save(_queued(OperationKind.CHECK))
        uow.commit()

    with sqlite3.connect(database_file) as connection, pytest.raises(sqlite3.IntegrityError):
        _ = connection.execute(
            "UPDATE operations SET completed_units = ? WHERE operation_id = ?",
            (COMPLETED_UNITS, str(OPERATION_ID)),
        )


def test_sqlite_operation_migration_rejects_invalid_stage_codes(tmp_path: Path) -> None:
    """The schema rejects non-snake-case stage codes even when a caller bypasses the domain model."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.operations.save(_queued(OperationKind.CHECK))
        uow.commit()

    with sqlite3.connect(database_file) as connection, pytest.raises(sqlite3.IntegrityError):
        _ = connection.execute(
            "UPDATE operations SET stage_code = ? WHERE operation_id = ?",
            ("Invalid Stage", str(OPERATION_ID)),
        )


def test_sqlite_operation_migration_requires_success_result_payload(tmp_path: Path) -> None:
    """A success discriminant cannot be persisted without its typed JSON payload."""
    database_file = default_application_paths(tmp_path).database_file
    succeeded = (
        _queued(OperationKind.CHECK)
        .mark_running(STARTED_TIME)
        .mark_succeeded(
            result=CheckCompletedResult((CHECK_RUN_ID,), ISSUE_COUNT),
            completed_at=COMPLETED_TIME,
            result_expires_at=RESULT_EXPIRY_TIME,
            tombstone_expires_at=TOMBSTONE_EXPIRY_TIME,
        )
    )
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.operations.save(succeeded)
        uow.commit()

    with sqlite3.connect(database_file) as connection, pytest.raises(sqlite3.IntegrityError):
        _ = connection.execute(
            "UPDATE operations SET result_json = NULL WHERE operation_id = ?",
            (str(OPERATION_ID),),
        )


@pytest.mark.parametrize("status", [OperationStatus.FAILED, OperationStatus.INTERRUPTED])
def test_sqlite_operation_migration_requires_terminal_error_payload(
    tmp_path: Path,
    status: OperationStatus,
) -> None:
    """A failure discriminant cannot be persisted without its redacted JSON payload."""
    database_file = default_application_paths(tmp_path).database_file
    running = _queued(OperationKind.CHECK).mark_running(STARTED_TIME)
    error = OperationError(
        code=(
            OperationErrorCode.OPERATION_FAILED
            if status is OperationStatus.FAILED
            else OperationErrorCode.OPERATION_INTERRUPTED
        ),
        message=TERMINAL_ERROR_MESSAGE,
        retryable=False,
    )
    terminal = (
        running.mark_failed(
            error=error,
            completed_at=COMPLETED_TIME,
            result_expires_at=RESULT_EXPIRY_TIME,
            tombstone_expires_at=TOMBSTONE_EXPIRY_TIME,
        )
        if status is OperationStatus.FAILED
        else running.mark_interrupted(
            error=error,
            completed_at=COMPLETED_TIME,
            result_expires_at=RESULT_EXPIRY_TIME,
            tombstone_expires_at=TOMBSTONE_EXPIRY_TIME,
        )
    )
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.operations.save(terminal)
        uow.commit()

    with sqlite3.connect(database_file) as connection, pytest.raises(sqlite3.IntegrityError):
        _ = connection.execute(
            "UPDATE operations SET error_json = NULL WHERE operation_id = ?",
            (str(OPERATION_ID),),
        )


def test_sqlite_operation_retention_returns_tombstone_then_purges_without_touching_active(
    tmp_path: Path,
) -> None:
    """Result expiry produces 410 identity and tombstone expiry removes only terminal work."""
    database_file = default_application_paths(tmp_path).database_file
    succeeded = (
        _queued(OperationKind.CHECK)
        .mark_running(STARTED_TIME)
        .mark_succeeded(
            result=CheckCompletedResult((CHECK_RUN_ID,), ISSUE_COUNT),
            completed_at=COMPLETED_TIME,
            result_expires_at=RESULT_EXPIRY_TIME,
            tombstone_expires_at=TOMBSTONE_EXPIRY_TIME,
        )
    )
    active = _queued(
        OperationKind.CHECK,
        operation_id=SECOND_OPERATION_ID,
        idempotency_key=SECOND_IDEMPOTENCY_KEY,
        request_fingerprint=SECOND_REQUEST_FINGERPRINT,
        requested_at=COMPLETED_TIME,
    )
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        uow.operations.save(succeeded)
        uow.operations.save(active)
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.operations.expire_terminal_payloads(RESULT_EXPIRY_TIME) == 1
        assert uow.operations.expire_terminal_payloads(RESULT_EXPIRY_TIME) == 0
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        expired = uow.operations.lookup(OPERATION_ID)
        assert expired == OperationTombstone(
            operation_id=OPERATION_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            kind=OperationKind.CHECK,
            request_fingerprint=REQUEST_FINGERPRINT,
            tombstone_expires_at=TOMBSTONE_EXPIRY_TIME,
        )
        assert uow.operations.find_by_idempotency_key(IDEMPOTENCY_KEY) == expired
        assert uow.operations.find_active() == active
        assert uow.operations.purge_expired_tombstones(LATER_TIME) == 1
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        assert uow.operations.lookup(OPERATION_ID) is None
        assert uow.operations.lookup(SECOND_OPERATION_ID) == active


def _queued(
    kind: OperationKind,
    *,
    operation_id: OperationId = OPERATION_ID,
    idempotency_key: UUID = IDEMPOTENCY_KEY,
    request_fingerprint: str = REQUEST_FINGERPRINT,
    requested_at: datetime = BASE_TIME,
) -> Operation:
    return Operation.queued(
        operation_id=operation_id,
        kind=kind,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        requested_at=requested_at,
        library_id=LIBRARY_ID,
    )


def _save_associations(uow: SQLiteUnitOfWork) -> None:
    uow.libraries.save(_library())
    uow.plans.save(_plan())
    uow.runs.save(_run())


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


def _plan() -> Plan:
    return Plan(
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        plan_type=PlanType.ADD,
        status=PlanStatus.READY,
        created_at=BASE_TIME,
        config_hash=CONFIG_HASH,
        library_root_at_plan=LIBRARY_ROOT,
    )


def _run() -> Run:
    return Run(
        run_id=RUN_ID,
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        status=RunStatus.RUNNING,
        started_at=STARTED_TIME,
    )


def _table_names(database_file: Path) -> set[str]:
    with sqlite3.connect(database_file) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {str(row[0]) for row in cast("list[tuple[object, ...]]", rows)}


def _index_names(database_file: Path) -> set[str]:
    with sqlite3.connect(database_file) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'").fetchall()
    return {str(row[0]) for row in cast("list[tuple[object, ...]]", rows)}


def _operation_column_names(database_file: Path) -> set[str]:
    with sqlite3.connect(database_file) as connection:
        rows = connection.execute("SELECT name FROM pragma_table_info('operations')").fetchall()
    return {str(row[0]) for row in cast("list[tuple[object, ...]]", rows)}


def _operation_rows(database_file: Path) -> tuple[tuple[object, ...], ...]:
    with sqlite3.connect(database_file) as connection:
        rows = connection.execute("SELECT * FROM operations ORDER BY operation_id").fetchall()
    return tuple(cast("list[tuple[object, ...]]", rows))


def _applied_migrations(database_file: Path) -> set[str]:
    with sqlite3.connect(database_file) as connection:
        rows = connection.execute("SELECT migration_name FROM schema_migrations").fetchall()
    return {str(row[0]) for row in cast("list[tuple[object, ...]]", rows)}


def _original_operation_constraint(sql: str) -> str:
    replacements = (
        (
            """(status = 'succeeded' AND started_at IS NOT NULL AND completed_at IS NOT NULL AND
            error_code IS NULL AND error_json IS NULL AND""",
            """(status = 'succeeded' AND started_at IS NOT NULL AND completed_at IS NOT NULL AND
            result_kind IS NOT NULL AND error_code IS NULL AND error_json IS NULL AND""",
        ),
        (
            """(status = 'failed' AND started_at IS NOT NULL AND completed_at IS NOT NULL AND
            result_kind IS NULL AND result_json IS NULL AND""",
            """(status = 'failed' AND started_at IS NOT NULL AND completed_at IS NOT NULL AND
            result_kind IS NULL AND result_json IS NULL AND error_code IS NOT NULL AND""",
        ),
        (
            "            (error_code IS NULL OR error_code = 'operation_interrupted') AND",
            "            error_code = 'operation_interrupted' AND",
        ),
    )
    for current, original in replacements:
        if current not in sql:
            raise AssertionError(LEGACY_FIXTURE_MISMATCH_MESSAGE)
        sql = sql.replace(current, original, 1)
    return sql
