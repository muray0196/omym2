"""
Summary: Interrupts orphaned durable Operations and cleans retained payloads.
Why: Makes process loss visible without automatically resuming unconfirmed work.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from omym2.config import OPERATION_RESULT_RETENTION_HOURS, OPERATION_TOMBSTONE_RETENTION_DAYS
from omym2.domain.models.operation import OperationError, OperationErrorCode, OperationStatus

if TYPE_CHECKING:
    from omym2.features.operations.ports import OperationPorts

INTERRUPTED_MESSAGE = "The process stopped before this Operation reached a confirmed result."


@dataclass(frozen=True, slots=True)
class ReconcileOperationsUseCase:
    """Conservatively interrupt active Operations after ownership is lost."""

    ports: OperationPorts

    def execute(self) -> tuple[object, ...]:
        """Commit all active interruptions atomically and return repaired identities."""
        with self.ports.uow as uow:
            candidates = tuple(uow.operations.list_reconciliation_candidates())
            now = self.ports.clock.now()
            repaired: list[object] = []
            for operation in candidates:
                if operation.status not in {OperationStatus.QUEUED, OperationStatus.RUNNING}:
                    continue
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
                repaired.append(interrupted.operation_id)
            if repaired:
                uow.commit()
            return tuple(repaired)


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
