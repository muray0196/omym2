"""
Summary: Defines local Web JSON API routes.
Why: Lets the React UI use feature usecases without server-rendered templates.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from json import JSONDecodeError
from secrets import compare_digest
from typing import TYPE_CHECKING, cast

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from omym2.adapters.web.routes.api_serializers import (
    serialize_app_config,
    serialize_artist_id_generation,
    serialize_check_issue,
    serialize_facet_value,
    serialize_group_count,
    serialize_organize_registration,
    serialize_page_info,
    serialize_path_preview,
    serialize_plan_detail,
    serialize_plan_detail_parts,
    serialize_plan_row,
    serialize_run_detail,
    serialize_run_summary,
    serialize_settings_change,
    serialize_settings_choices,
    serialize_track_summary,
    serialize_validation_result,
)
from omym2.adapters.web.schemas.settings_changes import describe_config_changes
from omym2.adapters.web.schemas.settings_json import parse_path_preview_json, parse_settings_json
from omym2.config import (
    PATH_POLICY_PREVIEW_ALBUM,
    PATH_POLICY_PREVIEW_ALBUM_ARTIST,
    PATH_POLICY_PREVIEW_ARTIST,
    PATH_POLICY_PREVIEW_DISC_NUMBER,
    PATH_POLICY_PREVIEW_DISC_TOTAL,
    PATH_POLICY_PREVIEW_FILE_EXTENSION,
    PATH_POLICY_PREVIEW_TITLE,
    PATH_POLICY_PREVIEW_TRACK_NUMBER,
    PATH_POLICY_PREVIEW_YEAR,
    WEB_API_ARTIST_IDS_GENERATE_ROUTE,
    WEB_API_CHECK_ROUTE,
    WEB_API_HISTORY_ROUTE,
    WEB_API_PLAN_ADD_ROUTE,
    WEB_API_PLAN_DETAIL_ROUTE,
    WEB_API_PLAN_ORGANIZE_ROUTE,
    WEB_API_PLAN_REFRESH_ROUTE,
    WEB_API_PLANS_ROUTE,
    WEB_API_RUN_DETAIL_ROUTE,
    WEB_API_SETTINGS_PREVIEW_ROUTE,
    WEB_API_SETTINGS_ROUTE,
    WEB_API_SETTINGS_SAVE_ROUTE,
    WEB_API_SETTINGS_VALIDATE_ROUTE,
    WEB_API_TRACKS_FACETS_ROUTE,
    WEB_API_TRACKS_GROUPS_ROUTE,
    WEB_API_TRACKS_ROUTE,
    WEB_CSRF_HEADER_NAME,
)
from omym2.domain.models.app_config import AppConfig
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus
from omym2.domain.models.track import TrackGrouping, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.features.add.dto import CreateAddPlanRequest
from omym2.features.add.usecases.create_add_plan import (
    AddLibrarySelectionError,
    AddSourceSelectionError,
    CreateAddPlanUseCase,
)
from omym2.features.artist_ids.dto import GenerateArtistIdsRequest
from omym2.features.artist_ids.usecases.generate_artist_ids import GenerateArtistIdsUseCase
from omym2.features.check.dto import CheckLibraryRequest
from omym2.features.check.usecases.check_library import CheckLibraryError, CheckLibraryUseCase
from omym2.features.common_ports import ConfigStoreValidationError, MetadataReadError
from omym2.features.history.dto import GetRunDetailRequest, ListRunsRequest
from omym2.features.history.usecases.get_run_detail import GetRunDetailUseCase, RunNotFoundError
from omym2.features.history.usecases.list_runs import ListRunsUseCase
from omym2.features.organize.dto import CreateOrganizePlanRequest, OrganizeLibraryResult
from omym2.features.organize.usecases.create_organize_plan import (
    CreateOrganizePlanUseCase,
    OrganizeLibrarySelectionError,
)
from omym2.features.plans.dto import GetPlanDetailRequest, ListPlansRequest
from omym2.features.plans.usecases.get_plan_detail import GetPlanDetailUseCase, PlanNotFoundError
from omym2.features.plans.usecases.list_plans import ListPlansUseCase
from omym2.features.refresh.dto import CreateRefreshPlanRequest
from omym2.features.refresh.usecases.create_refresh_plan import (
    CreateRefreshPlanUseCase,
    RefreshLibrarySelectionError,
    RefreshTargetSelectionError,
)
from omym2.features.settings.dto import (
    PathPolicyPreviewRequest,
    PathPolicyPreviewResult,
    SaveSettingsRequest,
    ValidateSettingsResult,
)
from omym2.features.settings.usecases.load_settings import LoadSettingsUseCase
from omym2.features.settings.usecases.preview_path_policy import PreviewPathPolicyUseCase
from omym2.features.settings.usecases.save_settings import SaveSettingsUseCase
from omym2.features.settings.usecases.validate_settings import ValidateSettingsUseCase
from omym2.features.tracks.dto import GroupTracksRequest, ListTracksRequest, TrackStatusFacetsRequest
from omym2.features.tracks.usecases.get_track_status_facets import GetTrackStatusFacetsUseCase
from omym2.features.tracks.usecases.group_tracks import GroupTracksUseCase
from omym2.features.tracks.usecases.list_tracks import ListTracksUseCase
from omym2.shared.ids import LibraryId, PlanId, RunId, parse_uuid
from omym2.shared.pagination import INVALID_CURSOR_MESSAGE, CursorDecodeError, PageRequest, clamp_limit, decode_cursor

if TYPE_CHECKING:
    from omym2.features.add.ports import CreateAddPlanPorts
    from omym2.features.artist_ids.ports import ArtistLanguageDetector, ArtistNameResolver
    from omym2.features.check.ports import CheckLibraryPorts
    from omym2.features.history.ports import HistoryPorts
    from omym2.features.organize.ports import CreateOrganizePlanPorts
    from omym2.features.plans.ports import PlanQueryPorts
    from omym2.features.refresh.ports import CreateRefreshPlanPorts
    from omym2.features.settings.ports import SettingsPorts
    from omym2.features.tracks.ports import TracksPorts

ERROR_STATUS_CODE = 400
FORBIDDEN_STATUS_CODE = 403
NOT_FOUND_STATUS_CODE = 404
SERVER_ERROR_STATUS_CODE = 500
SUCCESS_STATUS_CODE = 200
INVALID_JSON_ERROR_MESSAGE = "Request body must be valid JSON."
REQUEST_BODY_ERROR = "Request body must be a JSON object."
ARTIST_IDS_FIELD_ERROR = "Request body must contain an artist_names array."
RUN_NOT_FOUND_MESSAGE = "Run was not found."
PLAN_NOT_FOUND_MESSAGE = "Plan was not found."
SAVE_CSRF_ERROR_MESSAGE = "Settings save request failed CSRF validation."
PLAN_CSRF_ERROR_MESSAGE = "Plan creation request failed CSRF validation."
INSPECTION_ERROR_PREFIX = "Inspection failed"
PLAN_CREATION_ERROR_PREFIX = "Plan creation failed"
PLAN_PATH_NOT_DIRECTORY_MESSAGE = "Plan path must be a directory"
PLAN_PATH_NOT_FOUND_MESSAGE = "Plan path was not found"

type CheckPortsFactory = Callable[[], "CheckLibraryPorts"]
type HistoryPortsFactory = Callable[[], "HistoryPorts"]
type PlanQueryPortsFactory = Callable[[], "PlanQueryPorts"]
type AddPlanPortsFactory = Callable[[], "CreateAddPlanPorts"]
type OrganizePlanPortsFactory = Callable[[], "CreateOrganizePlanPorts"]
type RefreshPlanPortsFactory = Callable[[], "CreateRefreshPlanPorts"]
type TracksPortsFactory = Callable[[], "TracksPorts"]


@dataclass(frozen=True, slots=True)
class ApiRouteContext:
    """Concrete dependencies for JSON API routes."""

    check_ports_factory: CheckPortsFactory
    csrf_token: str
    history_ports_factory: HistoryPortsFactory
    plan_query_ports_factory: PlanQueryPortsFactory
    add_plan_ports_factory: AddPlanPortsFactory
    organize_plan_ports_factory: OrganizePlanPortsFactory
    refresh_plan_ports_factory: RefreshPlanPortsFactory
    settings_ports: SettingsPorts
    tracks_ports_factory: TracksPortsFactory
    artist_id_language_detector: ArtistLanguageDetector
    artist_id_name_resolver: ArtistNameResolver


def create_api_router(context: ApiRouteContext) -> APIRouter:
    """Create JSON API routes bound to concrete dependencies."""
    router = APIRouter()
    _register_settings_routes(router, context)
    _register_history_routes(router, context)
    _register_plan_routes(router, context)
    _register_inspection_routes(router, context)
    return router


def _register_settings_routes(router: APIRouter, context: ApiRouteContext) -> None:
    def get_settings() -> JSONResponse:
        return _get_settings(context)

    async def validate_settings(request: Request) -> JSONResponse:
        return await _validate_settings(context, request)

    async def preview_settings(request: Request) -> JSONResponse:
        return await _preview_settings(request)

    async def save_settings(request: Request) -> JSONResponse:
        return await _save_settings(context, request)

    async def generate_artist_ids(request: Request) -> JSONResponse:
        return await _generate_artist_ids(context, request)

    router.add_api_route(WEB_API_SETTINGS_ROUTE, get_settings, methods=["GET"])
    router.add_api_route(WEB_API_SETTINGS_PREVIEW_ROUTE, preview_settings, methods=["POST"])
    router.add_api_route(WEB_API_SETTINGS_VALIDATE_ROUTE, validate_settings, methods=["POST"])
    router.add_api_route(WEB_API_SETTINGS_SAVE_ROUTE, save_settings, methods=["POST"])
    router.add_api_route(WEB_API_ARTIST_IDS_GENERATE_ROUTE, generate_artist_ids, methods=["POST"])


def _register_history_routes(router: APIRouter, context: ApiRouteContext) -> None:
    def get_history() -> JSONResponse:
        return _get_history(context)

    def get_run_detail(run_id: str) -> JSONResponse:
        return _get_run_detail(context, run_id)

    router.add_api_route(WEB_API_HISTORY_ROUTE, get_history, methods=["GET"])
    router.add_api_route(WEB_API_RUN_DETAIL_ROUTE, get_run_detail, methods=["GET"])


def _register_plan_routes(router: APIRouter, context: ApiRouteContext) -> None:
    def get_plans(request: Request) -> JSONResponse:
        return _get_plans(context, request)

    def get_plan_detail(plan_id: str, request: Request) -> JSONResponse:
        return _get_plan_detail(context, plan_id, request)

    async def create_add_plan(request: Request) -> JSONResponse:
        return await _create_add_plan(context, request)

    async def create_organize_plan(request: Request) -> JSONResponse:
        return await _create_organize_plan(context, request)

    async def create_refresh_plan(request: Request) -> JSONResponse:
        return await _create_refresh_plan(context, request)

    router.add_api_route(WEB_API_PLANS_ROUTE, get_plans, methods=["GET"])
    router.add_api_route(WEB_API_PLAN_DETAIL_ROUTE, get_plan_detail, methods=["GET"])
    router.add_api_route(WEB_API_PLAN_ADD_ROUTE, create_add_plan, methods=["POST"])
    router.add_api_route(WEB_API_PLAN_ORGANIZE_ROUTE, create_organize_plan, methods=["POST"])
    router.add_api_route(WEB_API_PLAN_REFRESH_ROUTE, create_refresh_plan, methods=["POST"])


def _register_inspection_routes(router: APIRouter, context: ApiRouteContext) -> None:
    def get_check() -> JSONResponse:
        return _get_check(context)

    def get_tracks(request: Request) -> JSONResponse:
        return _get_tracks(context, request)

    def get_track_facets(request: Request) -> JSONResponse:
        return _get_track_facets(context, request)

    def get_track_groups(request: Request) -> JSONResponse:
        return _get_track_groups(context, request)

    router.add_api_route(WEB_API_CHECK_ROUTE, get_check, methods=["GET"])
    router.add_api_route(WEB_API_TRACKS_ROUTE, get_tracks, methods=["GET"])
    router.add_api_route(WEB_API_TRACKS_FACETS_ROUTE, get_track_facets, methods=["GET"])
    router.add_api_route(WEB_API_TRACKS_GROUPS_ROUTE, get_track_groups, methods=["GET"])


def _get_settings(context: ApiRouteContext) -> JSONResponse:
    current_config, load_errors = _load_current_config(context.settings_ports)
    validation_result = _validate_persisted_settings(context.settings_ports)
    preview_result = _preview_path_policy(current_config)
    return JSONResponse(
        {
            "config": serialize_app_config(current_config),
            "choices": serialize_settings_choices(),
            "validation": serialize_validation_result(validation_result),
            "preview": serialize_path_preview(preview_result),
            "errors": list(load_errors),
            "csrf_token": context.csrf_token,
        },
        status_code=SUCCESS_STATUS_CODE,
    )


async def _validate_settings(context: ApiRouteContext, request: Request) -> JSONResponse:
    payload, payload_errors = await _read_json_payload(request)
    if payload_errors:
        return _settings_validation_error(payload_errors)

    form_result = parse_settings_json(payload)
    if form_result.config is None:
        return _settings_validation_error(form_result.errors)

    current_config, load_errors = _load_current_config(context.settings_ports)
    proposed_config = form_result.config
    return JSONResponse(
        {
            "valid": True,
            "errors": list(load_errors),
            "changes": [
                serialize_settings_change(change) for change in describe_config_changes(current_config, proposed_config)
            ],
            "preview": serialize_path_preview(_preview_path_policy(proposed_config)),
        },
        status_code=SUCCESS_STATUS_CODE,
    )


async def _preview_settings(request: Request) -> JSONResponse:
    payload, payload_errors = await _read_json_payload(request)
    if payload_errors:
        return _settings_preview_error(payload_errors)

    preview_result = parse_path_preview_json(payload)
    if preview_result.config is None:
        return _settings_preview_error(preview_result.errors)
    if preview_result.errors:
        return _settings_preview_error(preview_result.errors)

    return JSONResponse(
        serialize_path_preview(
            _preview_path_policy(
                preview_result.config,
                metadata=preview_result.metadata,
                file_extension=preview_result.file_extension,
            )
        ),
        status_code=SUCCESS_STATUS_CODE,
    )


async def _save_settings(context: ApiRouteContext, request: Request) -> JSONResponse:
    if not _has_valid_csrf_token(context, request):
        return JSONResponse(
            {"saved": False, "errors": [SAVE_CSRF_ERROR_MESSAGE], "changes": []},
            status_code=FORBIDDEN_STATUS_CODE,
        )

    payload, payload_errors = await _read_json_payload(request)
    if payload_errors:
        return _settings_save_error(payload_errors)

    form_result = parse_settings_json(payload)
    if form_result.config is None:
        return _settings_save_error(form_result.errors)

    current_config, _load_errors = _load_current_config(context.settings_ports)
    proposed_config = form_result.config
    changes = describe_config_changes(current_config, proposed_config)
    try:
        SaveSettingsUseCase(context.settings_ports).execute(SaveSettingsRequest(config=proposed_config))
    except OSError as exc:
        return _settings_save_error((f"Config I/O error: {exc}",))

    validation_result = _validate_persisted_settings(context.settings_ports)
    return JSONResponse(
        {
            "saved": True,
            "errors": [],
            "changes": [serialize_settings_change(change) for change in changes],
            "config": serialize_app_config(proposed_config),
            "validation": serialize_validation_result(validation_result),
            "preview": serialize_path_preview(_preview_path_policy(proposed_config)),
        },
        status_code=SUCCESS_STATUS_CODE,
    )


async def _generate_artist_ids(context: ApiRouteContext, request: Request) -> JSONResponse:
    if not _has_valid_csrf_token(context, request):
        return JSONResponse(
            {"generated": False, "errors": [SAVE_CSRF_ERROR_MESSAGE], "entries": []},
            status_code=FORBIDDEN_STATUS_CODE,
        )

    payload, payload_errors = await _read_json_payload(request)
    if payload_errors:
        return _artist_ids_error(payload_errors)

    generation_request, request_errors = _artist_ids_request(payload)
    if request_errors:
        return _artist_ids_error(request_errors)

    try:
        result = GenerateArtistIdsUseCase(
            config_store=context.settings_ports.config_store,
            language_detector=context.artist_id_language_detector,
            artist_resolver=context.artist_id_name_resolver,
        ).execute(generation_request)
    except ConfigStoreValidationError as exc:
        return _artist_ids_error(exc.errors)
    except OSError as exc:
        return _artist_ids_error((f"Config I/O error: {exc}",))

    return JSONResponse(
        {"generated": True, "errors": [], **serialize_artist_id_generation(result)},
        status_code=SUCCESS_STATUS_CODE,
    )


def _get_history(context: ApiRouteContext) -> JSONResponse:
    try:
        runs = ListRunsUseCase(context.history_ports_factory()).execute(ListRunsRequest())
    except sqlite3.DatabaseError as exc:
        return JSONResponse(
            {"runs": [], "errors": list(_inspection_errors(exc))},
            status_code=SERVER_ERROR_STATUS_CODE,
        )

    return JSONResponse(
        {"runs": [serialize_run_summary(run) for run in runs], "errors": []},
        status_code=SUCCESS_STATUS_CODE,
    )


def _get_run_detail(context: ApiRouteContext, run_id: str) -> JSONResponse:
    parsed_run_id = _run_id_from_text(run_id)
    if parsed_run_id is None:
        return _run_detail_error(RUN_NOT_FOUND_MESSAGE)

    try:
        detail = GetRunDetailUseCase(context.history_ports_factory()).execute(GetRunDetailRequest(parsed_run_id))
    except RunNotFoundError:
        return _run_detail_error(RUN_NOT_FOUND_MESSAGE)
    except sqlite3.DatabaseError as exc:
        return JSONResponse(
            {"detail": None, "errors": list(_inspection_errors(exc))},
            status_code=SERVER_ERROR_STATUS_CODE,
        )

    return JSONResponse(
        {"detail": serialize_run_detail(detail.run, detail.file_events), "errors": []},
        status_code=SUCCESS_STATUS_CODE,
    )


def _get_plans(context: ApiRouteContext, request: Request) -> JSONResponse:
    status, status_errors = _plan_status_from_query(request.query_params.get("status"))
    plan_type, type_errors = _plan_type_from_query(request.query_params.get("type"))
    limit, limit_errors = _positive_int_from_query(request.query_params.get("limit"), field_name="limit")
    filter_errors = status_errors + type_errors + limit_errors
    if filter_errors:
        return JSONResponse({"plans": [], "errors": list(filter_errors)}, status_code=ERROR_STATUS_CODE)

    try:
        plans = ListPlansUseCase(context.plan_query_ports_factory()).execute(
            ListPlansRequest(status=status, plan_type=plan_type, limit=limit)
        )
    except sqlite3.DatabaseError as exc:
        return JSONResponse(
            {"plans": [], "errors": list(_inspection_errors(exc))},
            status_code=SERVER_ERROR_STATUS_CODE,
        )

    return JSONResponse(
        {"plans": [serialize_plan_row(plan) for plan in plans], "errors": []},
        status_code=SUCCESS_STATUS_CODE,
    )


def _get_plan_detail(context: ApiRouteContext, plan_id: str, request: Request) -> JSONResponse:
    parsed_plan_id = _plan_id_from_text(plan_id)
    if parsed_plan_id is None:
        return _plan_detail_error(PLAN_NOT_FOUND_MESSAGE)

    action_status, action_errors = _action_status_from_query(request.query_params.get("actions"))
    if action_errors:
        return JSONResponse({"detail": None, "errors": list(action_errors)}, status_code=ERROR_STATUS_CODE)

    try:
        detail = GetPlanDetailUseCase(context.plan_query_ports_factory()).execute(
            GetPlanDetailRequest(parsed_plan_id, action_status=action_status)
        )
    except PlanNotFoundError:
        return _plan_detail_error(PLAN_NOT_FOUND_MESSAGE)
    except sqlite3.DatabaseError as exc:
        return JSONResponse(
            {"detail": None, "errors": list(_inspection_errors(exc))},
            status_code=SERVER_ERROR_STATUS_CODE,
        )

    return JSONResponse(
        {"detail": serialize_plan_detail(detail), "errors": []},
        status_code=SUCCESS_STATUS_CODE,
    )


async def _create_add_plan(context: ApiRouteContext, request: Request) -> JSONResponse:
    if not _has_valid_csrf_token(context, request):
        return _plan_creation_forbidden()

    payload, payload_errors = await _read_json_payload(request)
    if payload_errors:
        return _plan_creation_error(payload_errors)

    source_path, source_errors = _optional_string_field(payload, "source_path")
    if source_errors:
        return _plan_creation_error(source_errors)

    try:
        plan = CreateAddPlanUseCase(context.add_plan_ports_factory()).execute(
            CreateAddPlanRequest(source_path=source_path)
        )
    except (ConfigStoreValidationError, AddLibrarySelectionError, AddSourceSelectionError) as exc:
        return _plan_creation_error(_errors_from_plan_client_error(exc))
    except (MetadataReadError, OSError, sqlite3.DatabaseError) as exc:
        return _plan_creation_exception_error(exc)

    return _created_plan_response(plan)


async def _create_organize_plan(context: ApiRouteContext, request: Request) -> JSONResponse:
    if not _has_valid_csrf_token(context, request):
        return _plan_creation_forbidden()

    payload, payload_errors = await _read_json_payload(request)
    if payload_errors:
        return _plan_creation_error(payload_errors)

    library_root, library_errors = _optional_string_field(payload, "library_root")
    if library_errors:
        return _plan_creation_error(library_errors)

    try:
        result = CreateOrganizePlanUseCase(context.organize_plan_ports_factory()).execute(
            CreateOrganizePlanRequest(library_root=library_root)
        )
    except (ConfigStoreValidationError, OrganizeLibrarySelectionError) as exc:
        return _plan_creation_error(_errors_from_plan_client_error(exc))
    except (MetadataReadError, OSError, sqlite3.DatabaseError) as exc:
        return _plan_creation_exception_error(exc)

    return _created_organize_response(result)


async def _create_refresh_plan(context: ApiRouteContext, request: Request) -> JSONResponse:
    if not _has_valid_csrf_token(context, request):
        return _plan_creation_forbidden()

    payload, payload_errors = await _read_json_payload(request)
    if payload_errors:
        return _plan_creation_error(payload_errors)

    target_path, target_errors = _optional_string_field(payload, "target_path")
    include_all, include_all_errors = _optional_boolean_field(payload, "include_all")
    request_errors = target_errors + include_all_errors
    if request_errors:
        return _plan_creation_error(request_errors)

    try:
        plan = CreateRefreshPlanUseCase(context.refresh_plan_ports_factory()).execute(
            CreateRefreshPlanRequest(target_path=target_path, include_all=include_all)
        )
    except (ConfigStoreValidationError, RefreshLibrarySelectionError, RefreshTargetSelectionError) as exc:
        return _plan_creation_error(_errors_from_plan_client_error(exc))
    except (MetadataReadError, OSError, sqlite3.DatabaseError) as exc:
        return _plan_creation_server_error(exc)

    return _created_plan_response(plan)


def _get_check(context: ApiRouteContext) -> JSONResponse:
    try:
        issues = CheckLibraryUseCase(context.check_ports_factory()).execute(CheckLibraryRequest())
    except (ConfigStoreValidationError, CheckLibraryError) as exc:
        return JSONResponse(
            {"issues": [], "errors": list(_errors_from_client_error(exc))},
            status_code=ERROR_STATUS_CODE,
        )
    except (MetadataReadError, OSError, sqlite3.DatabaseError) as exc:
        return JSONResponse(
            {"issues": [], "errors": [f"Check failed: {exc}"]},
            status_code=SERVER_ERROR_STATUS_CODE,
        )

    return JSONResponse(
        {"issues": [serialize_check_issue(issue) for issue in issues], "errors": []},
        status_code=SUCCESS_STATUS_CODE,
    )


def _get_tracks(context: ApiRouteContext, request: Request) -> JSONResponse:
    cursor_key, cursor_errors = _cursor_key_from_query(request.query_params.get("cursor"))
    if cursor_errors:
        return _list_error_response(cursor_errors)

    library_id, library_errors = _library_id_from_query(request.query_params.get("library_id"))
    status, status_errors = _track_status_from_query(request.query_params.get("status"))
    limit, limit_errors = _limit_from_query(request.query_params.get("limit"))
    filter_errors = library_errors + status_errors + limit_errors
    if filter_errors:
        return _list_error_response(filter_errors)

    effective_limit = cast("int", limit)
    search = _optional_query_text(request.query_params.get("query"))

    try:
        page = ListTracksUseCase(context.tracks_ports_factory()).execute(
            ListTracksRequest(
                library_id=library_id,
                search=search,
                status=status,
                page=PageRequest(limit=effective_limit, cursor_key=cursor_key),
            )
        )
    except CursorDecodeError:
        return _list_error_response((INVALID_CURSOR_MESSAGE,))
    except sqlite3.DatabaseError as exc:
        return JSONResponse(
            {"items": [], "page": None, "errors": list(_inspection_errors(exc))},
            status_code=SERVER_ERROR_STATUS_CODE,
        )

    return JSONResponse(
        _list_envelope(
            [serialize_track_summary(track) for track in page.items],
            limit=effective_limit,
            next_cursor_key=page.next_cursor_key,
            total=page.total,
        ),
        status_code=SUCCESS_STATUS_CODE,
    )


def _get_track_facets(context: ApiRouteContext, request: Request) -> JSONResponse:
    library_id, library_errors = _library_id_from_query(request.query_params.get("library_id"))
    if library_errors:
        return _facet_error_response(library_errors)

    try:
        result = GetTrackStatusFacetsUseCase(context.tracks_ports_factory()).execute(
            TrackStatusFacetsRequest(library_id=library_id)
        )
    except sqlite3.DatabaseError as exc:
        return JSONResponse(
            {"facets": {}, "total": None, "errors": list(_inspection_errors(exc))},
            status_code=SERVER_ERROR_STATUS_CODE,
        )

    return JSONResponse(
        _facet_envelope(
            {"status": [serialize_facet_value(facet) for facet in result.facets]},
            total=result.total,
        ),
        status_code=SUCCESS_STATUS_CODE,
    )


def _get_track_groups(context: ApiRouteContext, request: Request) -> JSONResponse:
    cursor_key, cursor_errors = _cursor_key_from_query(request.query_params.get("cursor"))
    if cursor_errors:
        return _group_error_response(cursor_errors)

    grouping, grouping_errors = _track_grouping_from_query(request.query_params.get("group_by"))
    library_id, library_errors = _library_id_from_query(request.query_params.get("library_id"))
    limit, limit_errors = _limit_from_query(request.query_params.get("limit"))
    filter_errors = grouping_errors + library_errors + limit_errors
    if filter_errors:
        return _group_error_response(filter_errors)

    effective_limit = cast("int", limit)
    effective_grouping = cast("TrackGrouping", grouping)

    try:
        page = GroupTracksUseCase(context.tracks_ports_factory()).execute(
            GroupTracksRequest(
                grouping=effective_grouping,
                library_id=library_id,
                page=PageRequest(limit=effective_limit, cursor_key=cursor_key),
            )
        )
    except CursorDecodeError:
        return _group_error_response((INVALID_CURSOR_MESSAGE,))
    except sqlite3.DatabaseError as exc:
        return JSONResponse(
            {"group_by": None, "items": [], "page": None, "errors": list(_inspection_errors(exc))},
            status_code=SERVER_ERROR_STATUS_CODE,
        )

    return JSONResponse(
        _group_envelope(
            effective_grouping.value,
            [serialize_group_count(group) for group in page.items],
            limit=effective_limit,
            next_cursor_key=page.next_cursor_key,
            total=page.total,
        ),
        status_code=SUCCESS_STATUS_CODE,
    )


async def _read_json_payload(request: Request) -> tuple[object, tuple[str, ...]]:
    try:
        return await request.json(), ()
    except JSONDecodeError:
        return None, (INVALID_JSON_ERROR_MESSAGE,)


def _settings_validation_error(errors: tuple[str, ...]) -> JSONResponse:
    return JSONResponse(
        {"valid": False, "errors": list(errors), "changes": [], "preview": {"path": None, "errors": []}},
        status_code=ERROR_STATUS_CODE,
    )


def _settings_preview_error(errors: tuple[str, ...]) -> JSONResponse:
    return JSONResponse({"path": None, "errors": list(errors)}, status_code=ERROR_STATUS_CODE)


def _settings_save_error(errors: tuple[str, ...]) -> JSONResponse:
    return JSONResponse({"saved": False, "errors": list(errors), "changes": []}, status_code=ERROR_STATUS_CODE)


def _artist_ids_error(errors: tuple[str, ...]) -> JSONResponse:
    return JSONResponse(
        {"generated": False, "errors": list(errors), "entries": []},
        status_code=ERROR_STATUS_CODE,
    )


def _artist_ids_request(payload: object) -> tuple[GenerateArtistIdsRequest, tuple[str, ...]]:
    if not isinstance(payload, Mapping):
        return GenerateArtistIdsRequest(()), (REQUEST_BODY_ERROR,)
    payload_mapping = cast("Mapping[str, object]", payload)
    artist_names = payload_mapping.get("artist_names")
    if not isinstance(artist_names, list):
        return GenerateArtistIdsRequest(()), (ARTIST_IDS_FIELD_ERROR,)
    artist_name_items = cast("list[object]", artist_names)
    if not all(isinstance(item, str) for item in artist_name_items):
        return GenerateArtistIdsRequest(()), (ARTIST_IDS_FIELD_ERROR,)
    overwrite = payload_mapping.get("overwrite", False)
    if not isinstance(overwrite, bool):
        return GenerateArtistIdsRequest(()), ("Request body overwrite must be a boolean.",)
    return GenerateArtistIdsRequest(tuple(cast("list[str]", artist_name_items)), overwrite=overwrite), ()


def _load_current_config(ports: SettingsPorts) -> tuple[AppConfig, tuple[str, ...]]:
    try:
        return LoadSettingsUseCase(ports).execute(), ()
    except ConfigStoreValidationError as exc:
        return AppConfig(), exc.errors
    except OSError as exc:
        return AppConfig(), (f"Config I/O error: {exc}",)


def _validate_persisted_settings(ports: SettingsPorts) -> ValidateSettingsResult:
    try:
        return ValidateSettingsUseCase(ports).execute()
    except OSError as exc:
        return ValidateSettingsResult(valid=False, errors=(f"Config I/O error: {exc}",))


def _preview_path_policy(
    config: AppConfig,
    *,
    metadata: TrackMetadata | None = None,
    file_extension: str | None = None,
) -> PathPolicyPreviewResult:
    return PreviewPathPolicyUseCase().execute(
        PathPolicyPreviewRequest(
            path_policy=config.path_policy,
            artist_ids=config.artist_ids,
            metadata=_preview_metadata() if metadata is None else metadata,
            file_extension=PATH_POLICY_PREVIEW_FILE_EXTENSION if file_extension is None else file_extension,
        )
    )


def _preview_metadata() -> TrackMetadata:
    return TrackMetadata(
        title=PATH_POLICY_PREVIEW_TITLE,
        artist=PATH_POLICY_PREVIEW_ARTIST,
        album=PATH_POLICY_PREVIEW_ALBUM,
        album_artist=PATH_POLICY_PREVIEW_ALBUM_ARTIST,
        year=PATH_POLICY_PREVIEW_YEAR,
        disc_number=PATH_POLICY_PREVIEW_DISC_NUMBER,
        disc_total=PATH_POLICY_PREVIEW_DISC_TOTAL,
        track_number=PATH_POLICY_PREVIEW_TRACK_NUMBER,
    )


def _has_valid_csrf_token(context: ApiRouteContext, request: Request) -> bool:
    supplied_token = request.headers.get(WEB_CSRF_HEADER_NAME, "")
    return compare_digest(supplied_token, context.csrf_token)


def _run_id_from_text(raw_value: str) -> RunId | None:
    try:
        return RunId(parse_uuid(raw_value))
    except ValueError:
        return None


def _plan_id_from_text(raw_value: str) -> PlanId | None:
    try:
        return PlanId(parse_uuid(raw_value))
    except ValueError:
        return None


def _plan_status_from_query(raw_value: str | None) -> tuple[PlanStatus | None, tuple[str, ...]]:
    if raw_value is None or raw_value == "":
        return None, ()
    try:
        return PlanStatus(raw_value), ()
    except ValueError:
        return None, (f"Invalid plan status filter: {raw_value}",)


def _plan_type_from_query(raw_value: str | None) -> tuple[PlanType | None, tuple[str, ...]]:
    if raw_value is None or raw_value == "":
        return None, ()
    try:
        return PlanType(raw_value), ()
    except ValueError:
        return None, (f"Invalid plan type filter: {raw_value}",)


def _action_status_from_query(raw_value: str | None) -> tuple[ActionStatus | None, tuple[str, ...]]:
    if raw_value is None or raw_value in {"", "all"}:
        return None, ()
    try:
        return ActionStatus(raw_value), ()
    except ValueError:
        return None, (f"Invalid action status filter: {raw_value}",)


def _positive_int_from_query(raw_value: str | None, *, field_name: str) -> tuple[int | None, tuple[str, ...]]:
    if raw_value is None or raw_value == "":
        return None, ()
    try:
        value = int(raw_value)
    except ValueError:
        return None, (f"Query parameter {field_name} must be a positive integer.",)
    if value <= 0:
        return None, (f"Query parameter {field_name} must be a positive integer.",)
    return value, ()


def _library_id_from_query(raw_value: str | None) -> tuple[LibraryId | None, tuple[str, ...]]:
    """Parse an optional `library_id` filter shared by every browsing endpoint."""
    if raw_value is None or raw_value == "":
        return None, ()
    try:
        return LibraryId(parse_uuid(raw_value)), ()
    except ValueError:
        return None, (f"Invalid library_id filter: {raw_value}",)


def _limit_from_query(raw_value: str | None) -> tuple[int | None, tuple[str, ...]]:
    """Parse and clamp the shared `limit` query parameter per shared.pagination.clamp_limit."""
    if raw_value is None or raw_value == "":
        return clamp_limit(None), ()
    try:
        parsed = int(raw_value)
    except ValueError:
        return None, ("Query parameter limit must be an integer.",)
    try:
        return clamp_limit(parsed), ()
    except ValueError as exc:
        return None, (str(exc),)


def _cursor_key_from_query(raw_value: str | None) -> tuple[tuple[str, ...] | None, tuple[str, ...]]:
    """Decode the shared opaque `cursor` query parameter into a keyset key."""
    if raw_value is None or raw_value == "":
        return None, ()
    try:
        return decode_cursor(raw_value), ()
    except CursorDecodeError:
        return None, (INVALID_CURSOR_MESSAGE,)


def _optional_query_text(raw_value: str | None) -> str | None:
    """Return a free-text query parameter, treating an empty string as absent."""
    if raw_value is None or raw_value == "":
        return None
    return raw_value


def _track_status_from_query(raw_value: str | None) -> tuple[TrackStatus | None, tuple[str, ...]]:
    if raw_value is None or raw_value == "":
        return None, ()
    try:
        return TrackStatus(raw_value), ()
    except ValueError:
        return None, (f"Invalid track status filter: {raw_value}",)


def _track_grouping_from_query(raw_value: str | None) -> tuple[TrackGrouping | None, tuple[str, ...]]:
    if raw_value is None or raw_value == "":
        return None, ("Query parameter group_by is required.",)
    try:
        return TrackGrouping(raw_value), ()
    except ValueError:
        return None, (f"Invalid group_by filter: {raw_value}",)


def _list_envelope(
    items: list[dict[str, object]],
    *,
    limit: int,
    next_cursor_key: tuple[str, ...] | None,
    total: int,
) -> dict[str, object]:
    """Build the shared list-endpoint envelope: items + page + errors.

    Reusable across every keyset-paginated list endpoint (Tracks now; Plans,
    History, and Check in later dispatches).
    """
    return {
        "items": items,
        "page": serialize_page_info(limit=limit, next_cursor_key=next_cursor_key, total=total),
        "errors": [],
    }


def _group_envelope(
    group_by: str,
    items: list[dict[str, object]],
    *,
    limit: int,
    next_cursor_key: tuple[str, ...] | None,
    total: int,
) -> dict[str, object]:
    """Build the shared group-endpoint envelope: group_by + items + page + errors."""
    return {
        "group_by": group_by,
        **_list_envelope(items, limit=limit, next_cursor_key=next_cursor_key, total=total),
    }


def _facet_envelope(facets: dict[str, list[dict[str, object]]], *, total: int) -> dict[str, object]:
    """Build the shared facet-endpoint envelope: facets + total + errors."""
    return {"facets": facets, "total": total, "errors": []}


def _list_error_response(errors: tuple[str, ...]) -> JSONResponse:
    """Build the shared 400 error envelope for list endpoints (items/page emptied)."""
    return JSONResponse({"items": [], "page": None, "errors": list(errors)}, status_code=ERROR_STATUS_CODE)


def _group_error_response(errors: tuple[str, ...]) -> JSONResponse:
    """Build the shared 400 error envelope for group endpoints (group_by/items/page emptied)."""
    return JSONResponse(
        {"group_by": None, "items": [], "page": None, "errors": list(errors)},
        status_code=ERROR_STATUS_CODE,
    )


def _facet_error_response(errors: tuple[str, ...]) -> JSONResponse:
    """Build the shared 400 error envelope for facet endpoints (facets/total emptied)."""
    return JSONResponse({"facets": {}, "total": None, "errors": list(errors)}, status_code=ERROR_STATUS_CODE)


def _optional_string_field(payload: object, field_name: str) -> tuple[str | None, tuple[str, ...]]:
    if not isinstance(payload, Mapping):
        return None, (REQUEST_BODY_ERROR,)
    payload_mapping = cast("Mapping[str, object]", payload)
    raw_value = payload_mapping.get(field_name)
    if raw_value is None:
        return None, ()
    if not isinstance(raw_value, str):
        return None, (f"Request body {field_name} must be a string or null.",)
    value = raw_value.strip()
    return (None if value == "" else value), ()


def _optional_boolean_field(payload: object, field_name: str) -> tuple[bool, tuple[str, ...]]:
    if not isinstance(payload, Mapping):
        return False, (REQUEST_BODY_ERROR,)
    payload_mapping = cast("Mapping[str, object]", payload)
    raw_value = payload_mapping.get(field_name, False)
    if not isinstance(raw_value, bool):
        return False, (f"Request body {field_name} must be a boolean.",)
    return raw_value, ()


def _run_detail_error(message: str) -> JSONResponse:
    return JSONResponse({"detail": None, "errors": [message]}, status_code=NOT_FOUND_STATUS_CODE)


def _plan_detail_error(message: str) -> JSONResponse:
    return JSONResponse({"detail": None, "errors": [message]}, status_code=NOT_FOUND_STATUS_CODE)


def _plan_creation_forbidden() -> JSONResponse:
    return JSONResponse(
        {"created": False, "detail": None, "registration": None, "errors": [PLAN_CSRF_ERROR_MESSAGE]},
        status_code=FORBIDDEN_STATUS_CODE,
    )


def _plan_creation_error(errors: tuple[str, ...]) -> JSONResponse:
    return JSONResponse(
        {"created": False, "detail": None, "registration": None, "errors": list(errors)},
        status_code=ERROR_STATUS_CODE,
    )


def _plan_creation_server_error(exc: BaseException) -> JSONResponse:
    return JSONResponse(
        {"created": False, "detail": None, "registration": None, "errors": [f"{PLAN_CREATION_ERROR_PREFIX}: {exc}"]},
        status_code=SERVER_ERROR_STATUS_CODE,
    )


def _plan_creation_exception_error(exc: MetadataReadError | OSError | sqlite3.DatabaseError) -> JSONResponse:
    if isinstance(exc, (FileNotFoundError, NotADirectoryError)):
        return _plan_creation_error(_errors_from_plan_path_error(exc))
    return _plan_creation_server_error(exc)


def _created_plan_response(plan: Plan) -> JSONResponse:
    return JSONResponse(
        {
            "created": True,
            "detail": serialize_plan_detail_parts(plan, plan.actions),
            "registration": None,
            "errors": [],
        },
        status_code=SUCCESS_STATUS_CODE,
    )


def _created_organize_response(result: OrganizeLibraryResult) -> JSONResponse:
    return JSONResponse(
        {
            "created": result.plan is not None,
            "detail": None if result.plan is None else serialize_plan_detail_parts(result.plan, result.actions),
            "registration": serialize_organize_registration(result),
            "errors": [],
        },
        status_code=SUCCESS_STATUS_CODE,
    )


def _errors_from_client_error(exc: ConfigStoreValidationError | CheckLibraryError) -> tuple[str, ...]:
    if isinstance(exc, ConfigStoreValidationError):
        return exc.errors
    return (str(exc),)


def _errors_from_plan_client_error(exc: BaseException) -> tuple[str, ...]:
    if isinstance(exc, ConfigStoreValidationError):
        return exc.errors
    return (str(exc),)


def _errors_from_plan_path_error(exc: FileNotFoundError | NotADirectoryError) -> tuple[str, ...]:
    target = _path_error_target(exc)
    if isinstance(exc, FileNotFoundError):
        return (f"{PLAN_PATH_NOT_FOUND_MESSAGE}: {target}",)
    return (f"{PLAN_PATH_NOT_DIRECTORY_MESSAGE}: {target}",)


def _path_error_target(exc: OSError) -> str:
    filename = cast("object | None", exc.filename)
    if filename is not None:
        return str(filename)
    args = cast("tuple[object, ...]", exc.args)
    if args:
        return str(args[0])
    return ""


def _inspection_errors(exc: sqlite3.DatabaseError) -> tuple[str, ...]:
    return (f"{INSPECTION_ERROR_PREFIX}: {exc}",)
