"""
Summary: Composes the bundled Web Bootstrap API and packaged SPA.
Why: Keeps concrete Config and SQLite adapters out of inbound Web modules.
"""

from __future__ import annotations

import secrets
from dataclasses import replace
from typing import TYPE_CHECKING

from omym2.adapters.db.sqlite.library_snapshot_reader import SQLiteLibrarySnapshotReader
from omym2.adapters.web.app import create_web_app
from omym2.adapters.web.routes.api_context import (
    ApiRouteContext,
    CheckRouteContext,
    HistoryRouteContext,
    LibrariesRouteContext,
    OperationsRouteContext,
    PlansRouteContext,
    SettingsRouteContext,
    TracksRouteContext,
)
from omym2.config import WEB_CSRF_TOKEN_BYTES
from omym2.domain.models.operation import (
    CheckCompletedResult,
    OperationKind,
    PlanCreatedResult,
    RegisteredWithoutPlanResult,
    RunCompletedResult,
)
from omym2.domain.models.plan import PlanStatus
from omym2.features.add.usecases.create_add_plan import CreateAddPlanUseCase
from omym2.features.apply.dto import ApplyOptions, ApplyPlanRequest
from omym2.features.apply.usecases.apply_plan import ApplyPlanUseCase
from omym2.features.artist_ids.usecases.generate_artist_id_draft import GenerateArtistIdDraftUseCase
from omym2.features.bootstrap.ports import BootstrapPorts
from omym2.features.bootstrap.usecases.get_bootstrap import GetBootstrapUseCase
from omym2.features.check.usecases.check_library import CheckLibraryUseCase
from omym2.features.check.usecases.get_check_issue_facets import GetCheckIssueFacetsUseCase
from omym2.features.check.usecases.group_check_issues import GroupCheckIssuesUseCase
from omym2.features.check.usecases.list_check_issues import ListCheckIssuesUseCase
from omym2.features.common_ports import ExclusiveOperationBusyError
from omym2.features.history.usecases.get_file_event_status_facets import GetFileEventStatusFacetsUseCase
from omym2.features.history.usecases.get_run_detail import GetRunDetailUseCase
from omym2.features.history.usecases.get_run_status_facets import GetRunStatusFacetsUseCase
from omym2.features.history.usecases.group_run_events import GroupRunEventsUseCase
from omym2.features.history.usecases.list_run_events import ListRunEventsUseCase
from omym2.features.history.usecases.list_runs import ListRunsUseCase
from omym2.features.libraries.usecases.inspect_libraries import InspectLibrariesUseCase
from omym2.features.organize.usecases.create_organize_plan import CreateOrganizePlanUseCase
from omym2.features.plans.usecases.cancel_plan import (
    PLAN_NOT_READY_MESSAGE,
    CancelPlanUseCase,
    PlanCannotBeCancelledError,
)
from omym2.features.plans.usecases.get_plan_action_facets import GetPlanActionFacetsUseCase
from omym2.features.plans.usecases.get_plan_action_summaries import GetPlanActionSummariesUseCase
from omym2.features.plans.usecases.get_plan_capabilities import GetPlanCapabilitiesUseCase
from omym2.features.plans.usecases.get_plan_header import GetPlanHeaderUseCase
from omym2.features.plans.usecases.group_plan_actions import GroupPlanActionsUseCase
from omym2.features.plans.usecases.list_plan_actions import ListPlanActionsUseCase
from omym2.features.plans.usecases.list_plans import ListPlansUseCase
from omym2.features.refresh.usecases.create_refresh_plan import CreateRefreshPlanUseCase
from omym2.features.settings.usecases.get_settings_edit import GetSettingsEditUseCase
from omym2.features.settings.usecases.preview_path_policy import PreviewPathPolicyUseCase
from omym2.features.settings.usecases.save_settings_candidate import SaveSettingsCandidateUseCase
from omym2.features.settings.usecases.validate_settings_candidate import ValidateSettingsCandidateUseCase
from omym2.features.tracks.usecases.get_track import GetTrackUseCase
from omym2.features.tracks.usecases.get_track_status_facets import GetTrackStatusFacetsUseCase
from omym2.features.tracks.usecases.group_tracks import GroupTracksUseCase
from omym2.features.tracks.usecases.list_tracks import ListTracksUseCase
from omym2.features.undo.usecases.create_undo_plan import CreateUndoPlanUseCase
from omym2.platform.artist_ids_composition import web_artist_language_detector, web_artist_name_resolver
from omym2.platform.cli_path_normalization import normalize_cli_path
from omym2.platform.feature_composition import (
    build_apply_plan_ports,
    build_check_library_ports,
    build_check_query_ports,
    build_create_add_plan_ports,
    build_create_organize_plan_ports,
    build_create_refresh_plan_ports,
    build_create_undo_plan_ports,
    build_history_ports,
    build_library_inspection_ports,
    build_plan_query_ports,
    build_settings_ports,
    build_tracks_ports,
    build_uow,
)
from omym2.platform.operation_composition import OperationRuntime
from omym2.platform.runtime_context import runtime_context_for

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path
    from uuid import UUID

    from fastapi import FastAPI

    from omym2.domain.models.plan import Plan
    from omym2.features.add.dto import CreateAddPlanRequest
    from omym2.features.check.dto import CheckLibraryRequest
    from omym2.features.operations.dto import ReserveOperationResult
    from omym2.features.organize.dto import CreateOrganizePlanRequest, OrganizeLibraryResult
    from omym2.features.plans.dto import CancelPlanRequest
    from omym2.features.refresh.dto import CreateRefreshPlanRequest
    from omym2.features.settings.dto import SaveSettingsRequest, SettingsCandidateResult
    from omym2.features.undo.dto import CreateUndoPlanRequest
    from omym2.platform.runtime_context import RuntimeContext
    from omym2.shared.ids import OperationId, PlanId


