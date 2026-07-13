"""
Summary: Interrupts orphaned durable Operations and cleans retained payloads.
Why: Makes process loss visible without automatically resuming unconfirmed work.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from omym2.config import OPERATION_RESULT_RETENTION_HOURS, OPERATION_TOMBSTONE_RETENTION_DAYS
from omym2.domain.models.file_event import FileEventStatus
from omym2.domain.models.operation import Operation, OperationError, OperationErrorCode, OperationKind, OperationStatus
from omym2.domain.models.plan import PlanStatus
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanActionReason
from omym2.domain.models.run import RunStatus

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from omym2.domain.models.file_event import FileEvent
    from omym2.domain.models.plan import Plan
    from omym2.domain.models.plan_action import PlanAction
    from omym2.domain.models.run import Run
    from omym2.features.common_ports import UnitOfWork
    from omym2.features.operations.ports import OperationPorts
    from omym2.shared.ids import OperationId

INTERRUPTED_MESSAGE = "The process stopped before this Operation reached a confirmed result."
APPLY_INTERRUPTED_SUMMARY = "Apply was interrupted before every action outcome was confirmed."
APPLY_FAILED_MESSAGE = "Apply stopped before producing a confirmed Run result."


@dataclass(frozen=True, slots=True)
class ReconcileOperationsUseCase:
    """Conservatively interrupt active Operations after ownership is lost."""

    ports: OperationPorts

    def execute(self, failed_apply_operation_id: OperationId | None = None) -> tuple[OperationId, ...]:
        """Commit all active interruptions atomically and return repaired identities."""
        with self.ports.uow as uow:
            candidates = tuple(uow.operations.list_reconciliation_candidates())
            now = self.ports.clock.now()
            repaired: list[OperationId] = []
            for operation in candidates:
                managed_state_repaired = operation.kind is OperationKind.APPLY_PLAN and _reconcile_apply_state(
                    uow, operation, now
                )
                operation_failed = (
                    operation.operation_id == failed_apply_operation_id
                    and operation.kind is OperationKind.APPLY_PLAN
                    and operation.status is OperationStatus.RUNNING
                )
                operation_interrupted = not operation_failed and operation.status in {
                    OperationStatus.QUEUED,
                    OperationStatus.RUNNING,
                }
                if operation_failed:
                    uow.operations.save(
                        operation.mark_failed(
                            error=OperationError(
                                code=OperationErrorCode.OPERATION_FAILED,
                                message=APPLY_FAILED_MESSAGE,
                                retryable=False,
                            ),
                            completed_at=now,
                            result_expires_at=now + timedelta(hours=OPERATION_RESULT_RETENTION_HOURS),
                            tombstone_expires_at=now + timedelta(days=OPERATION_TOMBSTONE_RETENTION_DAYS),
                        )
                    )
                elif operation_interrupted:
                    interrupted = operation.mark_interrupted(
                        error=OperationError(
                            code=OperationErrorCode.OPERATION_INTERRUPTED,
                            message=INTERRUPTED_MESSAGE,
                            retryable=False,
                        ),
                        completed_at=now,
                        result_expires_at=now + timedelta(hours=OPERATION_RESULT_RETENTION_HOURS),
                        tombstone_expires_at=now + timedelta(days=OPERATION_TOMBSTONE_RETENTION_DAYS),
                    )
                    uow.operations.save(interrupted)
                if managed_state_repaired or operation_failed or operation_interrupted:
                    repaired.append(operation.operation_id)
            if repaired:
                uow.commit()
            return tuple(repaired)


def _reconcile_apply_state(uow: UnitOfWork, operation: Operation, completed_at: datetime) -> bool:
    """Make one claimed Apply terminal using only its durable action/event evidence."""
    if operation.plan_id is None or operation.run_id is None:
        return False

    plan = uow.plans.get(operation.plan_id)
    run = uow.runs.get(operation.run_id)
    if plan is None or run is None:
        return False
    if plan.status is not PlanStatus.APPLYING and run.status is not RunStatus.RUNNING:
        return False

    _mark_unconfirmed_actions(uow, tuple(uow.plan_actions.list_by_plan(plan.plan_id)))
    actions = tuple(uow.plan_actions.list_by_plan(plan.plan_id))
    events = tuple(uow.file_events.list_by_run(run.run_id))
    final_plan, final_run = _reconciled_apply_outcome(plan, run, actions, events, completed_at)

    if plan.status is PlanStatus.APPLYING:
        uow.plans.save(final_plan)
    if run.status is RunStatus.RUNNING:
        uow.runs.save(final_run)
    return True


def _mark_unconfirmed_actions(uow: UnitOfWork, actions: Sequence[PlanAction]) -> None:
    for action in actions:
        if action.status is not ActionStatus.PLANNED:
            continue
        if action.action_type is ActionType.SKIP:
            uow.plan_actions.save(action.mark_applied())
        elif action.action_type in {ActionType.MOVE, ActionType.REFRESH_METADATA}:
            uow.plan_actions.save(action.mark_failed(PlanActionReason.OPERATION_INTERRUPTED))


def _reconciled_apply_outcome(
    plan: Plan,
    run: Run,
    actions: Sequence[PlanAction],
    events: Sequence[FileEvent],
    completed_at: datetime,
) -> tuple[Plan, Run]:
    eligible_actions = tuple(
        action for action in actions if action.action_type in {ActionType.MOVE, ActionType.REFRESH_METADATA}
    )
    success_count = sum(action.status is ActionStatus.APPLIED for action in eligible_actions)
    failure_count = sum(action.status is ActionStatus.FAILED for action in eligible_actions)
    has_pending_event = any(event.status is FileEventStatus.PENDING for event in events)
    if failure_count == 0 and not has_pending_event:
        return plan.mark_applied(), run.mark_succeeded(completed_at)
    if success_count > 0:
        return (
            plan.mark_partial_failed(),
            run.mark_partial_failed(completed_at, APPLY_INTERRUPTED_SUMMARY),
        )
    return plan.mark_failed(), run.mark_failed(completed_at, APPLY_INTERRUPTED_SUMMARY)


@dataclass(frozen=True, slots=True)
class CleanupOperationsUseCase:
    """Apply the two-phase terminal Operation retention policy."""

    ports: OperationPorts

    def execute(self) -> tuple[int, int]:
        """Expire payloads then purge elapsed tombstones in one transaction."""
        with self.ports.uow as uow:
            now = self.ports.clock.now()
            expired_payloads = uow.operations.expire_terminal_payloads(now)
            purged_tombstones = uow.operations.purge_expired_tombstones(now)
            if expired_payloads or purged_tombstones:
                uow.commit()
            return expired_payloads, purged_tombstones
