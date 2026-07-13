"""
Summary: Composes the renewed Web Bootstrap API and packaged SPA.
Why: Keeps concrete Config and SQLite adapters out of inbound Web modules.
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from omym2.adapters.db.sqlite.library_snapshot_reader import SQLiteLibrarySnapshotReader
from omym2.adapters.web.app import create_web_app
from omym2.adapters.web.routes.api_context import (
    ApiRouteContext,
    CheckRouteContext,
    HistoryRouteContext,
    LibrariesRouteContext,
    PlansRouteContext,
    TracksRouteContext,
)
from omym2.config import WEB_CSRF_TOKEN_BYTES
from omym2.features.bootstrap.ports import BootstrapPorts
from omym2.features.bootstrap.usecases.get_bootstrap import GetBootstrapUseCase
from omym2.features.check.usecases.get_check_issue_facets import GetCheckIssueFacetsUseCase
from omym2.features.check.usecases.group_check_issues import GroupCheckIssuesUseCase
from omym2.features.check.usecases.list_check_issues import ListCheckIssuesUseCase
from omym2.features.history.usecases.get_file_event_status_facets import GetFileEventStatusFacetsUseCase
from omym2.features.history.usecases.get_run_detail import GetRunDetailUseCase
from omym2.features.history.usecases.get_run_status_facets import GetRunStatusFacetsUseCase
from omym2.features.history.usecases.group_run_events import GroupRunEventsUseCase
from omym2.features.history.usecases.list_run_events import ListRunEventsUseCase
from omym2.features.history.usecases.list_runs import ListRunsUseCase
from omym2.features.libraries.usecases.inspect_libraries import InspectLibrariesUseCase
from omym2.features.plans.usecases.get_plan_action_facets import GetPlanActionFacetsUseCase
from omym2.features.plans.usecases.get_plan_action_summaries import GetPlanActionSummariesUseCase
from omym2.features.plans.usecases.get_plan_capabilities import GetPlanCapabilitiesUseCase
from omym2.features.plans.usecases.get_plan_header import GetPlanHeaderUseCase
from omym2.features.plans.usecases.group_plan_actions import GroupPlanActionsUseCase
from omym2.features.plans.usecases.list_plan_actions import ListPlanActionsUseCase
from omym2.features.plans.usecases.list_plans import ListPlansUseCase
from omym2.features.tracks.usecases.get_track import GetTrackUseCase
from omym2.features.tracks.usecases.get_track_status_facets import GetTrackStatusFacetsUseCase
from omym2.features.tracks.usecases.group_tracks import GroupTracksUseCase
from omym2.features.tracks.usecases.list_tracks import ListTracksUseCase
from omym2.platform.feature_composition import (
    build_check_query_ports,
    build_history_ports,
    build_library_inspection_ports,
    build_plan_query_ports,
    build_tracks_ports,
)
from omym2.platform.runtime_context import runtime_context_for

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from fastapi import FastAPI


def build_api_route_context(config_path: Path | None = None, database_path: Path | None = None) -> ApiRouteContext:
    """Build Bootstrap dependencies from one shared RuntimeContext."""
    runtime = runtime_context_for(config_path, database_path)
    usecase = GetBootstrapUseCase(
        BootstrapPorts(
            config_snapshot_reader=runtime.config_store,
            library_snapshot_reader=SQLiteLibrarySnapshotReader(runtime.database_file),
        )
    )
    return ApiRouteContext(
        csrf_token=secrets.token_urlsafe(WEB_CSRF_TOKEN_BYTES),
        get_bootstrap=usecase.execute,
        plans=PlansRouteContext(
            list_plans=lambda request: ListPlansUseCase(build_plan_query_ports(runtime)).execute(request),
            get_plan_header=lambda request: GetPlanHeaderUseCase(build_plan_query_ports(runtime)).execute(request),
            get_plan_action_summaries=lambda request: GetPlanActionSummariesUseCase(
                build_plan_query_ports(runtime)
            ).execute(request),
            get_plan_capabilities=lambda request: GetPlanCapabilitiesUseCase(build_plan_query_ports(runtime)).execute(
                request
            ),
            list_plan_actions=lambda request: ListPlanActionsUseCase(build_plan_query_ports(runtime)).execute(request),
            get_plan_action_facets=lambda request: GetPlanActionFacetsUseCase(build_plan_query_ports(runtime)).execute(
                request
            ),
            group_plan_actions=lambda request: GroupPlanActionsUseCase(build_plan_query_ports(runtime)).execute(
                request
            ),
        ),
        tracks=TracksRouteContext(
            list_tracks=lambda request: ListTracksUseCase(build_tracks_ports(runtime)).execute(request),
            get_track=lambda request: GetTrackUseCase(build_tracks_ports(runtime)).execute(request),
            get_track_status_facets=lambda request: GetTrackStatusFacetsUseCase(build_tracks_ports(runtime)).execute(
                request
            ),
            group_tracks=lambda request: GroupTracksUseCase(build_tracks_ports(runtime)).execute(request),
        ),
        libraries=LibrariesRouteContext(
            inspect_libraries=lambda request: InspectLibrariesUseCase(build_library_inspection_ports(runtime)).execute(
                request
            ),
        ),
        history=HistoryRouteContext(
            list_runs=lambda request: ListRunsUseCase(build_history_ports(runtime)).execute(request),
            get_run_detail=lambda request: GetRunDetailUseCase(build_history_ports(runtime)).execute(request),
            get_run_status_facets=lambda request: GetRunStatusFacetsUseCase(build_history_ports(runtime)).execute(
                request
            ),
            list_run_events=lambda request: ListRunEventsUseCase(build_history_ports(runtime)).execute(request),
            get_file_event_status_facets=lambda request: GetFileEventStatusFacetsUseCase(
                build_history_ports(runtime)
            ).execute(request),
            group_run_events=lambda request: GroupRunEventsUseCase(build_history_ports(runtime)).execute(request),
        ),
        check=CheckRouteContext(
            list_check_issues=lambda request: ListCheckIssuesUseCase(build_check_query_ports(runtime)).execute(request),
            get_check_issue_facets=lambda request: GetCheckIssueFacetsUseCase(build_check_query_ports(runtime)).execute(
                request
            ),
            group_check_issues=lambda request: GroupCheckIssuesUseCase(build_check_query_ports(runtime)).execute(
                request
            ),
        ),
    )


def build_web_app(
    config_path: Path | None = None,
    database_path: Path | None = None,
    static_dist_path: Path | None = None,
    *,
    allowed_hosts: Sequence[str] | None = None,
) -> FastAPI:
    """Build the local Web app from optional Config, database, and static paths."""
    context = build_api_route_context(config_path, database_path)
    if allowed_hosts is None:
        return create_web_app(context, static_dist_path)
    return create_web_app(context, static_dist_path, allowed_hosts=allowed_hosts)