def build_api_route_context(config_path: Path | None = None, database_path: Path | None = None) -> ApiRouteContext:
    """Build Bootstrap dependencies from one shared RuntimeContext."""
    runtime = runtime_context_for(config_path, database_path)
    operation_runtime = OperationRuntime(runtime)
    state_snapshot_reader = SQLiteLibrarySnapshotReader(runtime.database_file)
    usecase = GetBootstrapUseCase(
        BootstrapPorts(
            config_snapshot_reader=runtime.config_store,
            library_snapshot_reader=state_snapshot_reader,
            operation_snapshot_reader=state_snapshot_reader,
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
            cancel_plan=lambda request: _cancel_plan(runtime, operation_runtime, request),
            active_operation_id=operation_runtime.active_operation_id_for_plan,
            conflicting_operation_id=operation_runtime.active_operation_id,
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
            active_operation_id=operation_runtime.active_operation_id_for_run,
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
        settings=SettingsRouteContext(
            get_settings=GetSettingsEditUseCase(build_settings_ports(runtime)).execute,
            validate_settings=ValidateSettingsCandidateUseCase(build_settings_ports(runtime)).execute,
            preview_path_policy=PreviewPathPolicyUseCase().execute,
            save_settings=lambda request: _save_settings(runtime, operation_runtime, request),
            generate_artist_id_draft=GenerateArtistIdDraftUseCase(
                language_detector=web_artist_language_detector(),
                artist_resolver=web_artist_name_resolver(),
            ).execute,
        ),
        operations=OperationsRouteContext(
            get_operation=operation_runtime.get,
            active_operation_id=operation_runtime.active_operation_id,
            start_add_plan=lambda request, idempotency_key: _start_add_plan(
                runtime, operation_runtime, request, idempotency_key
            ),
            start_organize_plan=lambda request, idempotency_key: _start_organize_plan(
                runtime, operation_runtime, request, idempotency_key
            ),
            start_refresh_plan=lambda request, idempotency_key: _start_refresh_plan(
                runtime, operation_runtime, request, idempotency_key
            ),
            start_check=lambda request, idempotency_key: _start_check(
                runtime, operation_runtime, request, idempotency_key
            ),
            start_apply_plan=lambda plan_id, idempotency_key: _start_apply_plan(
                runtime, operation_runtime, plan_id, idempotency_key
            ),
            start_undo_plan=lambda request, idempotency_key: _start_undo_plan(
                runtime, operation_runtime, request, idempotency_key
            ),
        ),
        start_runtime=operation_runtime.start,
        close_runtime=operation_runtime.close,
    )


def _save_settings(
    runtime: RuntimeContext,
    operations: OperationRuntime,
    request: SaveSettingsRequest,
) -> SettingsCandidateResult:
    return operations.execute_exclusive(
        "save_settings",
        lambda: SaveSettingsCandidateUseCase(build_settings_ports(runtime)).execute(request),
    )


def _cancel_plan(
    runtime: RuntimeContext,
    operations: OperationRuntime,
    request: CancelPlanRequest,
) -> Plan:
    try:
        return operations.execute_exclusive(
            "cancel_plan",
            lambda: CancelPlanUseCase(build_plan_query_ports(runtime)).execute(request),
        )
    except ExclusiveOperationBusyError:
        with build_uow(runtime) as uow:
            plan = uow.plans.get(request.plan_id)
        if plan is not None and plan.status is not PlanStatus.READY:
            raise PlanCannotBeCancelledError(PLAN_NOT_READY_MESSAGE) from None
        raise


def _start_apply_plan(
    runtime: RuntimeContext,
    operations: OperationRuntime,
    plan_id: PlanId,
    idempotency_key: UUID,
) -> ReserveOperationResult:
    return operations.accept_apply(
        plan_id=plan_id,
        idempotency_key=idempotency_key,
        canonical_request={"plan_id": plan_id},
        work=lambda operation_id: _run_apply_plan(runtime, operations, plan_id, operation_id),
    )


def _run_apply_plan(
    runtime: RuntimeContext,
    operations: OperationRuntime,
    plan_id: PlanId,
    operation_id: OperationId,
) -> RunCompletedResult:
    operation = operations.get(operation_id)
    if operation.run_id is None:
        raise RuntimeError
    run = ApplyPlanUseCase(build_apply_plan_ports(runtime)).execute(
        ApplyPlanRequest(
            plan_id=plan_id,
            options=ApplyOptions(yes=True),
            run_id=operation.run_id,
            operation_id=operation_id,
        )
    )
    return RunCompletedResult(run.run_id)


def _start_undo_plan(
    runtime: RuntimeContext,
    operations: OperationRuntime,
    request: CreateUndoPlanRequest,
    idempotency_key: UUID,
) -> ReserveOperationResult:
    return operations.accept(
        kind=OperationKind.UNDO_PLAN,
        idempotency_key=idempotency_key,
        canonical_request={"run_id": request.run_id},
        run_id=request.run_id,
        preflight=lambda: CreateUndoPlanUseCase(build_create_undo_plan_ports(runtime)).validate(request),
        work=lambda operation_id: _run_undo_plan(runtime, request, operation_id),
    )


def _run_undo_plan(
    runtime: RuntimeContext,
    request: CreateUndoPlanRequest,
    operation_id: OperationId,
) -> PlanCreatedResult:
    plan = CreateUndoPlanUseCase(build_create_undo_plan_ports(runtime)).execute(
        replace(request, operation_id=operation_id)
    )
    return PlanCreatedResult(plan.plan_id)


def _start_add_plan(
    runtime: RuntimeContext,
    operations: OperationRuntime,
    request: CreateAddPlanRequest,
    idempotency_key: UUID,
) -> ReserveOperationResult:
    normalized = replace(
        request,
        source_path=None if request.source_path is None else normalize_cli_path(request.source_path),
    )
    return operations.accept(
        kind=OperationKind.ADD_PLAN,
        idempotency_key=idempotency_key,
        canonical_request={
            "library_id": normalized.library_id,
            "source_path": normalized.source_path,
        },
        library_id=normalized.library_id,
        work=lambda operation_id: _run_add_plan(runtime, normalized, operation_id),
    )


def _run_add_plan(
    runtime: RuntimeContext,
    request: CreateAddPlanRequest,
    operation_id: OperationId,
) -> PlanCreatedResult:
    plan = CreateAddPlanUseCase(build_create_add_plan_ports(runtime)).execute(
        replace(request, operation_id=operation_id)
    )
    return PlanCreatedResult(plan.plan_id)


def _start_organize_plan(
    runtime: RuntimeContext,
    operations: OperationRuntime,
    request: CreateOrganizePlanRequest,
    idempotency_key: UUID,
) -> ReserveOperationResult:
    normalized = replace(
        request,
        library_root=None if request.library_root is None else normalize_cli_path(request.library_root),
    )
    return operations.accept(
        kind=OperationKind.ORGANIZE_PLAN,
        idempotency_key=idempotency_key,
        canonical_request={"library_root": normalized.library_root},
        work=lambda operation_id: _run_organize_plan(runtime, normalized, operation_id),
    )


def _run_organize_plan(
    runtime: RuntimeContext,
    request: CreateOrganizePlanRequest,
    operation_id: OperationId,
) -> PlanCreatedResult | RegisteredWithoutPlanResult:
    result = CreateOrganizePlanUseCase(build_create_organize_plan_ports(runtime)).execute(
        replace(request, operation_id=operation_id)
    )
    return _organize_result(result)


def _organize_result(result: OrganizeLibraryResult) -> PlanCreatedResult | RegisteredWithoutPlanResult:
    if result.plan is not None:
        return PlanCreatedResult(result.plan.plan_id)
    return RegisteredWithoutPlanResult(result.library.library_id, result.track_count)


def _start_refresh_plan(
    runtime: RuntimeContext,
    operations: OperationRuntime,
    request: CreateRefreshPlanRequest,
    idempotency_key: UUID,
) -> ReserveOperationResult:
    normalized = replace(
        request,
        target_path=None if request.target_path is None else normalize_cli_path(request.target_path),
    )
    return operations.accept(
        kind=OperationKind.REFRESH_PLAN,
        idempotency_key=idempotency_key,
        canonical_request={
            "include_all": normalized.include_all,
            "library_id": normalized.library_id,
            "target_kind": normalized.target_kind,
            "target_path": normalized.target_path,
            "track_id": normalized.track_id,
        },
        library_id=normalized.library_id,
        work=lambda operation_id: _run_refresh_plan(runtime, normalized, operation_id),
    )


def _run_refresh_plan(
    runtime: RuntimeContext,
    request: CreateRefreshPlanRequest,
    operation_id: OperationId,
) -> PlanCreatedResult:
    plan = CreateRefreshPlanUseCase(build_create_refresh_plan_ports(runtime)).execute(
        replace(request, operation_id=operation_id)
    )
    return PlanCreatedResult(plan.plan_id)


def _start_check(
    runtime: RuntimeContext,
    operations: OperationRuntime,
    request: CheckLibraryRequest,
    idempotency_key: UUID,
) -> ReserveOperationResult:
    return operations.accept(
        kind=OperationKind.CHECK,
        idempotency_key=idempotency_key,
        canonical_request={"library_id": request.library_id},
        library_id=request.library_id,
        work=lambda operation_id: _run_check(runtime, request, operation_id),
    )


def _run_check(
    runtime: RuntimeContext,
    request: CheckLibraryRequest,
    operation_id: OperationId,
) -> CheckCompletedResult:
    result = CheckLibraryUseCase(build_check_library_ports(runtime)).execute(
        replace(request, operation_id=operation_id)
    )
    return CheckCompletedResult(result.check_run_ids, len(result.issues))


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
