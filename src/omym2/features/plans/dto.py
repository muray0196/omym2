"""
Summary: Defines plan query request and response data.
Why: Gives CLI and Web inspection stable Plan/PlanAction browsing contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from omym2.domain.models.plan_action import ActionStatus, ActionType
from omym2.shared.pagination import PageRequest

if TYPE_CHECKING:
    from collections.abc import Mapping

    from omym2.domain.models.plan import Plan, PlanStatus, PlanType
    from omym2.domain.models.plan_action import PlanAction, PlanActionReason
    from omym2.shared.ids import ActionId, LibraryId, PlanId
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
class PlanActionTypeCounts:
    """Counts of each action type within one recorded action status."""

    move: int
    move_lyrics: int
    move_artwork: int
    move_unprocessed: int
    skip: int
    refresh_metadata: int


@dataclass(frozen=True, slots=True)
class PlanActionSummary:
    """The complete current PlanAction status/action-type matrix for one Plan."""

    total: int
    planned: PlanActionTypeCounts
    blocked: PlanActionTypeCounts
    applied: PlanActionTypeCounts
    failed: PlanActionTypeCounts


@dataclass(frozen=True, slots=True)
class ListPlansRequest:
    """Request one keyset page of Plans for a Library or every known Library."""

    library_id: LibraryId | None = None
    search: str | None = None
    status: PlanStatus | None = None
    plan_type: PlanType | None = None
    blocked_only: bool = False
    page: PageRequest = field(default_factory=PageRequest)


@dataclass(frozen=True, slots=True)
class GetPlanActionSummariesRequest:
    """Request current action summaries for a bounded set of listed Plans."""

    plan_ids: tuple[PlanId, ...]


@dataclass(frozen=True, slots=True)
class GetPlanActionDependenciesRequest:
    """Request durable dependency IDs for a bounded set of PlanActions."""

    action_ids: tuple[ActionId, ...]


@dataclass(frozen=True, slots=True)
class GetPlanHeaderRequest:
    """Request to load one Plan header by ID, without its recorded actions."""

    plan_id: PlanId


@dataclass(frozen=True, slots=True)
class CancelPlanRequest:
    """Request a compare-and-set cancellation of one ready Plan."""

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
    `GetPlanActionFacetsUseCase`, plus `GetPlanActionDependenciesUseCase` for
    full action detail. `total_action_count` is the unfiltered action count,
    independent of any status filtering applied to `actions`.
    `action_dependencies` contains the durable dependency IDs for those
    displayed actions; callers must not derive dependency order from
    `sort_order` or `owner_action_id`.
    """

    plan: Plan
    actions: tuple[PlanAction, ...]
    total_action_count: int
    action_dependencies: Mapping[ActionId, tuple[ActionId, ...]]


def plan_action_summary_from_counts(
    counts: Mapping[tuple[ActionStatus, ActionType], int],
) -> PlanActionSummary:
    """Build one complete typed summary from persisted status/action-type counts."""
    planned = _action_type_counts_for_status(counts, ActionStatus.PLANNED)
    blocked = _action_type_counts_for_status(counts, ActionStatus.BLOCKED)
    applied = _action_type_counts_for_status(counts, ActionStatus.APPLIED)
    failed = _action_type_counts_for_status(counts, ActionStatus.FAILED)
    return PlanActionSummary(
        total=sum(counts.values()),
        planned=planned,
        blocked=blocked,
        applied=applied,
        failed=failed,
    )


def _action_type_counts_for_status(
    counts: Mapping[tuple[ActionStatus, ActionType], int],
    status: ActionStatus,
) -> PlanActionTypeCounts:
    """Return the fixed action-type counts for one status row."""
    return PlanActionTypeCounts(
        move=counts.get((status, ActionType.MOVE), 0),
        move_lyrics=counts.get((status, ActionType.MOVE_LYRICS), 0),
        move_artwork=counts.get((status, ActionType.MOVE_ARTWORK), 0),
        move_unprocessed=counts.get((status, ActionType.MOVE_UNPROCESSED), 0),
        skip=counts.get((status, ActionType.SKIP), 0),
        refresh_metadata=counts.get((status, ActionType.REFRESH_METADATA), 0),
    )
