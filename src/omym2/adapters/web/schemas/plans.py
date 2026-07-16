"""
Summary: Defines typed Web API resources for read-only Plan inspection.
Why: Keeps Plan browsing envelopes independent of opaque persisted summaries.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003  # Pydantic resolves timestamp schema types at runtime.
from uuid import UUID  # noqa: TC003  # Pydantic resolves UUID schema types at runtime.

from omym2.adapters.web.schemas.api_errors import ApiError, ApiModel
from omym2.adapters.web.schemas.browsing import (
    FacetValueResource,  # noqa: TC001  # Pydantic resolves nested schema types at runtime.
    NonNegativeCount,  # noqa: TC001  # Pydantic resolves annotated schema types at runtime.
    PageInfo,  # noqa: TC001  # Pydantic resolves nested schema types at runtime.
)
from omym2.domain.models.artist_name_resolution import (  # noqa: TC001  # Pydantic resolves enum schema types at runtime.
    ArtistNameResolutionIssue,
    ArtistNameResolutionProvenance,
)
from omym2.domain.models.plan import (  # noqa: TC001  # Pydantic resolves enum schema types at runtime.
    PlanStatus,
    PlanType,
)
from omym2.domain.models.plan_action import (  # noqa: TC001  # Pydantic resolves enum schema types at runtime.
    ActionStatus,
    ActionType,
    PlanActionReason,
)
from omym2.features.plans.dto import (
    PlanActionGrouping,  # noqa: TC001  # Pydantic resolves enum schema types at runtime.
)


class PlanActionTypeCounts(ApiModel):
    """Counts for every recorded PlanAction type within one status."""

    move: NonNegativeCount
    move_lyrics: NonNegativeCount
    move_artwork: NonNegativeCount
    move_unprocessed: NonNegativeCount
    skip: NonNegativeCount
    refresh_metadata: NonNegativeCount


class PlanActionSummaryCounts(ApiModel):
    """The complete status matrix for one Plan's current recorded actions."""

    planned: PlanActionTypeCounts
    blocked: PlanActionTypeCounts
    applied: PlanActionTypeCounts
    failed: PlanActionTypeCounts


class PlanActionSummary(ApiModel):
    """Typed current action count summary that replaces opaque Plan storage data."""

    total: NonNegativeCount
    counts: PlanActionSummaryCounts


class PlanSummary(ApiModel):
    """One Plan list row without execution capabilities or opaque persistence fields."""

    plan_id: UUID
    library_id: UUID
    plan_type: PlanType
    status: PlanStatus
    created_at: datetime
    summary: PlanActionSummary


class PlanHeader(ApiModel):
    """One Plan header without actions or an opaque persisted summary."""

    plan_id: UUID
    library_id: UUID
    plan_type: PlanType
    status: PlanStatus
    created_at: datetime
    config_hash: str
    library_root_at_plan: str


class PlanCapabilities(ApiModel):
    """Backend-authoritative operation availability for one Plan."""

    can_apply: bool
    can_cancel: bool
    can_recreate: bool
    disabled_reasons: tuple[ApiError, ...]


class PlanDetailData(ApiModel):
    """Plan header, current action summary, and advisory capabilities."""

    plan: PlanHeader
    summary: PlanActionSummary
    capabilities: PlanCapabilities
    active_operation_id: UUID | None


class ArtistNameResolutionDiagnosticResource(ApiModel):
    """One reviewable artist-field resolution outcome."""

    source_name: str | None
    resolved_name: str | None
    provenance: ArtistNameResolutionProvenance
    issue: ArtistNameResolutionIssue | None


class ArtistNameDiagnosticsResource(ApiModel):
    """Artist and album-artist naming evidence recorded for one action."""

    artist: ArtistNameResolutionDiagnosticResource
    album_artist: ArtistNameResolutionDiagnosticResource


class PlanActionResource(ApiModel):
    """One recorded PlanAction in immutable review order."""

    action_id: UUID
    plan_id: UUID
    library_id: UUID
    track_id: UUID | None
    action_type: ActionType
    source_path: str | None
    target_path: str | None
    content_hash_at_plan: str | None
    metadata_hash_at_plan: str | None
    status: ActionStatus
    reason: PlanActionReason | None
    sort_order: int
    companion_asset_id: UUID | None
    owner_action_id: UUID | None
    depends_on_action_ids: tuple[UUID, ...]
    artist_name_diagnostics: ArtistNameDiagnosticsResource | None


class PlanActionFacetSets(ApiModel):
    """The filter-aware status, action type, and non-null reason facets."""

    status: tuple[FacetValueResource[ActionStatus], ...]
    action_type: tuple[FacetValueResource[ActionType], ...]
    reason: tuple[FacetValueResource[PlanActionReason], ...]


class PlanActionFacetsData(ApiModel):
    """PlanAction facets plus the Plan-wide target-collision risk count."""

    facets: PlanActionFacetSets
    total: NonNegativeCount
    target_collisions: NonNegativeCount


class PlanActionGroupResource(ApiModel):
    """One enriched PlanAction group row for drill-down browsing."""

    key: str
    label: str
    count: NonNegativeCount
    blocked_count: NonNegativeCount
    top_reason: PlanActionReason | None


class PlanActionGroupsData(ApiModel):
    """One filter-aware page of enriched PlanAction groups."""

    group_by: PlanActionGrouping
    items: tuple[PlanActionGroupResource, ...]
    page: PageInfo
