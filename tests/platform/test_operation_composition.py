"""
Summary: Tests durable Operation worker and lock composition.
Why: Protects idempotent replay, async completion, and conservative reconciliation boundaries.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from typing import TYPE_CHECKING
from uuid import UUID

import pytest

from omym2.adapters.config.application_paths import default_application_paths
from omym2.config import OPERATION_RECONCILE_INTERVAL_SECONDS
from omym2.domain.models.operation import CheckCompletedResult, OperationKind, OperationStatus
from omym2.features.common_ports import (
    ExclusiveOperationBusyError,
    ExclusiveOperationRequest,
    IdempotencyKeyReusedError,
    SystemClock,
    Uuid7IdGenerator,
)
from omym2.features.operations.dto import ReserveOperationRequest
from omym2.features.operations.ports import OperationPorts
from omym2.features.operations.usecases.reserve_operation import (
    ClassifyOperationReplayUseCase,
    ReserveOperationUseCase,
)
from omym2.platform.feature_composition import build_uow
from omym2.platform.operation_composition import OperationRuntime
from omym2.platform.runtime_context import runtime_context_for
from omym2.shared.ids import CheckRunId, OperationId

if TYPE_CHECKING:
    from pathlib import Path

    from omym2.domain.models.operation import OperationLookup

IDEMPOTENCY_KEY = UUID("018f6a4f-3c2d-7b8a-9abc-def012345601")
CHECK_RUN_ID = CheckRunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345602"))
RECONCILIATION_FAILURE = "transient database failure"


def test_operation_runtime_replays_active_request_without_redispatch(tmp_path: Path) -> None:
    """An exact retained key returns the same Operation while its worker holds the lock."""
    paths = default_application_paths(tmp_path)
    runtime_context = runtime_context_for(paths.config_file, paths.database_file)
    runtime = OperationRuntime(runtime_context)
    started = Event()
    release = Event()
    work_count = 0

    def work(_operation_id: OperationId) -> CheckCompletedResult:
        nonlocal work_count
        work_count += 1
        started.set()
        _ = release.wait(OPERATION_RECONCILE_INTERVAL_SECONDS)
        return CheckCompletedResult(check_run_ids=(CHECK_RUN_ID,), issue_count=0)

    first = runtime.accept(
        kind=OperationKind.CHECK,
        idempotency_key=IDEMPOTENCY_KEY,
        canonical_request={"library_id": None},
        work=work,
    )
    assert started.wait(OPERATION_RECONCILE_INTERVAL_SECONDS)

    replay = runtime.accept(
        kind=OperationKind.CHECK,
        idempotency_key=IDEMPOTENCY_KEY,
        canonical_request={"library_id": None},
        work=work,
    )

    assert replay.is_new is False
    assert replay.lookup.operation_id == first.lookup.operation_id
    assert work_count == 1
    release.set()
    runtime.close()
    operation = runtime.get(first.lookup.operation_id)
    assert operation.status is OperationStatus.SUCCEEDED
    assert operation.result == CheckCompletedResult(check_run_ids=(CHECK_RUN_ID,), issue_count=0)


def test_operation_runtime_reclassifies_exact_replay_after_lock_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A request classified before its twin reserves replays after losing the lock race."""
    paths = default_application_paths(tmp_path)
    runtime_context = runtime_context_for(paths.config_file, paths.database_file)
    runtime = OperationRuntime(runtime_context)
    classified, resume = _pause_initial_replay_classification(monkeypatch)
    started = Event()
    release = Event()
    work_count = 0

    def work(_operation_id: OperationId) -> CheckCompletedResult:
        nonlocal work_count
        work_count += 1
        started.set()
        _ = release.wait(OPERATION_RECONCILE_INTERVAL_SECONDS)
        return CheckCompletedResult((CHECK_RUN_ID,), 0)

    racing_requests = ThreadPoolExecutor(max_workers=1)
    try:
        replay_future = racing_requests.submit(
            runtime.accept,
            kind=OperationKind.CHECK,
            idempotency_key=IDEMPOTENCY_KEY,
            canonical_request={"library_id": None},
            work=work,
        )
        assert classified.wait(OPERATION_RECONCILE_INTERVAL_SECONDS)
        accepted = runtime.accept(
            kind=OperationKind.CHECK,
            idempotency_key=IDEMPOTENCY_KEY,
            canonical_request={"library_id": None},
            work=work,
        )
        resume.set()
        replay = replay_future.result(timeout=OPERATION_RECONCILE_INTERVAL_SECONDS)

        assert started.wait(OPERATION_RECONCILE_INTERVAL_SECONDS)
        assert accepted.is_new is True
        assert replay.is_new is False
        assert replay.lookup.operation_id == accepted.lookup.operation_id
        assert work_count == 1
    finally:
        resume.set()
        release.set()
        racing_requests.shutdown(wait=True)
        runtime.close()


