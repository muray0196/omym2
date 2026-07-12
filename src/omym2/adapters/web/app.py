"""
Summary: Builds the local renewed Web application.
Why: Serves the typed Bootstrap API and packaged Vite SPA with one secure loopback boundary.
"""

from __future__ import annotations

import logging
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, cast
from uuid import uuid4

from fastapi import (  # noqa: TC002  # FastAPI resolves nested route annotations at registration.
    FastAPI,
    Request,
    Response,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.routing import Match

from omym2.adapters.web.routes.api_context import (
    ApiRouteContext,  # noqa: TC001  # FastAPI factory annotation is public runtime API.
)
from omym2.adapters.web.schema_app import create_api_schema_app
from omym2.adapters.web.schemas.api_envelopes import ApiFailureEnvelope
from omym2.adapters.web.schemas.api_errors import ApiError, ApiErrorCode
from omym2.adapters.web.static_assets import is_hashed_asset_name
from omym2.config import (
    HTTP_BAD_REQUEST_STATUS,
    HTTP_INTERNAL_ERROR_STATUS,
    HTTP_METHOD_NOT_ALLOWED_STATUS,
    HTTP_NOT_FOUND_STATUS,
    HTTP_SERVICE_UNAVAILABLE_STATUS,
    HTTP_UNPROCESSABLE_CONTENT_STATUS,
    WEB_API_NOT_FOUND_MESSAGE,
    WEB_API_PREFIX,
    WEB_ASSET_CACHE_CONTROL,
    WEB_CONTENT_SECURITY_POLICY,
    WEB_CONTENT_TYPE_OPTIONS_HEADER_NAME,
    WEB_CONTENT_TYPE_OPTIONS_VALUE,
    WEB_CORRELATION_HEADER_NAME,
    WEB_CSP_HEADER_NAME,
    WEB_FRAME_OPTIONS,
    WEB_FRAME_OPTIONS_HEADER_NAME,
    WEB_HTML_ACCEPT_MEDIA_TYPE,
    WEB_INDEX_CACHE_CONTROL,
    WEB_METHOD_NOT_ALLOWED_MESSAGE,
    WEB_PRODUCTION_ALLOWED_HOSTS,
    WEB_REFERRER_POLICY,
    WEB_REFERRER_POLICY_HEADER_NAME,
    WEB_STATIC_ASSET_NOT_FOUND_MESSAGE,
    WEB_STATIC_ASSET_ROUTE,
    WEB_STATIC_EXPORT_DIRECTORY_NAME,
    WEB_STATIC_EXPORT_INDEX_FILE_NAME,
    WEB_STATIC_EXPORT_MISSING_MESSAGE,
    WEB_UI_NOT_FOUND_MESSAGE,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from starlette.types import Scope

LOGGER = logging.getLogger(__name__)
INTERNAL_ERROR_MESSAGE = "An unexpected internal error occurred."
INVALID_JSON_MESSAGE = "Request body must be valid JSON."
VALIDATION_FAILED_MESSAGE = "Request validation failed."
INVALID_HOST_MESSAGE = "Invalid host header"


def create_web_app(
    context: ApiRouteContext,
    static_dist_path: Path | None = None,
    *,
    allowed_hosts: Sequence[str] = WEB_PRODUCTION_ALLOWED_HOSTS,
) -> FastAPI:
    """Create the production API and packaged Vite SPA application."""
    app = create_api_schema_app()
    app.state.api_route_context = context
    _install_allowed_hosts(app, allowed_hosts)
    _install_error_handlers(app)
    _install_response_headers(app)

    package_dir = Path(__file__).resolve().parent
    web_dist = static_dist_path or package_dir / WEB_STATIC_EXPORT_DIRECTORY_NAME

    def serve_asset(asset_path: str) -> Response:
        return _asset_response(web_dist, asset_path)

    def serve_ui(ui_path: str, request: Request) -> Response:
        return _ui_response(web_dist, ui_path, request)

    app.add_api_route(
        f"{WEB_STATIC_ASSET_ROUTE}/{{asset_path:path}}",
        serve_asset,
        methods=["GET"],
        include_in_schema=False,
    )
    app.add_api_route("/{ui_path:path}", serve_ui, methods=["GET"], include_in_schema=False)
    return app


def _install_allowed_hosts(app: FastAPI, allowed_hosts: Sequence[str]) -> None:
    allowed = frozenset(host.lower() for host in allowed_hosts)

    @app.middleware("http")
    async def enforce_allowed_host(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered middleware.
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if _host_name(request.headers.get("host", "")) in allowed:
            return await call_next(request)
        if _is_api_path(request.url.path):
            return _api_failure(HTTP_NOT_FOUND_STATUS, ApiErrorCode.API_NOT_FOUND, WEB_API_NOT_FOUND_MESSAGE)
        return PlainTextResponse(INVALID_HOST_MESSAGE, status_code=HTTP_BAD_REQUEST_STATUS)


def _install_response_headers(app: FastAPI) -> None:
    @app.middleware("http")
    async def add_response_headers(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered middleware.
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        correlation_id = str(uuid4())
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        _set_common_response_headers(response, correlation_id)
        LOGGER.info(
            "Web request completed correlation_id=%s method=%s path=%s status=%s",
            correlation_id,
            request.method,
            request.url.path,
            response.status_code,
        )
        return response


def _install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered handlers.
        request: Request,
        exc: RequestValidationError,
    ) -> Response:
        if not _is_api_path(request.url.path):
            return PlainTextResponse(VALIDATION_FAILED_MESSAGE, status_code=HTTP_UNPROCESSABLE_CONTENT_STATUS)
        validation_errors = cast("list[dict[str, object]]", exc.errors())
        is_json_decode = any(error.get("type") == "json_invalid" for error in validation_errors)
        code = ApiErrorCode.INVALID_JSON if is_json_decode else ApiErrorCode.VALIDATION_FAILED
        status_code = HTTP_BAD_REQUEST_STATUS if is_json_decode else HTTP_UNPROCESSABLE_CONTENT_STATUS
        message = INVALID_JSON_MESSAGE if is_json_decode else VALIDATION_FAILED_MESSAGE
        return _api_failure(status_code, code, message, field=_validation_field(exc))

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered handlers.
        request: Request,
        exc: StarletteHTTPException,
    ) -> Response:
        if _is_api_path(request.url.path):
            if exc.status_code == HTTP_METHOD_NOT_ALLOWED_STATUS and _is_known_api_path(app, request.url.path):
                return _api_failure(
                    HTTP_METHOD_NOT_ALLOWED_STATUS,
                    ApiErrorCode.METHOD_NOT_ALLOWED,
                    WEB_METHOD_NOT_ALLOWED_MESSAGE,
                )
            return _api_failure(HTTP_NOT_FOUND_STATUS, ApiErrorCode.API_NOT_FOUND, WEB_API_NOT_FOUND_MESSAGE)
        message = (
            WEB_METHOD_NOT_ALLOWED_MESSAGE
            if exc.status_code == HTTP_METHOD_NOT_ALLOWED_STATUS
            else WEB_UI_NOT_FOUND_MESSAGE
        )
        return PlainTextResponse(message, status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def handle_unexpected_error(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered handlers.
        request: Request,
        exc: Exception,
    ) -> Response:
        correlation_id = _request_correlation_id(request)
        LOGGER.error("Unhandled Web request error correlation_id=%s", correlation_id, exc_info=exc)
        if _is_api_path(request.url.path):
            response = _api_failure(HTTP_INTERNAL_ERROR_STATUS, ApiErrorCode.INTERNAL_ERROR, INTERNAL_ERROR_MESSAGE)
        else:
            response = PlainTextResponse(INTERNAL_ERROR_MESSAGE, status_code=HTTP_INTERNAL_ERROR_STATUS)
        _set_common_response_headers(response, correlation_id)
        return response


def _request_correlation_id(request: Request) -> str:
    correlation_id: object = getattr(request.state, "correlation_id", None)
    if isinstance(correlation_id, str):
        return correlation_id
    generated = str(uuid4())
    request.state.correlation_id = generated
    return generated


def _set_common_response_headers(response: Response, correlation_id: str) -> None:
    response.headers[WEB_CORRELATION_HEADER_NAME] = correlation_id
    response.headers[WEB_CSP_HEADER_NAME] = WEB_CONTENT_SECURITY_POLICY
    response.headers[WEB_CONTENT_TYPE_OPTIONS_HEADER_NAME] = WEB_CONTENT_TYPE_OPTIONS_VALUE
    response.headers[WEB_REFERRER_POLICY_HEADER_NAME] = WEB_REFERRER_POLICY
    response.headers[WEB_FRAME_OPTIONS_HEADER_NAME] = WEB_FRAME_OPTIONS


def _api_failure(
    status_code: int,
    code: ApiErrorCode,
    message: str,
    *,
    field: str | None = None,
) -> JSONResponse:
    error = (
        ApiError(
            code=code,
            message=message,
            field=field,
            retryable=status_code >= HTTP_INTERNAL_ERROR_STATUS,
        )
        if field is not None
        else ApiError(
            code=code,
            message=message,
            retryable=status_code >= HTTP_INTERNAL_ERROR_STATUS,
        )
    )
    envelope = ApiFailureEnvelope(
        data=None,
        errors=(error,),
    )
    return JSONResponse(envelope.model_dump(mode="json"), status_code=status_code)


def _validation_field(exc: RequestValidationError) -> str | None:
    errors = cast("list[dict[str, object]]", exc.errors())
    if not errors:
        return None
    location = errors[0].get("loc")
    if not isinstance(location, tuple):
        return None
    location_parts = cast("tuple[object, ...]", location)
    return ".".join(str(part) for part in location_parts)


def _asset_response(web_dist: Path, asset_path: str) -> Response:
    if _is_rejected_path(asset_path) or not is_hashed_asset_name(PurePosixPath(asset_path).name):
        return PlainTextResponse(WEB_STATIC_ASSET_NOT_FOUND_MESSAGE, status_code=HTTP_NOT_FOUND_STATUS)
    asset_root = (web_dist / WEB_STATIC_ASSET_ROUTE.removeprefix("/")).resolve()
    asset_file = (asset_root / asset_path).resolve()
    if not asset_file.is_relative_to(asset_root) or not asset_file.is_file():
        return PlainTextResponse(WEB_STATIC_ASSET_NOT_FOUND_MESSAGE, status_code=HTTP_NOT_FOUND_STATUS)
    return FileResponse(asset_file, headers={"Cache-Control": WEB_ASSET_CACHE_CONTROL})


def _ui_response(web_dist: Path, ui_path: str, request: Request) -> Response:
    request_path = request.url.path
    if _is_api_path(request_path):
        return _api_failure(HTTP_NOT_FOUND_STATUS, ApiErrorCode.API_NOT_FOUND, WEB_API_NOT_FOUND_MESSAGE)
    if request_path == WEB_STATIC_ASSET_ROUTE or request_path.startswith(f"{WEB_STATIC_ASSET_ROUTE}/"):
        return PlainTextResponse(WEB_STATIC_ASSET_NOT_FOUND_MESSAGE, status_code=HTTP_NOT_FOUND_STATUS)
    if _is_rejected_path(ui_path) or WEB_HTML_ACCEPT_MEDIA_TYPE not in request.headers.get("accept", "").lower():
        return PlainTextResponse(WEB_UI_NOT_FOUND_MESSAGE, status_code=HTTP_NOT_FOUND_STATUS)
    index_file = web_dist / WEB_STATIC_EXPORT_INDEX_FILE_NAME
    if not index_file.is_file():
        return PlainTextResponse(WEB_STATIC_EXPORT_MISSING_MESSAGE, status_code=HTTP_SERVICE_UNAVAILABLE_STATUS)
    return FileResponse(index_file, headers={"Cache-Control": WEB_INDEX_CACHE_CONTROL})


def _is_api_path(path: str) -> bool:
    return path == WEB_API_PREFIX or path.startswith(f"{WEB_API_PREFIX}/")


def _host_name(host_header: str) -> str | None:
    host, separator, port = host_header.lower().partition(":")
    if not host or (separator and not port.isdecimal()):
        return None
    return host


def _is_known_api_path(app: FastAPI, request_path: str) -> bool:
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "server": ("localhost", 80),
        "client": ("127.0.0.1", 0),
        "scheme": "http",
        "method": "GET",
        "root_path": "",
        "path": request_path,
        "raw_path": request_path.encode("utf-8"),
        "query_string": b"",
        "headers": [],
    }
    for route in app.routes:
        route_path = getattr(route, "path", None)
        if isinstance(route_path, str) and not _is_api_path(route_path):
            continue
        if route_path is None and not hasattr(route, "original_router"):
            continue
        match, _child_scope = route.matches(scope)
        if match in {Match.FULL, Match.PARTIAL}:
            return True
    return False


def _is_rejected_path(path: str) -> bool:
    if "\\" in path:
        return True
    return any(segment in {".", ".."} or segment.startswith(".") for segment in PurePosixPath(path).parts)
