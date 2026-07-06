"""
Summary: Defines plan query request and response data.
Why: Gives CLI and later UI stable Plan inspection contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.plan import Plan, PlanStatus, PlanType
    from omym2.domain.models.plan_action import ActionStatus, PlanAction
    from omym2.shared.ids import LibraryId, PlanId


@dataclass(frozen=True, slots=True)
class ListPlansRequest:
    """Request to list Plans for one Library or all known Libraries.

    Optional status/plan_type filters and limit are applied after
    fetch and sort; see ListPlansUseCase for the exact pipeline order.
    """

    library_id: LibraryId | None = None
    status: PlanStatus | None = None
    plan_type: PlanType | None = None
    limit: int | None = None


@dataclass(frozen=True, slots=True)
class GetPlanDetailRequest:
    """Request to load one Plan and its recorded actions.

    An optional action_status filters the returned actions; it never
    affects PlanDetail.total_action_count, which always reflects the
    unfiltered action count.
    """

    plan_id: PlanId
    action_status: ActionStatus | None = None


@dataclass(frozen=True, slots=True)
class PlanDetail:
    """Plan detail response with actions in review order.

    total_action_count is the unfiltered action count, computed before
    any action_status filtering, so callers can detect filtered output.
    """

    plan: Plan
    actions: tuple[PlanAction, ...]
    total_action_count: int
