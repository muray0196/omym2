"""
Summary: Defines local Web JSON API routes.
Why: Lets the React UI use feature usecases without server-rendered templates.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from json import JSONDecodeError
from secrets import compare_digest
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from omym2.adapters.metadata.mutagen_reader import MetadataReadError
from omym2.adapters.web.routes.api_serializers import (
    serialize_app_config,
    serialize_check_issue,
    serialize_path_preview,
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
    PATH_POLICY_PREVIEW_FILE_EXTENSION,
    PATH_POLICY_PREVIEW_TITLE,
    PATH_POLICY_PREVIEW_TRACK_NUMBER,
    PATH_POLICY_PREVIEW_YEAR,
    WEB_API_CHECK_ROUTE,
    WEB_API_HISTORY_ROUTE,
    WEB_API_RUN_DETAIL_ROUTE,
    WEB_API_SETTINGS_PREVIEW_ROUTE,
    WEB_API_SETTINGS_ROUTE,
    WEB_API_SETTINGS_SAVE_ROUTE,
    WEB_API_SETTINGS_VALIDATE_ROUTE,
    WEB_API_TRACKS_ROUTE,
    WEB_CSRF_HEADER_NAME,
)
from omym2.domain.models.app_config import AppConfig
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.features.check.dto import CheckLibraryRequest
from omym2.features.check.usecases.check_library import CheckLibraryError, CheckLibraryUseCase
from omym2.features.common_ports import ConfigStoreValidationError
from omym2.features.history.dto import GetRunDetailRequest, ListRunsRequest
from omym2.features.history.usecases.get_run_detail import GetRunDetailUseCase, RunNotFoundError
from omym2.features.history.usecases.list_runs import ListRunsUseCase
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
from omym2.features.tracks.dto import ListTracksRequest
from omym2.features.tracks.usecases.list_tracks import ListTracksUseCase
from omym2.shared.ids import RunId, parse_uuid

if TYPE_CHECKING:
    from omym2.features.check.ports import CheckLibraryPorts
    from omym2.features.history.ports import HistoryPorts
    from omym2.features.settings.ports import SettingsPorts
    from omym2.features.tracks.ports import TracksPorts

ERROR_STATUS_CODE = 400
FORBIDDEN_STATUS_CODE = 403
NOT_FOUND_STATUS_CODE = 404
SERVER_ERROR_STATUS_CODE = 500
SUCCESS_STATUS_CODE = 200
INVALID_JSON_ERROR_MESSAGE = "Request body must be valid JSON."
RUN_NOT_FOUND_MESSAGE = "Run was not found."
SAVE_CSRF_ERROR_MESSAGE = "Settings save request failed CSRF validation."
INSPECTION_ERROR_PREFIX = "Inspection failed"

type CheckPortsFactory = Callable[[], "CheckLibraryPorts"]
type HistoryPortsFactory = Callable[[], "HistoryPorts"]
type TracksPortsFactory = Callable[[], "TracksPorts"]


@dataclass(frozen=True, slots=True)
class ApiRouteContext:
    """Concrete dependencies for JSON API routes."""

    check_ports_factory: CheckPortsFactory
    csrf_token: str
    history_ports_factory: HistoryPortsFactory
    settings_ports: SettingsPorts
    tracks_ports_factory: TracksPortsFactory


def create_api_router(context: ApiRouteContext) -> APIRouter:
    """Create JSON API routes bound to concrete dependencies."""
    router = APIRouter()

    def get_settings() -> JSONResponse:
        return _get_settings(context)

    async def validate_settings(request: Request) -> JSONResponse:
        return await _validate_settings(context, request)

    async def preview_settings(request: Request) -> JSONResponse:
        return await _preview_settings(request)

    async def save_settings(request: Request) -> JSONResponse:
        return await _save_settings(context, request)

    def get_history() -> JSONResponse:
        return _get_history(context)

    def get_run_detail(run_id: str) -> JSONResponse:
        return _get_run_detail(context, run_id)

    def get_check() -> JSONResponse:
        return _get_check(context)

    def get_tracks() -> JSONResponse:
        return _get_tracks(context)

    router.add_api_route(WEB_API_SETTINGS_ROUTE, get_settings, methods=["GET"])
    router.add_api_route(WEB_API_SETTINGS_PREVIEW_ROUTE, preview_settings, methods=["POST"])
    router.add_api_route(WEB_API_SETTINGS_VALIDATE_ROUTE, validate_settings, methods=["POST"])
    router.add_api_route(WEB_API_SETTINGS_SAVE_ROUTE, save_settings, methods=["POST"])
    router.add_api_route(WEB_API_HISTORY_ROUTE, get_history, methods=["GET"])
    router.add_api_route(WEB_API_RUN_DETAIL_ROUTE, get_run_detail, methods=["GET"])
    router.add_api_route(WEB_API_CHECK_ROUTE, get_check, methods=["GET"])
    router.add_api_route(WEB_API_TRACKS_ROUTE, get_tracks, methods=["GET"])
    return router


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


def _get_tracks(context: ApiRouteContext) -> JSONResponse:
    try:
        tracks = ListTracksUseCase(context.tracks_ports_factory()).execute(ListTracksRequest())
    except sqlite3.DatabaseError as exc:
        return JSONResponse(
            {"tracks": [], "errors": list(_inspection_errors(exc))},
            status_code=SERVER_ERROR_STATUS_CODE,
        )

    return JSONResponse(
        {"tracks": [serialize_track_summary(track) for track in tracks], "errors": []},
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


def _run_detail_error(message: str) -> JSONResponse:
    return JSONResponse({"detail": None, "errors": [message]}, status_code=NOT_FOUND_STATUS_CODE)


def _errors_from_client_error(exc: ConfigStoreValidationError | CheckLibraryError) -> tuple[str, ...]:
    if isinstance(exc, ConfigStoreValidationError):
        return exc.errors
    return (str(exc),)


def _inspection_errors(exc: sqlite3.DatabaseError) -> tuple[str, ...]:
    return (f"{INSPECTION_ERROR_PREFIX}: {exc}",)
