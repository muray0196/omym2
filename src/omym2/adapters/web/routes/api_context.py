"""
Summary: Resolves Web route dependencies at request time.
Why: Lets production and schema-only apps register exactly the same router without I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, cast

from fastapi import Depends, Request

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from uuid import UUID

    from fastapi import FastAPI

    from omym2.domain.models.file_event import FileEvent
    from omym2.domain.models.operation import Operation
    from omym2.domain.models.plan import Plan
    from omym2.domain.models.plan_action import PlanAction
    from omym2.domain.models.run import Run
    from omym2.domain.models.track import Track
    from omym2.features.add.dto import CreateAddPlanRequest
    from omym2.features.artist_ids.dto import GenerateArtistIdDraftRequest, GenerateArtistIdDraftResult
    from omym2.features.bootstrap.dto import BootstrapResult
    from omym2.features.check.dto import (
        CheckIssueFacetsRequest,
        CheckIssueFacetsResult,
        CheckLibraryRequest,
        GroupCheckIssuesRequest,
        ListCheckIssuesRequest,
        ListCheckIssuesResult,
    )
    from omym2.features.common_ports import CheckIssueGroup
    from omym2.features.history.dto import (
        FileEventStatusFacetsRequest,
        FileEventStatusFacetsResult,
        GetRunDetailRequest,
        GroupRunEventsRequest,
        ListRunEventsRequest,
        ListRunsRequest,
        RunDetailResult,
        RunStatusFacetsRequest,
        RunStatusFacetsResult,
    )
    from omym2.features.libraries.dto import InspectLibrariesRequest, LibraryInspection
    from omym2.features.operations.dto import ReserveOperationResult
    from omym2.features.organize.dto import CreateOrganizePlanRequest
    from omym2.features.plans.dto import (
        CancelPlanRequest,
        GetPlanActionDependenciesRequest,
        GetPlanActionSummariesRequest,
        GetPlanHeaderRequest,
        GroupPlanActionsRequest,
        ListPlanActionsRequest,
        ListPlansRequest,
        PlanActionFacetsRequest,
        PlanActionFacetsResult,
        PlanActionGroup,
        PlanActionSummary,
    )
    from omym2.features.plans.usecases.get_plan_capabilities import (
        GetPlanCapabilitiesRequest,
        PlanCapabilitiesResult,
    )
    from omym2.features.refresh.dto import CreateRefreshPlanRequest
    from omym2.features.settings.dto import (
        PathPolicyPreviewRequest,
        PathPolicyPreviewResult,
        SaveSettingsRequest,
        SettingsCandidateResult,
        SettingsEditResult,
        ValidateSettingsRequest,
    )
    from omym2.features.tracks.dto import (
        GetTrackRequest,
        GroupTracksRequest,
        ListTracksRequest,
        TrackStatusFacetsRequest,
        TrackStatusFacetsResult,
    )
    from omym2.features.undo.dto import CreateUndoPlanRequest
    from omym2.shared.ids import ActionId, OperationId, PlanId, RunId
    from omym2.shared.pagination import GroupCount, Page


@dataclass(frozen=True, slots=True)
class PlansRouteContext:
    """Plan query and synchronous cancellation handlers resolved by platform composition."""

    list_plans: Callable[[ListPlansRequest], Page[Plan]]
    get_plan_header: Callable[[GetPlanHeaderRequest], Plan]
    get_plan_action_summaries: Callable[[GetPlanActionSummariesRequest], dict[PlanId, PlanActionSummary]]
    get_plan_capabilities: Callable[[GetPlanCapabilitiesRequest], PlanCapabilitiesResult]
    list_plan_actions: Callable[[ListPlanActionsRequest], Page[PlanAction]]
    get_plan_action_dependencies: Callable[
        [GetPlanActionDependenciesRequest],
        Mapping[ActionId, tuple[ActionId, ...]],
    ]
    get_plan_action_facets: Callable[[PlanActionFacetsRequest], PlanActionFacetsResult]
    group_plan_actions: Callable[[GroupPlanActionsRequest], Page[PlanActionGroup]]
    cancel_plan: Callable[[CancelPlanRequest], Plan]
    active_operation_id: Callable[[PlanId], OperationId | None]
    conflicting_operation_id: Callable[[], OperationId | None]


@dataclass(frozen=True, slots=True)
class TracksRouteContext:
    """Read-only Track query handlers resolved by the platform composition root."""

    list_tracks: Callable[[ListTracksRequest], Page[Track]]
    get_track: Callable[[GetTrackRequest], Track]
    get_track_status_facets: Callable[[TrackStatusFacetsRequest], TrackStatusFacetsResult]
    group_tracks: Callable[[GroupTracksRequest], Page[GroupCount]]


@dataclass(frozen=True, slots=True)
class LibrariesRouteContext:
    """Read-only Library inspection handler resolved by the platform composition root."""

    inspect_libraries: Callable[[InspectLibrariesRequest], tuple[LibraryInspection, ...]]


@dataclass(frozen=True, slots=True)
class HistoryRouteContext:
    """Run and FileEvent query handlers resolved by the platform composition root."""

    list_runs: Callable[[ListRunsRequest], Page[Run]]
    get_run_detail: Callable[[GetRunDetailRequest], RunDetailResult]
    get_run_status_facets: Callable[[RunStatusFacetsRequest], RunStatusFacetsResult]
    list_run_events: Callable[[ListRunEventsRequest], Page[FileEvent]]
    get_file_event_status_facets: Callable[[FileEventStatusFacetsRequest], FileEventStatusFacetsResult]
    group_run_events: Callable[[GroupRunEventsRequest], Page[GroupCount]]
    active_operation_id: Callable[[RunId], OperationId | None]


@dataclass(frozen=True, slots=True)
class CheckRouteContext:
    """Read-only persisted Check handlers resolved by the platform composition root."""

    list_check_issues: Callable[[ListCheckIssuesRequest], ListCheckIssuesResult]
    get_check_issue_facets: Callable[[CheckIssueFacetsRequest], CheckIssueFacetsResult]
    group_check_issues: Callable[[GroupCheckIssuesRequest], Page[CheckIssueGroup]]


@dataclass(frozen=True, slots=True)
class SettingsRouteContext:
    """Settings edit and draft handlers resolved by the platform composition root."""

    get_settings: Callable[[], SettingsEditResult]
    validate_settings: Callable[[ValidateSettingsRequest], SettingsCandidateResult]
    preview_path_policy: Callable[[PathPolicyPreviewRequest], PathPolicyPreviewResult]
    save_settings: Callable[[SaveSettingsRequest], SettingsCandidateResult]
    generate_artist_id_draft: Callable[[GenerateArtistIdDraftRequest], GenerateArtistIdDraftResult]


@dataclass(frozen=True, slots=True)
class OperationsRouteContext:
    """Durable planning, Check, Apply, and Undo handlers resolved by platform orchestration."""

    get_operation: Callable[[OperationId], Operation]
    active_operation_id: Callable[[], OperationId | None]
    start_add_plan: Callable[[CreateAddPlanRequest, UUID], ReserveOperationResult]
    start_organize_plan: Callable[[CreateOrganizePlanRequest, UUID], ReserveOperationResult]
    start_refresh_plan: Callable[[CreateRefreshPlanRequest, UUID], ReserveOperationResult]
    start_check: Callable[[CheckLibraryRequest, UUID], ReserveOperationResult]
    start_apply_plan: Callable[[PlanId, UUID], ReserveOperationResult]
    start_undo_plan: Callable[[CreateUndoPlanRequest, UUID], ReserveOperationResult]


@dataclass(frozen=True, slots=True)
class ApiRouteContext:
    """Concrete collaborators used by the renewed API routes."""

    csrf_token: str
    get_bootstrap: Callable[[], BootstrapResult]
    plans: PlansRouteContext | None = None
    tracks: TracksRouteContext | None = None
    libraries: LibrariesRouteContext | None = None
    history: HistoryRouteContext | None = None
    check: CheckRouteContext | None = None
    settings: SettingsRouteContext | None = None
    operations: OperationsRouteContext | None = None
    start_runtime: Callable[[], None] | None = None
    close_runtime: Callable[[], None] | None = None


def get_api_route_context(request: Request) -> ApiRouteContext:
    """Return the context installed by the production application factory."""
    app = cast("FastAPI", request.scope["app"])
    return cast("ApiRouteContext", app.state.api_route_context)


type ApiContext = Annotated[ApiRouteContext, Depends(get_api_route_context)]
