"""
Summary: Composes durable Operation reservation, locking, workers, and reconciliation.
Why: Runs feature work asynchronously without crossing feature or adapter boundaries.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass, field
from hashlib import new as new_hash
from threading import Event, Lock, Thread
from typing import TYPE_CHECKING

from omym2.config import (
    OPERATION_RECONCILE_INTERVAL_SECONDS,
    OPERATION_REQUEST_FINGERPRINT_ALGORITHM,
    OPERATION_WORKER_COUNT,
)
from omym2.domain.models.operation import (
    Operation,
    OperationError,
    OperationErrorCode,
    OperationKind,
    OperationStatus,
)
from omym2.domain.models.plan import PlanStatus
from omym2.features.apply.dto import ClaimApplyRequest
from omym2.features.apply.usecases.apply_plan import PLAN_NOT_READY_MESSAGE, PlanCannotBeAppliedError
from omym2.features.apply.usecases.claim_apply import ClaimApplyUseCase
from omym2.features.common_ports import (
    ExclusiveOperationBusyError,
    ExclusiveOperationRequest,
    MetadataReadError,
    SystemClock,
    Uuid7IdGenerator,
)
from omym2.features.operations.dto import FinishOperationRequest, ReserveOperationRequest, ReserveOperationResult
from omym2.features.operations.ports import OperationPorts
from omym2.features.operations.usecases.get_operation import GetOperationUseCase
from omym2.features.operations.usecases.reconcile_operations import (
    CleanupOperationsUseCase,
    ReconcileOperationsUseCase,
)
from omym2.features.operations.usecases.reserve_operation import (
    ClassifyOperationReplayUseCase,
    ReserveOperationUseCase,
)
from omym2.features.operations.usecases.update_operation import (
    FinishOperationUseCase,
    MarkOperationRunningUseCase,
)
from omym2.platform.feature_composition import build_apply_plan_ports, build_uow

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from uuid import UUID

    from omym2.domain.models.operation import OperationResult
    from omym2.platform.runtime_context import RuntimeContext
    from omym2.shared.ids import LibraryId, OperationId, PlanId, RunId

LOGGER = logging.getLogger(__name__)
DISPATCH_FAILURE_MESSAGE = "The accepted Operation could not start its worker."
METADATA_FAILURE_MESSAGE = "Metadata could not be read while executing this Operation."
OPERATION_FAILURE_MESSAGE = "The Operation failed before producing a confirmed result."
WORKER_THREAD_NAME_PREFIX = "omym2-operation"
SUPERVISOR_THREAD_NAME = "omym2-operation-reconcile"

type OperationWork = Callable[[OperationId], OperationResult]
type OperationPreflight = Callable[[], None]
type ExclusiveWork[T] = Callable[[], T]
type InlineOperationWork[T] = Callable[[OperationId], T]
type InlineApplyWork[T] = Callable[[OperationId, RunId], T]


@dataclass(slots=True)
class OperationRuntime:
    """One-slot durable worker and bounded reconciliation supervisor."""

    runtime: RuntimeContext
    _executor: ThreadPoolExecutor = field(init=False, repr=False)
    _stop_event: Event = field(default_factory=Event, init=False, repr=False)
    _supervisor: Thread | None = field(default=None, init=False, repr=False)
    _lifecycle_guard: Lock = field(default_factory=Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        """Create the one-slot executor without starting threads or I/O."""
        self._executor = ThreadPoolExecutor(
            max_workers=OPERATION_WORKER_COUNT,
            thread_name_prefix=WORKER_THREAD_NAME_PREFIX,
        )

    def start(self) -> None:
        """Run startup reconciliation, then start the bounded supervisor."""
        with self._lifecycle_guard:
            if self._supervisor is not None:
                return
            self._try_reconcile()
            supervisor = Thread(target=self._supervise, name=SUPERVISOR_THREAD_NAME, daemon=True)
            self._supervisor = supervisor
            supervisor.start()

    def close(self) -> None:
        """Stop reconciliation and wait for any accepted worker to release its lock."""
        with self._lifecycle_guard:
            supervisor = self._supervisor
            self._supervisor = None
            self._stop_event.set()
        if supervisor is not None:
            supervisor.join(timeout=OPERATION_RECONCILE_INTERVAL_SECONDS)
        self._executor.shutdown(wait=True, cancel_futures=False)

    def get(self, operation_id: OperationId) -> Operation:
        """Return one read-only polling snapshot without reconciliation."""
        return GetOperationUseCase(self._ports()).execute(operation_id)

    def active_operation_id(self) -> OperationId | None:
        """Return the active durable identity for conflict remediation."""
        try:
            with build_uow(self.runtime) as uow:
                operation = uow.operations.find_active()
        except Exception:  # Conflict remediation must not replace the original typed 409.
            LOGGER.exception("Active Operation lookup failed during conflict remediation")
            return None
        return None if operation is None else operation.operation_id

    def active_operation_id_for_plan(self, plan_id: PlanId) -> OperationId | None:
        """Return the queued/running Operation associated with one Plan, if any."""
        with build_uow(self.runtime) as uow:
            operation = uow.operations.find_active()
        if operation is None or operation.plan_id != plan_id:
            return None
        return operation.operation_id

    def active_operation_id_for_run(self, run_id: RunId) -> OperationId | None:
        """Return the queued/running Operation associated with one Run, if any."""
        with build_uow(self.runtime) as uow:
            operation = uow.operations.find_active()
        if operation is None or operation.run_id != run_id:
            return None
        return operation.operation_id

    def accept(  # noqa: PLR0913  # Durable acceptance fields are one explicit transaction contract.
        self,
        *,
        kind: OperationKind,
        idempotency_key: UUID,
        canonical_request: Mapping[str, object],
        work: OperationWork,
        library_id: LibraryId | None = None,
        plan_id: PlanId | None = None,
        run_id: RunId | None = None,
        preflight: OperationPreflight | None = None,
    ) -> ReserveOperationResult:
        """Replay or durably accept one request before handing its retained lock to the worker."""
        request = ReserveOperationRequest(
            kind=kind,
            idempotency_key=idempotency_key,
            request_fingerprint=operation_request_fingerprint(canonical_request),
            library_id=library_id,
            plan_id=plan_id,
            run_id=run_id,
        )
        replay = ClassifyOperationReplayUseCase(self._ports()).execute(request)
        if replay is not None:
            return ReserveOperationResult(lookup=replay, is_new=False)

        transfer = ExitStack()
        try:
            try:
                _ = transfer.enter_context(
                    self.runtime.exclusive_operation_lock.hold(ExclusiveOperationRequest(operation_name=kind.value))
                )
            except ExclusiveOperationBusyError:
                replay = ClassifyOperationReplayUseCase(self._ports()).execute(request)
                if replay is not None:
                    return ReserveOperationResult(lookup=replay, is_new=False)
                raise
            self._reconcile_and_cleanup()
            if preflight is not None:
                preflight()
            reserved = ReserveOperationUseCase(self._ports()).execute(request)
            if not reserved.is_new:
                return reserved
            if not isinstance(reserved.lookup, Operation):
                raise TypeError
            worker_stack = transfer.pop_all()
            try:
                _ = self._executor.submit(self._run, reserved.lookup.operation_id, work, worker_stack)
            except RuntimeError:
                with worker_stack:
                    self._interrupt_dispatch_failure()
                raise
            return reserved
        finally:
            transfer.close()

    def accept_apply(
        self,
        *,
        plan_id: PlanId,
        idempotency_key: UUID,
        canonical_request: Mapping[str, object],
        work: OperationWork,
    ) -> ReserveOperationResult:
        """Atomically claim a ready Plan before dispatching its retained-lock worker."""
        fingerprint = operation_request_fingerprint(canonical_request)
        replay_request = ReserveOperationRequest(
            kind=OperationKind.APPLY_PLAN,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            plan_id=plan_id,
        )
        replay = ClassifyOperationReplayUseCase(self._ports()).execute(replay_request)
        if replay is not None:
            return ReserveOperationResult(lookup=replay, is_new=False)

        transfer = ExitStack()
        try:
            try:
                _ = transfer.enter_context(
                    self.runtime.exclusive_operation_lock.hold(
                        ExclusiveOperationRequest(operation_name=OperationKind.APPLY_PLAN.value)
                    )
                )
            except ExclusiveOperationBusyError:
                replay = ClassifyOperationReplayUseCase(self._ports()).execute(replay_request)
                if replay is not None:
                    return ReserveOperationResult(lookup=replay, is_new=False)
                if not self._plan_is_ready(plan_id):
                    raise PlanCannotBeAppliedError(PLAN_NOT_READY_MESSAGE) from None
                raise
            self._reconcile_and_cleanup()
            claim = ClaimApplyUseCase(build_apply_plan_ports(self.runtime)).execute(
                ClaimApplyRequest(
                    plan_id=plan_id,
                    idempotency_key=idempotency_key,
                    request_fingerprint=fingerprint,
                )
            )
            reserved = ReserveOperationResult(lookup=claim.lookup, is_new=claim.is_new)
            if not reserved.is_new:
                return reserved
            if not isinstance(reserved.lookup, Operation):
                raise TypeError
            worker_stack = transfer.pop_all()
            try:
                _ = self._executor.submit(self._run, reserved.lookup.operation_id, work, worker_stack)
            except RuntimeError:
                with worker_stack:
                    self._interrupt_dispatch_failure()
                raise
            return reserved
        finally:
            transfer.close()

    def _plan_is_ready(self, plan_id: PlanId) -> bool:
        """Read the target Plan after lock contention to distinguish a committed claim."""
        with build_uow(self.runtime) as uow:
            plan = uow.plans.get(plan_id)
        return plan is None or plan.status is PlanStatus.READY

    def reconcile_if_idle(self) -> bool:
        """Attempt one nonblocking reconciliation pass without disturbing a live owner."""
        try:
            with self.runtime.exclusive_operation_lock.hold(
                ExclusiveOperationRequest(operation_name="reconcile_operations")
            ):
                self._reconcile_and_cleanup()
        except ExclusiveOperationBusyError:
            return False
        return True

    def execute_exclusive[T](self, operation_name: str, work: ExclusiveWork[T]) -> T:
        """Run one synchronous mutation after reconciliation under the shared lock."""
        with self.runtime.exclusive_operation_lock.hold(ExclusiveOperationRequest(operation_name=operation_name)):
            self._reconcile_and_cleanup()
            return work()

    def run_inline[T](  # noqa: PLR0913  # Inline durable identity mirrors background acceptance.
        self,
        *,
        kind: OperationKind,
        canonical_request: Mapping[str, object],
        work: InlineOperationWork[T],
        library_id: LibraryId | None = None,
        plan_id: PlanId | None = None,
        run_id: RunId | None = None,
    ) -> T:
        """Persist the same lifecycle for a CLI flow while executing under the shared lock."""
        from omym2.shared.ids import new_uuid7  # noqa: PLC0415  # One fresh key per CLI invocation.

        with self.runtime.exclusive_operation_lock.hold(ExclusiveOperationRequest(operation_name=kind.value)):
            self._reconcile_and_cleanup()
            reserved = ReserveOperationUseCase(self._ports()).execute(
                ReserveOperationRequest(
                    kind=kind,
                    idempotency_key=new_uuid7(),
                    request_fingerprint=operation_request_fingerprint(canonical_request),
                    library_id=library_id,
                    plan_id=plan_id,
                    run_id=run_id,
                )
            )
            if not isinstance(reserved.lookup, Operation):
                raise TypeError
            operation_id = reserved.lookup.operation_id
            _ = MarkOperationRunningUseCase(self._ports()).execute(operation_id)
            try:
                result = work(operation_id)
            except MetadataReadError:
                self._fail_metadata_execution(operation_id)
                raise
            except Exception:
                self._finish_failure(operation_id, OperationErrorCode.OPERATION_FAILED, OPERATION_FAILURE_MESSAGE)
                raise
            current = self.get(operation_id)
            if current.status is not OperationStatus.SUCCEEDED:
                self._finish_failure(operation_id, OperationErrorCode.OPERATION_FAILED, OPERATION_FAILURE_MESSAGE)
                raise RuntimeError(OPERATION_FAILURE_MESSAGE)
            return result

    def run_inline_apply[T](
        self,
        *,
        plan_id: PlanId,
        canonical_request: Mapping[str, object],
        work: InlineApplyWork[T],
    ) -> T:
        """Atomically claim and execute one CLI Apply under the shared lock."""
        from omym2.shared.ids import new_uuid7  # noqa: PLC0415  # One fresh key per CLI invocation.

        with self.runtime.exclusive_operation_lock.hold(
            ExclusiveOperationRequest(operation_name=OperationKind.APPLY_PLAN.value)
        ):
            self._reconcile_and_cleanup()
            claim = ClaimApplyUseCase(build_apply_plan_ports(self.runtime)).execute(
                ClaimApplyRequest(
                    plan_id=plan_id,
                    idempotency_key=new_uuid7(),
                    request_fingerprint=operation_request_fingerprint(canonical_request),
                )
            )
            if not claim.is_new or not isinstance(claim.lookup, Operation) or claim.lookup.run_id is None:
                raise TypeError
            operation_id = claim.lookup.operation_id
            run_id = claim.lookup.run_id
            try:
                _ = MarkOperationRunningUseCase(self._ports()).execute(operation_id)
                result = work(operation_id, run_id)
            except Exception:
                self._fail_apply_execution(operation_id)
                raise
            current = self.get(operation_id)
            if not current.is_terminal:
                self._fail_apply_execution(operation_id)
                raise RuntimeError(OPERATION_FAILURE_MESSAGE)
            return result

    def _ports(self) -> OperationPorts:
        return OperationPorts(
            uow=build_uow(self.runtime),
            clock=SystemClock(),
            id_generator=Uuid7IdGenerator(),
        )

    def _run(self, operation_id: OperationId, work: OperationWork, worker_stack: ExitStack) -> None:
        with worker_stack:
            try:
                _ = MarkOperationRunningUseCase(self._ports()).execute(operation_id)
                result = work(operation_id)
                current = self.get(operation_id)
                if current.status is OperationStatus.RUNNING:
                    if current.kind is OperationKind.APPLY_PLAN:
                        LOGGER.error(
                            "Apply worker returned before managed state became terminal operation_id=%s",
                            operation_id,
                        )
                        self._fail_apply_execution(operation_id)
                        return
                    _ = FinishOperationUseCase(self._ports()).execute(
                        FinishOperationRequest(operation_id=operation_id, result=result)
                    )
            except MetadataReadError:
                self._fail_metadata_execution(operation_id)
            except Exception:
                LOGGER.exception("Durable Operation worker failed operation_id=%s", operation_id)
                self._fail_operation_execution(operation_id)

    def _fail_operation_execution(self, operation_id: OperationId) -> None:
        try:
            current = self.get(operation_id)
        except Exception:
            LOGGER.exception("Durable Operation lookup failed after worker error operation_id=%s", operation_id)
            return
        if current.kind is OperationKind.APPLY_PLAN and current.status in {
            OperationStatus.QUEUED,
            OperationStatus.RUNNING,
        }:
            self._fail_apply_execution(operation_id)
            return
        self._finish_failure(operation_id, OperationErrorCode.OPERATION_FAILED, OPERATION_FAILURE_MESSAGE)

    def _fail_metadata_execution(self, operation_id: OperationId) -> None:
        """Reconcile Apply managed state or persist a metadata-specific generic failure."""
        try:
            current = self.get(operation_id)
        except Exception:
            LOGGER.exception("Durable Operation lookup failed after metadata error operation_id=%s", operation_id)
            return
        if current.kind is OperationKind.APPLY_PLAN and current.status is OperationStatus.RUNNING:
            self._fail_apply_execution(operation_id)
            return
        self._finish_failure(operation_id, OperationErrorCode.METADATA_READ_FAILED, METADATA_FAILURE_MESSAGE)

    def _fail_apply_execution(self, operation_id: OperationId) -> None:
        try:
            _ = ReconcileOperationsUseCase(self._ports()).execute(failed_apply_operation_id=operation_id)
        except Exception:
            LOGGER.exception("Apply terminal reconciliation failed operation_id=%s", operation_id)

    def _finish_failure(self, operation_id: OperationId, code: OperationErrorCode, message: str) -> None:
        try:
            current = self.get(operation_id)
            if current.status is not OperationStatus.RUNNING:
                return
            _ = FinishOperationUseCase(self._ports()).execute(
                FinishOperationRequest(
                    operation_id=operation_id,
                    error=OperationError(code=code, message=message, retryable=False),
                )
            )
        except Exception:
            LOGGER.exception("Durable Operation terminal write failed operation_id=%s", operation_id)

    def _interrupt_dispatch_failure(self) -> None:
        LOGGER.error(DISPATCH_FAILURE_MESSAGE)
        _ = ReconcileOperationsUseCase(self._ports()).execute()

    def _reconcile_and_cleanup(self) -> None:
        _ = ReconcileOperationsUseCase(self._ports()).execute()
        _ = CleanupOperationsUseCase(self._ports()).execute()

    def _supervise(self) -> None:
        while not self._stop_event.wait(OPERATION_RECONCILE_INTERVAL_SECONDS):
            self._try_reconcile()

    def _try_reconcile(self) -> None:
        try:
            _ = self.reconcile_if_idle()
        except Exception:
            LOGGER.exception("Durable Operation reconciliation pass failed")


def operation_request_fingerprint(canonical_request: Mapping[str, object]) -> str:
    """Return a stable digest without retaining the raw request body."""
    canonical_json = json.dumps(
        canonical_request,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )
    digest = new_hash(OPERATION_REQUEST_FINGERPRINT_ALGORITHM)
    digest.update(canonical_json.encode("utf-8"))
    return digest.hexdigest()
