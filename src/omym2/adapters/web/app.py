"""
Summary: Builds the local Web UI application.
Why: Wires React and JSON API routes to feature usecases without involving CLI code.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.routing import Match

from omym2.adapters.web.routes.api import ApiRouteContext, create_api_router
from omym2.config import (
    WEB_API_NOT_FOUND_MESSAGE,
    WEB_API_PREFIX,
    WEB_APP_TITLE,
    WEB_CHECK_ROUTE,
    WEB_HISTORY_ROUTE,
    WEB_NEXT_STATIC_DIRECTORY_NAME,
    WEB_NEXT_STATIC_ROUTE,
    WEB_PATH_POLICY_ROUTE,
    WEB_PLAN_DETAIL_ROUTE,
    WEB_PLANS_ROUTE,
    WEB_ROOT_ROUTE,
    WEB_RUN_DETAIL_ROUTE,
    WEB_SETTINGS_ROUTE,
    WEB_STATIC_ASSET_NOT_FOUND_MESSAGE,
    WEB_STATIC_EXPORT_DIRECTORY_NAME,
    WEB_STATIC_EXPORT_INDEX_FILE_NAME,
    WEB_STATIC_EXPORT_MISSING_MESSAGE,
    WEB_TRACKS_ROUTE,
)


def create_web_app(context: ApiRouteContext, static_dist_path: Path | None = None) -> FastAPI:
    """Create the localhost Web UI application from a pre-built API route context."""
    package_dir = Path(__file__).resolve().parent
    web_dist = static_dist_path or package_dir / WEB_STATIC_EXPORT_DIRECTORY_NAME

    app = FastAPI(title=WEB_APP_TITLE)
    app.include_router(create_api_router(context))

    @app.exception_handler(StarletteHTTPException)
    async def handle_api_route_exception(  # pyright: ignore[reportUnusedFunction]  # FastAPI calls decorator-registered handlers.
        request: Request, exc: StarletteHTTPException
    ) -> Response:
        """Return the API 404 envelope for method misses on unknown API paths."""
        # Starlette reports non-GET requests against the later static catch-all as
        # 405s. Remap only unregistered API paths so known API method errors stay
        # unchanged.
        if exc.status_code in {404, 405} and _is_unknown_api_path(app, request.url.path):
            return _api_not_found_response()
        return await http_exception_handler(request, exc)

    next_static_directory = web_dist / WEB_NEXT_STATIC_DIRECTORY_NAME
    if next_static_directory.exists():
        app.mount(
            WEB_NEXT_STATIC_ROUTE,
            StaticFiles(directory=next_static_directory),
            name="next_static",
        )

    def serve_spa() -> Response:
        """Return the Web UI entry document for known UI routes."""
        index_file = web_dist / WEB_STATIC_EXPORT_INDEX_FILE_NAME
        if not index_file.is_file():
            return PlainTextResponse(WEB_STATIC_EXPORT_MISSING_MESSAGE, status_code=503)
        return FileResponse(index_file)

    def serve_static_asset(asset_path: str) -> Response:
        """Return root-level files emitted by the static Web UI export."""
        api_route = WEB_API_PREFIX.removeprefix("/")
        # Keep SPA static fallback for browser routes, but send JSON API shape for unknown API paths.
        if asset_path == api_route or asset_path.startswith(f"{api_route}/"):
            return _api_not_found_response()
        static_file = (web_dist / asset_path).resolve()
        web_dist_root = web_dist.resolve()
        if not static_file.is_relative_to(web_dist_root) or not static_file.is_file():
            return PlainTextResponse(WEB_STATIC_ASSET_NOT_FOUND_MESSAGE, status_code=404)
        return FileResponse(static_file)

    for route in (
        WEB_ROOT_ROUTE,
        WEB_SETTINGS_ROUTE,
        WEB_PATH_POLICY_ROUTE,
        WEB_HISTORY_ROUTE,
        WEB_RUN_DETAIL_ROUTE,
        WEB_CHECK_ROUTE,
        WEB_TRACKS_ROUTE,
        WEB_PLANS_ROUTE,
        WEB_PLAN_DETAIL_ROUTE,
    ):
        app.add_api_route(route, serve_spa, methods=["GET"], include_in_schema=False)

    app.add_api_route("/{asset_path:path}", serve_static_asset, methods=["GET"], include_in_schema=False)

    return app


def _api_not_found_response() -> JSONResponse:
    """Return the stable Web API route-miss envelope."""
    return JSONResponse({"detail": None, "errors": [WEB_API_NOT_FOUND_MESSAGE]}, status_code=404)


def _is_unknown_api_path(app: FastAPI, request_path: str) -> bool:
    """Return whether a request path is under the API prefix but unregistered."""
    if not _is_api_path(request_path):
        return False

    scope = {"type": "http", "path": request_path, "method": "GET", "root_path": ""}
    for route in app.routes:
        route_path = getattr(route, "path", None)
        if isinstance(route_path, str) and not _is_api_path(route_path):
            continue
        # FastAPI stores included API routers as route containers without a path.
        if route_path is None and not hasattr(route, "original_router"):
            continue
        match, _child_scope = route.matches(scope)
        if match in {Match.FULL, Match.PARTIAL}:
            return False
    return True


def _is_api_path(path: str) -> bool:
    """Return whether a route or request path belongs to the JSON API."""
    return path == WEB_API_PREFIX or path.startswith(f"{WEB_API_PREFIX}/")
