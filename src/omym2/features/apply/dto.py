"""
Summary: Defines apply feature request data.
Why: Gives apply usecases stable contracts before file mutation support exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID

    from omym2.domain.models.operation import OperationLookup
    from omym2.shared.ids import OperationId, PlanId, RunId


@dataclass(frozen=True, slots=True)
class ApplyOptions:
    """User confirmation options shared by direct and orchestrated apply."""

    yes: bool = False


@dataclass(frozen=True, slots=True)
class ApplyPlanRequest:
    """Request to apply one reviewed Plan."""

    plan_id: PlanId
    run_id: RunId
    operation_id: OperationId
    options: ApplyOptions = field(default_factory=ApplyOptions)


@dataclass(frozen=True, slots=True)
class ClaimApplyRequest:
    """Validated durable identity for atomically claiming one ready Plan."""

    plan_id: PlanId
    idempotency_key: UUID
    request_fingerprint: str


@dataclass(frozen=True, slots=True)
class ClaimApplyResult:
    """New atomic Apply reservation or one exact retained replay."""

    lookup: OperationLookup
    is_new: bool
