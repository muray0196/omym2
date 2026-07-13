"""
Summary: Tests Apply-specific worker failure routing in durable Operation composition.
Why: Prevents worker and start failures from leaving atomically claimed state active.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from threading import Event
from typing import TYPE_CHECKING
from uuid import UUID

import pytest

from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.fs.exclusive_operation_lock import FilesystemExclusiveOperationLock
from omym2.config import OPERATION_RECONCILE_INTERVAL_SECONDS
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.operation import (
    CheckCompletedResult,
    OperationErrorCode,
    OperationStatus,
    RunCompletedResult,
)
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction, PlanActionReason
from omym2.domain.models.run import RunStatus
from omym2.features.common_ports import IdempotencyKeyReusedError, MetadataReadError
from omym2.features.operations.usecases.reconcile_operations import ReconcileOperationsUseCase
from omym2.features.operations.usecases.reserve_operation import ClassifyOperationReplayUseCase
from omym2.features.operations.usecases.update_operation import MarkOperationRunningUseCase
from omym2.platform.feature_composition import build_uow
from omym2.platform.operation_composition import OperationRuntime
from omym2.platform.runtime_context import runtime_context_for
from omym2.shared.ids import ActionId, LibraryId, OperationId, PlanId

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from omym2.domain.models.operation import OperationLookup
    from omym2.features.common_ports import ExclusiveOperationLease, ExclusiveOperationRequest
    from omym2.features.operations.dto import ReserveOperationRequest
    from omym2.platform.runtime_context import RuntimeContext
    from omym2.shared.ids import RunId

NOW = datetime(2026, 7, 13, tzinfo=UTC)
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456a0"))
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456a1"))
ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456a2"))
IDEMPOTENCY_KEY = UUID("018f6a4f-3c2d-7b8a-9abc-def0123456a3")
METADATA_FAILURE = "fixture metadata failure"


def test_apply_metadata_failure_reconciles_claimed_state_before_worker_releases_lock(tmp_path: Path) -> None:
    """An Apply-specific metadata error terminalizes Operation, Plan, Run, and unconfirmed action."""
    paths = default_application_paths(tmp_path)
    runtime_context = runtime_context_for(paths.config_file, paths.database_file)
    _seed_ready_plan(runtime_context, tmp_path)
    runtime = OperationRuntime(runtime_context)

    def fail_metadata(_operation_id: OperationId) -> CheckCompletedResult:
        raise MetadataReadError(METADATA_FAILURE)

    accepted = runtime.accept_apply(
        plan_id=PLAN_ID,
        idempotency_key=IDEMPOTENCY_KEY,
        canonical_request={"plan_id": PLAN_ID},
        work=fail_metadata,
    )
    runtime.close()

    operation = runtime.get(accepted.lookup.operation_id)
    assert operation.status is OperationStatus.FAILED
    assert operation.error is not None
    assert operation.error.code is OperationErrorCode.OPERATION_FAILED
    assert operation.run_id is not None
    with build_uow(runtime_context) as uow:
        plan = uow.plans.get(PLAN_ID)
        run = uow.runs.get(operation.run_id)
        action = uow.plan_actions.get(ACTION_ID)
    assert plan is not None
    assert plan.status is PlanStatus.FAILED
    assert run is not None
    assert run.status is RunStatus.FAILED
    assert action is not None
    assert action.status is ActionStatus.FAILED
    assert action.reason is PlanActionReason.OPERATION_INTERRUPTED


def test_apply_start_failure_interrupts_claim_and_reconciles_before_worker_releases_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failure to mark the queued Apply running still repairs every atomically claimed association."""
    paths = default_application_paths(tmp_path)
    runtime_context = runtime_context_for(paths.config_file, paths.database_file)
    _seed_ready_plan(runtime_context, tmp_path)
    runtime = OperationRuntime(runtime_context)

    def fail_start(_usecase: MarkOperationRunningUseCase, _operation_id: OperationId) -> None:
        raise RuntimeError

    monkeypatch.setattr(MarkOperationRunningUseCase, "execute", fail_start)
    accepted = runtime.accept_apply(
        plan_id=PLAN_ID,
        idempotency_key=IDEMPOTENCY_KEY,
        canonical_request={"plan_id": PLAN_ID},
        work=lambda _operation_id: CheckCompletedResult((), 0),
    )
    runtime.close()

    operation = runtime.get(accepted.lookup.operation_id)
    assert operation.status is OperationStatus.INTERRUPTED
    assert operation.run_id is not None
    with build_uow(runtime_context) as uow:
        plan = uow.plans.get(PLAN_ID)
        run = uow.runs.get(operation.run_id)
        action = uow.plan_actions.get(ACTION_ID)
    assert plan is not None
    assert plan.status is PlanStatus.FAILED
    assert run is not None
    assert run.status is RunStatus.FAILED
    assert action is not None
    assert action.status is ActionStatus.FAILED
    assert action.reason is PlanActionReason.OPERATION_INTERRUPTED