def test_operation_runtime_reclassifies_mismatched_key_after_lock_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A raced key reuse remains an idempotency conflict after the winner reserves."""
    paths = default_application_paths(tmp_path)
    runtime_context = runtime_context_for(paths.config_file, paths.database_file)
    runtime = OperationRuntime(runtime_context)
    classified, resume = _pause_initial_replay_classification(monkeypatch)
    release = Event()

    def work(_operation_id: OperationId) -> CheckCompletedResult:
        _ = release.wait(OPERATION_RECONCILE_INTERVAL_SECONDS)
        return CheckCompletedResult((CHECK_RUN_ID,), 0)

    racing_requests = ThreadPoolExecutor(max_workers=1)
    try:
        mismatch_future = racing_requests.submit(
            runtime.accept,
            kind=OperationKind.CHECK,
            idempotency_key=IDEMPOTENCY_KEY,
            canonical_request={"library_id": "changed"},
            work=work,
        )
        assert classified.wait(OPERATION_RECONCILE_INTERVAL_SECONDS)
        _ = runtime.accept(
            kind=OperationKind.CHECK,
            idempotency_key=IDEMPOTENCY_KEY,
            canonical_request={"library_id": None},
            work=work,
        )
        resume.set()

        with pytest.raises(IdempotencyKeyReusedError):
            _ = mismatch_future.result(timeout=OPERATION_RECONCILE_INTERVAL_SECONDS)
    finally:
        resume.set()
        release.set()
        racing_requests.shutdown(wait=True)
        runtime.close()


def test_operation_runtime_rejects_reused_key_and_busy_lock(tmp_path: Path) -> None:
    """Mismatched replay and independent lock contention fail before dispatch."""
    paths = default_application_paths(tmp_path)
    runtime_context = runtime_context_for(paths.config_file, paths.database_file)
    runtime = OperationRuntime(runtime_context)

    with (
        runtime_context.exclusive_operation_lock.hold(ExclusiveOperationRequest(operation_name="test_owner")),
        pytest.raises(ExclusiveOperationBusyError),
    ):
        _ = runtime.accept(
            kind=OperationKind.CHECK,
            idempotency_key=IDEMPOTENCY_KEY,
            canonical_request={"library_id": None},
            work=lambda _operation_id: CheckCompletedResult((CHECK_RUN_ID,), 0),
        )

    release = Event()
    started = Event()

    def work(_operation_id: OperationId) -> CheckCompletedResult:
        started.set()
        _ = release.wait(OPERATION_RECONCILE_INTERVAL_SECONDS)
        return CheckCompletedResult((CHECK_RUN_ID,), 0)

    _ = runtime.accept(
        kind=OperationKind.CHECK,
        idempotency_key=IDEMPOTENCY_KEY,
        canonical_request={"library_id": None},
        work=work,
    )
    assert started.wait(OPERATION_RECONCILE_INTERVAL_SECONDS)
    with pytest.raises(IdempotencyKeyReusedError):
        _ = runtime.accept(
            kind=OperationKind.CHECK,
            idempotency_key=IDEMPOTENCY_KEY,
            canonical_request={"library_id": "changed"},
            work=work,
        )
    release.set()
    runtime.close()


def test_operation_runtime_interrupts_orphaned_reservation(tmp_path: Path) -> None:
    """A free lock plus queued durable evidence becomes interrupted and is never dispatched."""
    paths = default_application_paths(tmp_path)
    runtime_context = runtime_context_for(paths.config_file, paths.database_file)
    ports = OperationPorts(
        uow=build_uow(runtime_context),
        clock=SystemClock(),
        id_generator=Uuid7IdGenerator(),
    )
    reserved = ReserveOperationUseCase(ports).execute(
        ReserveOperationRequest(
            kind=OperationKind.CHECK,
            idempotency_key=IDEMPOTENCY_KEY,
            request_fingerprint="orphaned",
        )
    )
    runtime = OperationRuntime(runtime_context)

    assert runtime.reconcile_if_idle() is True

    operation = runtime.get(reserved.lookup.operation_id)
    assert operation.status is OperationStatus.INTERRUPTED
    assert operation.error is not None
    assert operation.error.code.value == "operation_interrupted"
    runtime.close()


def test_operation_runtime_contains_startup_reconciliation_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A transient reconciliation failure is logged without preventing lifecycle startup."""
    paths = default_application_paths(tmp_path)
    runtime_context = runtime_context_for(paths.config_file, paths.database_file)
    runtime = OperationRuntime(runtime_context)

    def fail_reconciliation(_runtime: OperationRuntime) -> bool:
        raise OSError(RECONCILIATION_FAILURE)

    monkeypatch.setattr(OperationRuntime, "reconcile_if_idle", fail_reconciliation)
    with caplog.at_level(logging.ERROR):
        runtime.start()
        runtime.close()

    assert "Durable Operation reconciliation pass failed" in caplog.text


def _pause_initial_replay_classification(monkeypatch: pytest.MonkeyPatch) -> tuple[Event, Event]:
    """Pause one absent-key classification so another request can reserve first."""
    classified = Event()
    resume = Event()
    original_execute = ClassifyOperationReplayUseCase.execute

    def execute_and_pause(
        usecase: ClassifyOperationReplayUseCase,
        request: ReserveOperationRequest,
    ) -> OperationLookup | None:
        replay = original_execute(usecase, request)
        if not classified.is_set():
            classified.set()
            assert resume.wait(OPERATION_RECONCILE_INTERVAL_SECONDS)
        return replay

    monkeypatch.setattr(ClassifyOperationReplayUseCase, "execute", execute_and_pause)
    return classified, resume
