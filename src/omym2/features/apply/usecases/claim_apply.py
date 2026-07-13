"""
Summary: Atomically claims one reviewed Plan for durable Apply execution.
Why: Prevents duplicate Runs or Operations before any Library mutation starts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.domain.models.operation import Operation, OperationKind
from omym2.domain.models.plan import PlanStatus
from omym2.domain.models.run import Run, RunStatus
from omym2.features.apply.dto import ClaimApplyResult
from omym2.features.apply.usecases.apply_plan import (
    LIBRARY_NOT_FOUND_MESSAGE,
    LIBRARY_ROOT_CHANGED_SUMMARY,
    PLAN_NOT_FOUND_MESSAGE,
    PLAN_NOT_READY_MESSAGE,
    ApplyPlanError,
    PlanCannotBeAppliedError,
    PlanNotFoundError,
)
from omym2.features.common_ports import IdempotencyKeyReusedError, OperationInProgressError

if TYPE_CHECKING:
    from omym2.domain.models.operation import OperationLookup
    from omym2.features.apply.dto import ClaimApplyRequest
    from omym2.features.apply.ports import ApplyPlanPorts


@dataclass(frozen=True, slots=True)
class ClaimApplyUseCase:
    """Claim a ready Plan, create its Run, and reserve its Apply Operation."""

    ports: ApplyPlanPorts

    def execute(self, request: ClaimApplyRequest) -> ClaimApplyResult:
        """Commit the complete Apply acceptance boundary in one transaction."""
        with self.ports.uow as uow:
            retained = uow.operations.find_by_idempotency_key(request.idempotency_key)
            if retained is not None:
                _require_same_apply_request(retained, request.request_fingerprint)
                return ClaimApplyResult(lookup=retained, is_new=False)

            active = uow.operations.find_active()
            if active is not None:
                raise OperationInProgressError(active)

            plan = uow.plans.get(request.plan_id)
            if plan is None:
                raise PlanNotFoundError(PLAN_NOT_FOUND_MESSAGE)
            if plan.status is not PlanStatus.READY:
                raise PlanCannotBeAppliedError(PLAN_NOT_READY_MESSAGE)

            library = uow.libraries.get(plan.library_id)
            if library is None:
                raise ApplyPlanError(LIBRARY_NOT_FOUND_MESSAGE)
            if library.root_path != plan.library_root_at_plan:
                uow.plans.save(plan.mark_expired())
                uow.commit()
                raise LibraryRootChangedError(LIBRARY_ROOT_CHANGED_SUMMARY)

            requested_at = self.ports.clock.now()
            run = Run(
                run_id=self.ports.id_generator.new_run_id(),
                plan_id=plan.plan_id,
                library_id=plan.library_id,
                status=RunStatus.RUNNING,
                started_at=requested_at,
            )
            operation = Operation.queued(
                operation_id=self.ports.id_generator.new_operation_id(),
                kind=OperationKind.APPLY_PLAN,
                idempotency_key=request.idempotency_key,
                request_fingerprint=request.request_fingerprint,
                requested_at=requested_at,
                library_id=plan.library_id,
                plan_id=plan.plan_id,
                run_id=run.run_id,
            )
            if not uow.claim_apply(plan.plan_id, run, operation):
                raise PlanCannotBeAppliedError(PLAN_NOT_READY_MESSAGE)
            uow.commit()
            return ClaimApplyResult(lookup=operation, is_new=True)


class LibraryRootChangedError(ApplyPlanError):
    """Raised after a ready Plan is expired because its Library root changed."""


def _require_same_apply_request(retained: OperationLookup, request_fingerprint: str) -> None:
    if retained.kind is not OperationKind.APPLY_PLAN or retained.request_fingerprint != request_fingerprint:
        raise IdempotencyKeyReusedError
