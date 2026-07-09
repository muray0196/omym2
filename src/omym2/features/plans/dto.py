"""
Summary: Defines plan query request and response data.
Why: Gives CLI and Web inspection stable Plan/PlanAction browsing contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from omym2.shared.pagination import PageRequest

if TYPE_CHECKING:
    from omym2.domain.models.plan import Plan, PlanStatus, PlanType
    from omym2.domain.models.plan_action import ActionStatus, PlanAction
    from omym2.shared.ids import LibraryId, PlanId
    from omym2.shared.pagination import FacetValue


@dataclass(frozen=True, slots=True)
class ListPlansRequest:
    """Request one keyset page of Plans for a Library or every known Library."""

    library_id: LibraryId | None = None
    status: PlanStatus | None = None
    plan_type: PlanType | None = None
    page: PageRequest = field(default_factory=PageRequest)


@dataclass(frozen=True, slots=True)
class GetPlanHeaderRequest:
    """Request to load one Plan header by ID, without its recorded actions."""

    plan_id: PlanId


@dataclass(frozen=True, slots=True)
class ListPlanActionsRequest:
    """Request one keyset page of a Plan's recorded actions.

    An optional `status` filter is pushed into the query itself, not applied
    as a post-fetch Python filter.
    """

    plan_id: PlanId
    status: ActionStatus | None = None
    page: PageRequest = field(default_factory=PageRequest)


@dataclass(frozen=True, slots=True)
class PlanActionFacetsRequest:
    """Request PlanAction status/action_type facet counts for one Plan."""

    plan_id: PlanId


@dataclass(frozen=True, slots=True)
class PlanActionFacetsResult:
    """PlanAction status/action_type facet counts plus the unfiltered action total.

    `total` is the sum of the status facet counts: every PlanAction has
    exactly one status, so the status breakdown always partitions the full
    unfiltered action set for the Plan.
    """

    status_facets: tuple[FacetValue, ...]
    action_type_facets: tuple[FacetValue, ...]
    total: int


@dataclass(frozen=True, slots=True)
class GroupPlanActionsRequest:
    """Request one keyset page of a Plan's actions grouped by target directory."""

    plan_id: PlanId
    page: PageRequest = field(default_factory=PageRequest)


@dataclass(frozen=True, slots=True)
class PlanDetail:
    """A Plan header bundled with a set of its recorded actions.

    Unlike the other DTOs in this module, no single usecase returns
    PlanDetail: the Web API's Plan detail route is header-only per
    `docs/contracts/web-api.md`, so callers that still want a bundled
    plan+actions+total view (the CLI's `plans <PLAN_ID>` command) assemble
    one from `GetPlanHeaderUseCase`, `ListPlanActionsUseCase`, and
    `GetPlanActionFacetsUseCase` themselves. `total_action_count` is the
    unfiltered action count, independent of any status filtering applied to
    `actions`.
    """

    plan: Plan
    actions: tuple[PlanAction, ...]
    total_action_count: int
