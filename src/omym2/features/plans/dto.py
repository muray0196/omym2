"""
Summary: Defines plan query request and response data.
Why: Gives CLI and later UI stable Plan inspection contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.plan import Plan
    from omym2.domain.models.plan_action import PlanAction
    from omym2.shared.ids import LibraryId, PlanId


@dataclass(frozen=True, slots=True)
class ListPlansRequest:
    """Request to list Plans for one Library or all known Libraries."""

    library_id: LibraryId | None = None


@dataclass(frozen=True, slots=True)
class GetPlanDetailRequest:
    """Request to load one Plan and its recorded actions."""

    plan_id: PlanId


@dataclass(frozen=True, slots=True)
class PlanDetail:
    """Plan detail response with actions in review order."""

    plan: Plan
    actions: tuple[PlanAction, ...]
