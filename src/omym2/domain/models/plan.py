"""
Summary: Defines reviewed Plans made of recorded actions.
Why: Ensures apply uses stored PlanActions instead of recalculating paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from omym2.shared.time import as_utc

if TYPE_CHECKING:
    from datetime import datetime

    from omym2.domain.models.plan_action import PlanAction
    from omym2.shared.ids import LibraryId, PlanId, RunId


class PlanType(StrEnum):
    """Supported Plan types."""

    ADD = "add"
    ORGANIZE = "organize"
    REFRESH = "refresh"
    UNDO = "undo"


class PlanStatus(StrEnum):
    """Supported Plan statuses."""

    READY = "ready"
    APPLYING = "applying"
    APPLIED = "applied"
    PARTIAL_FAILED = "partial_failed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


TERMINAL_PLAN_STATUSES = frozenset(
    {
        PlanStatus.APPLIED,
        PlanStatus.PARTIAL_FAILED,
        PlanStatus.FAILED,
        PlanStatus.CANCELLED,
        PlanStatus.EXPIRED,
    }
)


@dataclass(frozen=True, slots=True)
class Plan:
    """Scheduled set of actions before execution."""

    plan_id: PlanId
    library_id: LibraryId
    plan_type: PlanType
    status: PlanStatus
    created_at: datetime
    config_hash: str
    library_root_at_plan: str
    source_root_at_plan: str | None = None
    source_run_id: RunId | None = None
    summary: dict[str, str] = field(default_factory=dict)
    actions: tuple[PlanAction, ...] = ()

    def __post_init__(self) -> None:
        """Normalize timestamps and immutable action collections."""
        object.__setattr__(self, "created_at", as_utc(self.created_at))
        object.__setattr__(self, "actions", tuple(self.actions))

    @property
    def is_terminal(self) -> bool:
        """Return whether this Plan can no longer be applied."""
        return self.status in TERMINAL_PLAN_STATUSES

    def mark_applied(self) -> Plan:
        """Return this Plan as fully applied."""
        return self._with_status(PlanStatus.APPLIED)

    def mark_partial_failed(self) -> Plan:
        """Return this Plan as partially failed."""
        return self._with_status(PlanStatus.PARTIAL_FAILED)

    def mark_failed(self) -> Plan:
        """Return this Plan as failed."""
        return self._with_status(PlanStatus.FAILED)

    def mark_expired(self) -> Plan:
        """Return this Plan as expired before an apply run starts."""
        return self._with_status(PlanStatus.EXPIRED)

    def mark_cancelled(self) -> Plan:
        """Return this ready Plan as cancelled before apply starts."""
        return self._with_status(PlanStatus.CANCELLED)

    def _with_status(self, status: PlanStatus) -> Plan:
        return Plan(
            plan_id=self.plan_id,
            library_id=self.library_id,
            plan_type=self.plan_type,
            status=status,
            created_at=self.created_at,
            config_hash=self.config_hash,
            library_root_at_plan=self.library_root_at_plan,
            source_root_at_plan=self.source_root_at_plan,
            source_run_id=self.source_run_id,
            summary=dict(self.summary),
            actions=self.actions,
        )