def test_inline_apply_start_failure_reconciles_once_before_lock_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A CLI start failure repairs its claim under lock and preserves the original exception."""
    paths = default_application_paths(tmp_path)
    runtime_context = runtime_context_for(paths.config_file, paths.database_file)
    _seed_ready_plan(runtime_context, tmp_path)
    runtime = OperationRuntime(runtime_context)
    start_error = RuntimeError("fixture inline Apply start failure")
    claimed_operation_ids: list[OperationId] = []
    repaired_operation_ids: list[OperationId] = []
    work_calls = 0
    observed_before_release: list[tuple[OperationStatus, PlanStatus | None, RunStatus | None, ActionStatus | None]] = []
    original_hold = FilesystemExclusiveOperationLock.hold
    original_reconcile = ReconcileOperationsUseCase.execute

    @contextmanager
    def observe_before_release(
        lock: FilesystemExclusiveOperationLock,
        request: ExclusiveOperationRequest,
    ) -> Generator[ExclusiveOperationLease]:
        with original_hold(lock, request) as lease:
            try:
                yield lease
            finally:
                if claimed_operation_ids:
                    operation = runtime.get(claimed_operation_ids[0])
                    with build_uow(runtime_context) as uow:
                        plan = uow.plans.get(PLAN_ID)
                        run = None if operation.run_id is None else uow.runs.get(operation.run_id)
                        action = uow.plan_actions.get(ACTION_ID)
                    observed_before_release.append(
                        (
                            operation.status,
                            None if plan is None else plan.status,
                            None if run is None else run.status,
                            None if action is None else action.status,
                        )
                    )

    def fail_start(_usecase: MarkOperationRunningUseCase, operation_id: OperationId) -> None:
        claimed_operation_ids.append(operation_id)
        raise start_error

    def count_apply_repair(
        usecase: ReconcileOperationsUseCase,
        failed_apply_operation_id: OperationId | None = None,
    ) -> tuple[OperationId, ...]:
        if failed_apply_operation_id is not None:
            repaired_operation_ids.append(failed_apply_operation_id)
        return original_reconcile(usecase, failed_apply_operation_id)

    def should_not_run(_operation_id: OperationId, _run_id: RunId) -> None:
        nonlocal work_calls
        work_calls += 1

    monkeypatch.setattr(FilesystemExclusiveOperationLock, "hold", observe_before_release)
    monkeypatch.setattr(MarkOperationRunningUseCase, "execute", fail_start)
    monkeypatch.setattr(ReconcileOperationsUseCase, "execute", count_apply_repair)
    try:
        with pytest.raises(RuntimeError) as exc_info:
            runtime.run_inline_apply(
                plan_id=PLAN_ID,
                canonical_request={"plan_id": PLAN_ID},
                work=should_not_run,
            )
    finally:
        runtime.close()

    assert exc_info.value is start_error
    assert work_calls == 0
    assert repaired_operation_ids == claimed_operation_ids
    assert observed_before_release == [
        (OperationStatus.INTERRUPTED, PlanStatus.FAILED, RunStatus.FAILED, ActionStatus.FAILED)
    ]


def test_apply_reclassifies_exact_replay_before_plan_readiness_after_lock_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pre-claim exact request replays the winner instead of rejecting its applying Plan."""
    paths = default_application_paths(tmp_path)
    runtime_context = runtime_context_for(paths.config_file, paths.database_file)
    _seed_ready_plan(runtime_context, tmp_path)
    runtime = OperationRuntime(runtime_context)
    classified, resume = _pause_initial_replay_classification(monkeypatch)
    started = Event()
    release = Event()
    work_count = 0

    def work(operation_id: OperationId) -> RunCompletedResult:
        nonlocal work_count
        work_count += 1
        started.set()
        _ = release.wait(OPERATION_RECONCILE_INTERVAL_SECONDS)
        run_id = runtime.get(operation_id).run_id
        assert run_id is not None
        return RunCompletedResult(run_id)

    racing_requests = ThreadPoolExecutor(max_workers=1)
    try:
        replay_future = racing_requests.submit(
            runtime.accept_apply,
            plan_id=PLAN_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            canonical_request={"plan_id": PLAN_ID},
            work=work,
        )
        assert classified.wait(OPERATION_RECONCILE_INTERVAL_SECONDS)
        accepted = runtime.accept_apply(
            plan_id=PLAN_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            canonical_request={"plan_id": PLAN_ID},
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


def test_apply_reclassifies_mismatched_key_before_plan_readiness_after_lock_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A raced Apply key mismatch remains a reuse conflict after the Plan is claimed."""
    paths = default_application_paths(tmp_path)
    runtime_context = runtime_context_for(paths.config_file, paths.database_file)
    _seed_ready_plan(runtime_context, tmp_path)
    runtime = OperationRuntime(runtime_context)
    classified, resume = _pause_initial_replay_classification(monkeypatch)
    release = Event()

    def work(operation_id: OperationId) -> RunCompletedResult:
        _ = release.wait(OPERATION_RECONCILE_INTERVAL_SECONDS)
        run_id = runtime.get(operation_id).run_id
        assert run_id is not None
        return RunCompletedResult(run_id)

    racing_requests = ThreadPoolExecutor(max_workers=1)
    try:
        mismatch_future = racing_requests.submit(
            runtime.accept_apply,
            plan_id=PLAN_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            canonical_request={"plan_id": PLAN_ID, "mode": "changed"},
            work=work,
        )
        assert classified.wait(OPERATION_RECONCILE_INTERVAL_SECONDS)
        _ = runtime.accept_apply(
            plan_id=PLAN_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            canonical_request={"plan_id": PLAN_ID},
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


def test_apply_worker_result_cannot_finish_nonterminal_managed_state(tmp_path: Path) -> None:
    """A premature Apply result routes through reconciliation instead of generic success."""
    paths = default_application_paths(tmp_path)
    runtime_context = runtime_context_for(paths.config_file, paths.database_file)
    _seed_ready_plan(runtime_context, tmp_path)
    runtime = OperationRuntime(runtime_context)

    def return_result_without_applying(operation_id: OperationId) -> RunCompletedResult:
        run_id = runtime.get(operation_id).run_id
        assert run_id is not None
        return RunCompletedResult(run_id)

    accepted = runtime.accept_apply(
        plan_id=PLAN_ID,
        idempotency_key=IDEMPOTENCY_KEY,
        canonical_request={"plan_id": PLAN_ID},
        work=return_result_without_applying,
    )
    runtime.close()

    operation = runtime.get(accepted.lookup.operation_id)
    assert operation.status is OperationStatus.FAILED
    assert operation.result is None
    assert operation.error is not None
    assert operation.error.code is OperationErrorCode.OPERATION_FAILED
    assert operation.run_id is not None
    with build_uow(runtime_context) as uow:
        plan = uow.plans.get(PLAN_ID)
        run = uow.runs.get(operation.run_id)
        action = uow.plan_actions.get(ACTION_ID)
    assert plan is not None
    assert plan.status is PlanStatus.FAILED
    assert run is not None
    assert run.status is RunStatus.FAILED
    assert action is not None
    assert action.status is ActionStatus.FAILED
    assert action.reason is PlanActionReason.OPERATION_INTERRUPTED


def _seed_ready_plan(runtime_context: RuntimeContext, tmp_path: Path) -> None:
    """Persist one eligible action so reconciliation has unconfirmed Apply work to classify."""
    library_root = tmp_path / "library"
    library_root.mkdir()
    with build_uow(runtime_context) as uow:
        uow.libraries.save(
            Library(
                library_id=LIBRARY_ID,
                root_path=str(library_root),
                path_policy_hash="path-policy",
                registered_at=NOW,
                status=LibraryStatus.REGISTERED,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        uow.plans.save(
            Plan(
                plan_id=PLAN_ID,
                library_id=LIBRARY_ID,
                plan_type=PlanType.ORGANIZE,
                status=PlanStatus.READY,
                created_at=NOW,
                config_hash="config-hash",
                library_root_at_plan=str(library_root),
            )
        )
        uow.plan_actions.save(
            PlanAction(
                action_id=ACTION_ID,
                plan_id=PLAN_ID,
                library_id=LIBRARY_ID,
                track_id=None,
                action_type=ActionType.MOVE,
                source_path="Artist/source.flac",
                target_path="Artist/target.flac",
                content_hash_at_plan="content-hash",
                metadata_hash_at_plan="metadata-hash",
                status=ActionStatus.PLANNED,
                reason=None,
                sort_order=1,
            )
        )
        uow.commit()


def _pause_initial_replay_classification(monkeypatch: pytest.MonkeyPatch) -> tuple[Event, Event]:
    """Pause one absent-key classification so another Apply request can claim first."""
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
