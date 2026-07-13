"""
Summary: Computes backend-authoritative read-only Plan capabilities.
Why: Keeps Plan operation availability out of Web status inference.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from omym2.domain.models.plan import PlanStatus, PlanType
from omym2.features.plans.usecases.get_plan_header import PLAN_NOT_FOUND_MESSAGE, PlanNotFoundError

if TYPE_CHECKING:
    from omym2.features.plans.ports import PlanQueryPorts
    from omym2.shared.ids import PlanId


class PlanCapability(StrEnum):
    """Plan controls whose availability is projected by the backend."""

    APPLY = "can_apply"
    CANCEL = "can_cancel"
    RECREATE = "can_recreate"


class PlanCapabilityReason(StrEnum):
    """Feature-level reasons why one Plan control is unavailable."""

    PLAN_NOT_READY = "plan_not_ready"
    LIBRARY_NOT_FOUND = "library_not_found"
    LIBRARY_ROOT_CHANGED = "library_root_changed"
    UNDO_RECREATES_FROM_HISTORY = "undo_recreates_from_history"


@dataclass(frozen=True, slots=True)
class GetPlanCapabilitiesRequest:
    """Request current operation availability for one Plan."""

    plan_id: PlanId


@dataclass(frozen=True, slots=True)
class PlanCapabilityDisabledReason:
    """One capability-specific disabled reason."""

    capability: PlanCapability
    reason: PlanCapabilityReason


@dataclass(frozen=True, slots=True)
class PlanCapabilitiesResult:
    """Current advisory Plan capabilities and their disabled reasons."""

    can_apply: bool
    can_cancel: bool
    can_recreate: bool
    disabled_reasons: tuple[PlanCapabilityDisabledReason, ...]


@dataclass(frozen=True, slots=True)
class GetPlanCapabilitiesUseCase:
    """Compute Plan capabilities from persisted Plan and Library state."""

    ports: PlanQueryPorts

    def execute(self, request: GetPlanCapabilitiesRequest) -> PlanCapabilitiesResult:
        """Return an advisory snapshot that mutations must revalidate later."""
        with self.ports.uow as uow:
            plan = uow.plans.get(request.plan_id)
            if plan is None:
                raise PlanNotFoundError(PLAN_NOT_FOUND_MESSAGE)
            library = uow.libraries.get(plan.library_id)

        disabled_reasons: list[PlanCapabilityDisabledReason] = []
        can_apply = plan.status is PlanStatus.READY
        can_cancel = plan.status is PlanStatus.READY
        can_recreate = plan.plan_type is not PlanType.UNDO

        if not can_apply:
            disabled_reasons.append(
                PlanCapabilityDisabledReason(PlanCapability.APPLY, PlanCapabilityReason.PLAN_NOT_READY)
            )
        elif library is None:
            can_apply = False
            disabled_reasons.append(
                PlanCapabilityDisabledReason(PlanCapability.APPLY, PlanCapabilityReason.LIBRARY_NOT_FOUND)
            )
        elif library.root_path != plan.library_root_at_plan:
            can_apply = False
            disabled_reasons.append(
                PlanCapabilityDisabledReason(PlanCapability.APPLY, PlanCapabilityReason.LIBRARY_ROOT_CHANGED)
            )

        if not can_cancel:
            disabled_reasons.append(
                PlanCapabilityDisabledReason(PlanCapability.CANCEL, PlanCapabilityReason.PLAN_NOT_READY)
            )

        if not can_recreate:
            disabled_reasons.append(
                PlanCapabilityDisabledReason(
                    PlanCapability.RECREATE,
                    PlanCapabilityReason.UNDO_RECREATES_FROM_HISTORY,
                )
            )

        return PlanCapabilitiesResult(
            can_apply=can_apply,
            can_cancel=can_cancel,
            can_recreate=can_recreate,
            disabled_reasons=tuple(disabled_reasons),
        )
