"""
Summary: Resolves Web route dependencies at request time.
Why: Lets production and schema-only apps register exactly the same router without I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, cast

from fastapi import Depends, Request

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

    from omym2.domain.models.file_event import FileEvent
    from omym2.domain.models.plan import Plan
    from omym2.domain.models.plan_action import PlanAction
    from omym2.domain.models.run import Run
    from omym2.domain.models.track import Track
    from omym2.features.bootstrap.dto import BootstrapResult
    from omym2.features.check.dto import (
        CheckIssueFacetsRequest,
        CheckIssueFacetsResult,
        GroupCheckIssuesRequest,
        ListCheckIssuesRequest,
        ListCheckIssuesResult,
    )
    from omym2.features.common_ports import CheckIssueGroup
    from omym2.features.history.dto import (
        FileEventStatusFacetsRequest,
        FileEventStatusFacetsResult,
        GetRunHeaderRequest,
        GroupRunEventsRequest,
        ListRunEventsRequest,
        ListRunsRequest,
        RunDetailResult,
        RunStatusFacetsRequest,
        RunStatusFacetsResult,
    )
    from omym2.features.libraries.dto import InspectLibrariesRequest, LibraryInspection
    from omym2.features.plans.dto import (
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
    from omym2.features.tracks.dto import (
        GetTrackRequest,
        GroupTracksRequest,
        ListTracksRequest,
        TrackStatusFacetsRequest,
        TrackStatusFacetsResult,
    )
    from omym2.shared.ids import PlanId
    from omym2.shared.pagination import GroupCount, Page


@dataclass(frozen=True, slots=True)
class PlansRouteContext:
    """Read-only Plan query handlers resolved by the platform composition root."""

    list_plans: Callable[[ListPlansRequest], Page[Plan]]
    get_plan_header: Callable[[GetPlanHeaderRequest], Plan]
    get_plan_action_summaries: Callable[[GetPlanActionSummariesRequest], dict[PlanId, PlanActionSummary]]
    get_plan_capabilities: Callable[[GetPlanCapabilitiesRequest], PlanCapabilitiesResult]
    list_plan_actions: Callable[[ListPlanActionsRequest], Page[PlanAction]]
    get_plan_action_facets: Callable[[PlanActionFacetsRequest], PlanActionFacetsResult]
    group_plan_actions: Callable[[GroupPlanActionsRequest], Page[PlanActionGroup]]


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
    """Read-only Run and FileEvent handlers resolved by the platform composition root."""

    list_runs: Callable[[ListRunsRequest], Page[Run]]
    get_run_detail: Callable[[GetRunHeaderRequest], RunDetailResult]
    get_run_status_facets: Callable[[RunStatusFacetsRequest], RunStatusFacetsResult]
    list_run_events: Callable[[ListRunEventsRequest], Page[FileEvent]]
    get_file_event_status_facets: Callable[[FileEventStatusFacetsRequest], FileEventStatusFacetsResult]
    group_run_events: Callable[[GroupRunEventsRequest], Page[GroupCount]]


@dataclass(frozen=True, slots=True)
class CheckRouteContext:
    """Read-only persisted Check handlers resolved by the platform composition root."""

    list_check_issues: Callable[[ListCheckIssuesRequest], ListCheckIssuesResult]
    get_check_issue_facets: Callable[[CheckIssueFacetsRequest], CheckIssueFacetsResult]
    group_check_issues: Callable[[GroupCheckIssuesRequest], Page[CheckIssueGroup]]


@dataclass(frozen=True, slots=True)
class ApiRouteContext:
    """Concrete collaborators used by the renewed read-only API routes."""

    csrf_token: str
    get_bootstrap: Callable[[], BootstrapResult]
    plans: PlansRouteContext | None = None
    tracks: TracksRouteContext | None = None
    libraries: LibrariesRouteContext | None = None
    history: HistoryRouteContext | None = None
    check: CheckRouteContext | None = None


def get_api_route_context(request: Request) -> ApiRouteContext:
    """Return the context installed by the production application factory."""
    app = cast("FastAPI", request.scope["app"])
    return cast("ApiRouteContext", app.state.api_route_context)


type ApiContext = Annotated[ApiRouteContext, Depends(get_api_route_context)]
