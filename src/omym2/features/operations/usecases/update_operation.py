"""
Summary: Advances running durable Operation state and terminal evidence.
Why: Centralizes lifecycle transitions and retention timestamps for workers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from omym2.config import OPERATION_RESULT_RETENTION_HOURS, OPERATION_TOMBSTONE_RETENTION_DAYS
from omym2.domain.models.operation import Operation, OperationProgress
from omym2.features.operations.dto import FinishOperationRequest, OperationLifecycleError

if TYPE_CHECKING:
    from omym2.features.operations.ports import OperationPorts
    from omym2.shared.ids import OperationId

INVALID_FINISH_REQUEST_MESSAGE = "Exactly one Operation result or error is required."
MISSING_FAILURE_EVIDENCE_MESSAGE = "Operation failure evidence is required."
MISSING_LIFECYCLE_STATE_MESSAGE = "Full Operation lifecycle state is unavailable."


@dataclass(frozen=True, slots=True)
class MarkOperationRunningUseCase:
    """Transition one committed reservation to running."""

    ports: OperationPorts

    def execute(self, operation_id: OperationId) -> Operation:
        """Persist a queued-to-running transition."""
        with self.ports.uow as uow:
            operation = _require_operation(uow.operations.lookup(operation_id))
            running = operation.mark_running(self.ports.clock.now())
            uow.operations.save(running)
            uow.commit()
            return running


@dataclass(frozen=True, slots=True)
class UpdateOperationProgressUseCase:
    """Persist real worker progress for one running Operation."""

    ports: OperationPorts

    def execute(self, operation_id: OperationId, progress: OperationProgress) -> Operation:
        """Persist a monotonic progress snapshot."""
        with self.ports.uow as uow:
            operation = _require_operation(uow.operations.lookup(operation_id))
            updated = operation.update_progress(progress, self.ports.clock.now())
            uow.operations.save(updated)
            uow.commit()
            return updated


@dataclass(frozen=True, slots=True)
class FinishOperationUseCase:
    """Persist one typed success or redacted terminal failure."""

    ports: OperationPorts

    def execute(self, request: FinishOperationRequest) -> Operation:
        """Finish running work and derive both retention boundaries once."""
        if (request.result is None) == (request.error is None):
            raise OperationLifecycleError(INVALID_FINISH_REQUEST_MESSAGE)

        with self.ports.uow as uow:
            operation = _require_operation(uow.operations.lookup(request.operation_id))
            completed_at = self.ports.clock.now()
            result_expires_at = completed_at + timedelta(hours=OPERATION_RESULT_RETENTION_HOURS)
            tombstone_expires_at = completed_at + timedelta(days=OPERATION_TOMBSTONE_RETENTION_DAYS)
            if request.result is not None:
                terminal = operation.mark_succeeded(
                    result=request.result,
                    completed_at=completed_at,
                    result_expires_at=result_expires_at,
                    tombstone_expires_at=tombstone_expires_at,
                )
            else:
                if request.error is None:
                    raise OperationLifecycleError(MISSING_FAILURE_EVIDENCE_MESSAGE)
                terminal = operation.mark_failed(
                    error=request.error,
                    completed_at=completed_at,
                    result_expires_at=result_expires_at,
                    tombstone_expires_at=tombstone_expires_at,
                )
            uow.operations.save(terminal)
            uow.commit()
            return terminal


def _require_operation(retained: object) -> Operation:
    if not isinstance(retained, Operation):
        raise OperationLifecycleError(MISSING_LIFECYCLE_STATE_MESSAGE)
    return retained
