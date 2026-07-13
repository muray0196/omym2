"""
Summary: Reserves one idempotent durable Operation.
Why: Prevents duplicate work and enforces the application-wide active-operation slot.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.domain.models.operation import Operation, OperationTombstone
from omym2.features.common_ports import IdempotencyKeyReusedError, OperationInProgressError
from omym2.features.operations.dto import (
    ReserveOperationResult,
)

if TYPE_CHECKING:
    from omym2.features.operations.dto import ReserveOperationRequest
    from omym2.features.operations.ports import OperationPorts


@dataclass(frozen=True, slots=True)
class ReserveOperationUseCase:
    """Classify replay identity and durably reserve absent work."""

    ports: OperationPorts

    def execute(self, request: ReserveOperationRequest) -> ReserveOperationResult:
        """Return an exact replay or create one queued Operation."""
        with self.ports.uow as uow:
            retained = uow.operations.find_by_idempotency_key(request.idempotency_key)
            if retained is not None:
                _require_same_request(retained, request)
                return ReserveOperationResult(lookup=retained, is_new=False)

            active = uow.operations.find_active()
            if active is not None:
                raise OperationInProgressError(active)

            requested_at = self.ports.clock.now()
            operation = Operation.queued(
                operation_id=self.ports.id_generator.new_operation_id(),
                kind=request.kind,
                idempotency_key=request.idempotency_key,
                request_fingerprint=request.request_fingerprint,
                requested_at=requested_at,
                library_id=request.library_id,
                plan_id=request.plan_id,
                run_id=request.run_id,
            )
            uow.operations.save(operation)
            uow.commit()
            return ReserveOperationResult(lookup=operation, is_new=True)


@dataclass(frozen=True, slots=True)
class ClassifyOperationReplayUseCase:
    """Classify an idempotency key without acquiring a mutation slot."""

    ports: OperationPorts

    def execute(self, request: ReserveOperationRequest) -> Operation | OperationTombstone | None:
        """Return an exact retained request or reject mismatched key reuse."""
        with self.ports.uow as uow:
            retained = uow.operations.find_by_idempotency_key(request.idempotency_key)
        if retained is not None:
            _require_same_request(retained, request)
        return retained


def _require_same_request(
    retained: Operation | OperationTombstone,
    request: ReserveOperationRequest,
) -> None:
    if retained.kind is not request.kind or retained.request_fingerprint != request.request_fingerprint:
        raise IdempotencyKeyReusedError
