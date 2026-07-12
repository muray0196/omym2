"""
Summary: Defines plan query request and response data.
Why: Gives CLI and Web inspection stable Plan/PlanAction browsing contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from omym2.shared.pagination import PageRequest

if TYPE_CHECKING:
    from omym2.domain.models.plan import Plan, PlanStatus, PlanType
    from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction, PlanActionReason
    from omym2.shared.ids import LibraryId, PlanId
    from omym2.shared.pagination import FacetValue


class PlanActionGrouping(StrEnum):
    """Supported group_by keys for browsing one Plan's actions."""

    TARGET_DIRECTORY = "target_directory"
    SOURCE_DIRECTORY = "source_directory"
    ARTIST_ALBUM = "artist_album"
    ACTION_TYPE = "action_type"
    STATUS = "status"
    BLOCK_REASON = "block_reason"
    EXTENSION = "extension"


@dataclass(frozen=True, slots=True)
class PlanActionGroup:
    """One grouped row of a Plan's actions, enriched with review risk fields.

    Extends the generic group row (`key`, `label`, `count`) with
    `blocked_count` (members with status blocked) and `top_reason` (the most
    frequent non-null reason among members; ties resolve to the
    lexicographically smallest value; None when no member has a reason).
    """

    key: str
    label: str
    count: int
    blocked_count: int
    top_reason: str | None


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
    as a post-fetch Python filter. `grouping` and `group_key` select one
    derived action group as a drill-down filter and must be provided
    together; the usecase rejects one without the other (routes translate
    that into an HTTP 400). The group filter combines with `status` as AND.
    """

    plan_id: PlanId
    search: str | None = None
    status: ActionStatus | None = None
    action_type: ActionType | None = None
    reason: PlanActionReason | None = None
    grouping: PlanActionGrouping | None = None
    group_key: str | None = None
    page: PageRequest = field(default_factory=PageRequest)


@dataclass(frozen=True, slots=True)
class PlanActionFacetsRequest:
    """Request filtered PlanAction status/action_type/reason facet counts for one Plan."""

    plan_id: PlanId
    search: str | None = None
    status: ActionStatus | None = None
    action_type: ActionType | None = None
    reason: PlanActionReason | None = None


@dataclass(frozen=True, slots=True)
class PlanActionFacetsResult:
    """PlanAction status/action_type/reason facet counts plus Plan-wide risk scalars.

    `total` is the sum of the status facet counts: every PlanAction has
    exactly one status, so the status breakdown always partitions the full
    unfiltered action set for the Plan. `reason_facets` breaks down only the
    non-null recorded reasons. `target_collisions` counts the distinct
    non-null target_path values recorded by 2 or more of the Plan's actions.
    """

    status_facets: tuple[FacetValue, ...]
    action_type_facets: tuple[FacetValue, ...]
    reason_facets: tuple[FacetValue, ...]
    total: int
    target_collisions: int


@dataclass(frozen=True, slots=True)
class GroupPlanActionsRequest:
    """Request one keyset page of a Plan's actions grouped by a supported grouping."""

    plan_id: PlanId
    search: str | None = None
    status: ActionStatus | None = None
    action_type: ActionType | None = None
    reason: PlanActionReason | None = None
    grouping: PlanActionGrouping = PlanActionGrouping.TARGET_DIRECTORY
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
