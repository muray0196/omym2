"""
Summary: Defines local Web UI read-only inspection routes.
Why: Exposes history, check, and Track state without adding Web mutations.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from omym2.adapters.metadata.mutagen_reader import MetadataReadError
from omym2.config import (
    WEB_CHECK_ROUTE,
    WEB_CHECK_TEMPLATE_NAME,
    WEB_HISTORY_ROUTE,
    WEB_HISTORY_TEMPLATE_NAME,
    WEB_RUN_DETAIL_ROUTE,
    WEB_RUN_DETAIL_TEMPLATE_NAME,
    WEB_TRACKS_ROUTE,
    WEB_TRACKS_TEMPLATE_NAME,
)
from omym2.features.check.dto import CheckLibraryRequest
from omym2.features.check.usecases.check_library import CheckLibraryError, CheckLibraryUseCase
from omym2.features.common_ports import ConfigStoreValidationError
from omym2.features.history.dto import GetRunDetailRequest, ListRunsRequest
from omym2.features.history.usecases.get_run_detail import GetRunDetailUseCase, RunNotFoundError
from omym2.features.history.usecases.list_runs import ListRunsUseCase
from omym2.features.tracks.dto import ListTracksRequest
from omym2.features.tracks.usecases.list_tracks import ListTracksUseCase
from omym2.shared.ids import RunId, parse_uuid

if TYPE_CHECKING:
    from fastapi.templating import Jinja2Templates
    from starlette.responses import Response

    from omym2.features.check.ports import CheckLibraryPorts
    from omym2.features.history.dto import RunDetail
    from omym2.features.history.ports import HistoryPorts
    from omym2.features.tracks.ports import TracksPorts

ERROR_STATUS_CODE = 400
NOT_FOUND_STATUS_CODE = 404
SERVER_ERROR_STATUS_CODE = 500
SUCCESS_STATUS_CODE = 200
RUN_NOT_FOUND_MESSAGE = "Run was not found."
INSPECTION_ERROR_PREFIX = "Inspection failed"

type CheckPortsFactory = Callable[[], "CheckLibraryPorts"]
type HistoryPortsFactory = Callable[[], "HistoryPorts"]
type TracksPortsFactory = Callable[[], "TracksPorts"]


@dataclass(frozen=True, slots=True)
class InspectionRouteContext:
    """Concrete dependencies for read-only inspection routes."""

    check_ports_factory: CheckPortsFactory
    history_ports_factory: HistoryPortsFactory
    templates: Jinja2Templates
    tracks_ports_factory: TracksPortsFactory


def create_inspection_router(context: InspectionRouteContext) -> APIRouter:
    """Create read-only inspection routes bound to concrete dependencies."""
    router = APIRouter()

    def show_history(request: Request) -> Response:
        """Render the Run history screen."""
        return _show_history(context, request)

    def show_run_detail(request: Request, run_id: str) -> Response:
        """Render one Run and its durable FileEvents."""
        return _show_run_detail(context, request, run_id)

    def show_check(request: Request) -> Response:
        """Render read-only Library consistency check results."""
        return _show_check(context, request)

    def show_tracks(request: Request) -> Response:
        """Render current managed Track state."""
        return _show_tracks(context, request)

    router.add_api_route(WEB_HISTORY_ROUTE, show_history, methods=["GET"], response_class=HTMLResponse)
    router.add_api_route(WEB_RUN_DETAIL_ROUTE, show_run_detail, methods=["GET"], response_class=HTMLResponse)
    router.add_api_route(WEB_CHECK_ROUTE, show_check, methods=["GET"], response_class=HTMLResponse)
    router.add_api_route(WEB_TRACKS_ROUTE, show_tracks, methods=["GET"], response_class=HTMLResponse)
    return router


def _show_history(context: InspectionRouteContext, request: Request) -> Response:
    errors = ()
    runs = ()
    status_code = SUCCESS_STATUS_CODE
    try:
        runs = ListRunsUseCase(context.history_ports_factory()).execute(ListRunsRequest())
    except sqlite3.DatabaseError as exc:
        errors = _inspection_errors(exc)
        status_code = SERVER_ERROR_STATUS_CODE

    return context.templates.TemplateResponse(
        request,
        WEB_HISTORY_TEMPLATE_NAME,
        {"active_nav": "history", "errors": errors, "runs": runs},
        status_code=status_code,
    )


def _show_run_detail(context: InspectionRouteContext, request: Request, run_id: str) -> Response:
    parsed_run_id = _run_id_from_text(run_id)
    if parsed_run_id is None:
        return _render_run_detail_error(context, request, RUN_NOT_FOUND_MESSAGE)

    try:
        detail = GetRunDetailUseCase(context.history_ports_factory()).execute(GetRunDetailRequest(parsed_run_id))
    except RunNotFoundError:
        return _render_run_detail_error(context, request, RUN_NOT_FOUND_MESSAGE)
    except sqlite3.DatabaseError as exc:
        return _render_run_detail(
            context,
            request,
            detail=None,
            errors=_inspection_errors(exc),
            status_code=SERVER_ERROR_STATUS_CODE,
        )

    return _render_run_detail(context, request, detail=detail, errors=(), status_code=SUCCESS_STATUS_CODE)


def _show_check(context: InspectionRouteContext, request: Request) -> Response:
    issues = ()
    errors = ()
    status_code = SUCCESS_STATUS_CODE

    try:
        issues = CheckLibraryUseCase(context.check_ports_factory()).execute(CheckLibraryRequest())
    except (ConfigStoreValidationError, CheckLibraryError) as exc:
        errors = _errors_from_client_error(exc)
        status_code = ERROR_STATUS_CODE
    except (MetadataReadError, OSError, sqlite3.DatabaseError) as exc:
        errors = (f"Check failed: {exc}",)
        status_code = SERVER_ERROR_STATUS_CODE

    return context.templates.TemplateResponse(
        request,
        WEB_CHECK_TEMPLATE_NAME,
        {"active_nav": "check", "errors": errors, "issues": issues},
        status_code=status_code,
    )


def _show_tracks(context: InspectionRouteContext, request: Request) -> Response:
    errors = ()
    status_code = SUCCESS_STATUS_CODE
    tracks = ()
    try:
        tracks = ListTracksUseCase(context.tracks_ports_factory()).execute(ListTracksRequest())
    except sqlite3.DatabaseError as exc:
        errors = _inspection_errors(exc)
        status_code = SERVER_ERROR_STATUS_CODE

    return context.templates.TemplateResponse(
        request,
        WEB_TRACKS_TEMPLATE_NAME,
        {"active_nav": "tracks", "errors": errors, "tracks": tracks},
        status_code=status_code,
    )


def _render_run_detail_error(context: InspectionRouteContext, request: Request, message: str) -> Response:
    return _render_run_detail(context, request, detail=None, errors=(message,), status_code=NOT_FOUND_STATUS_CODE)


def _render_run_detail(
    context: InspectionRouteContext,
    request: Request,
    *,
    detail: RunDetail | None,
    errors: tuple[str, ...],
    status_code: int,
) -> Response:
    return context.templates.TemplateResponse(
        request,
        WEB_RUN_DETAIL_TEMPLATE_NAME,
        {"active_nav": "history", "detail": detail, "errors": errors},
        status_code=status_code,
    )


def _run_id_from_text(raw_value: str) -> RunId | None:
    try:
        return RunId(parse_uuid(raw_value))
    except ValueError:
        return None


def _errors_from_client_error(exc: ConfigStoreValidationError | CheckLibraryError) -> tuple[str, ...]:
    if isinstance(exc, ConfigStoreValidationError):
        return exc.errors
    return (str(exc),)


def _inspection_errors(exc: sqlite3.DatabaseError) -> tuple[str, ...]:
    return (f"{INSPECTION_ERROR_PREFIX}: {exc}",)
