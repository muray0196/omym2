"""
Summary: Retrieves one retained durable Operation for polling.
Why: Distinguishes full status, expired tombstones, and unknown identities without mutation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.domain.models.operation import Operation, OperationTombstone
from omym2.features.operations.dto import OperationExpiredError, OperationNotFoundError

if TYPE_CHECKING:
    from omym2.features.operations.ports import OperationPorts
    from omym2.shared.ids import OperationId


@dataclass(frozen=True, slots=True)
class GetOperationUseCase:
    """Return one full read-only Operation snapshot."""

    ports: OperationPorts

    def execute(self, operation_id: OperationId) -> Operation:
        """Return a full resource or raise the retained lookup condition."""
        with self.ports.uow as uow:
            retained = uow.operations.lookup(operation_id)
        if retained is None:
            raise OperationNotFoundError
        if isinstance(retained, OperationTombstone):
            raise OperationExpiredError
        return retained
