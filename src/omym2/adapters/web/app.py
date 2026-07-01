"""
Summary: Builds the local Web UI application.
Why: Wires React and JSON API routes to feature usecases without involving CLI code.
"""

from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.config.toml_config_store import TomlConfigStore
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.adapters.fs.file_scanner import FilesystemFileScanner
from omym2.adapters.fs.file_snapshot_reader import FilesystemFileSnapshotReader
from omym2.adapters.fs.path_resolver import FilesystemPathResolver
from omym2.adapters.metadata.mutagen_reader import MutagenMetadataReader
from omym2.adapters.web.routes.api import ApiRouteContext, create_api_router
from omym2.config import (
    WEB_APP_TITLE,
    WEB_CHECK_ROUTE,
    WEB_CSRF_TOKEN_BYTES,
    WEB_HISTORY_ROUTE,
    WEB_NEXT_STATIC_DIRECTORY_NAME,
    WEB_NEXT_STATIC_ROUTE,
    WEB_PATH_POLICY_ROUTE,
    WEB_ROOT_ROUTE,
    WEB_RUN_DETAIL_ROUTE,
    WEB_SETTINGS_ROUTE,
    WEB_STATIC_ASSET_NOT_FOUND_MESSAGE,
    WEB_STATIC_EXPORT_DIRECTORY_NAME,
    WEB_STATIC_EXPORT_INDEX_FILE_NAME,
    WEB_STATIC_EXPORT_MISSING_MESSAGE,
    WEB_TRACKS_ROUTE,
)
from omym2.features.check.ports import CheckLibraryPorts
from omym2.features.history.ports import HistoryPorts
from omym2.features.settings.ports import SettingsPorts
from omym2.features.tracks.ports import TracksPorts


def create_web_app(
    config_path: Path | None = None,
    database_path: Path | None = None,
    static_dist_path: Path | None = None,
) -> FastAPI:
    """Create the localhost Web UI application."""
    package_dir = Path(__file__).resolve().parent
    web_dist = static_dist_path or package_dir / WEB_STATIC_EXPORT_DIRECTORY_NAME
    app_paths = default_application_paths()
    config_file = config_path or app_paths.config_file
    database_file = database_path or app_paths.database_file
    store = TomlConfigStore(config_file)

    app = FastAPI(title=WEB_APP_TITLE)
    app.include_router(
        create_api_router(
            ApiRouteContext(
                check_ports_factory=lambda: CheckLibraryPorts(
                    uow=SQLiteUnitOfWork(database_file),
                    file_scanner=FilesystemFileScanner(),
                    file_snapshot_reader=FilesystemFileSnapshotReader(metadata_reader=MutagenMetadataReader()),
                    config_store=store,
                    path_resolver=FilesystemPathResolver(),
                ),
                csrf_token=secrets.token_urlsafe(WEB_CSRF_TOKEN_BYTES),
                history_ports_factory=lambda: HistoryPorts(uow=SQLiteUnitOfWork(database_file)),
                settings_ports=SettingsPorts(config_store=store),
                tracks_ports_factory=lambda: TracksPorts(uow=SQLiteUnitOfWork(database_file)),
            )
        )
    )

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
    ):
        app.add_api_route(route, serve_spa, methods=["GET"], include_in_schema=False)

    app.add_api_route("/{asset_path:path}", serve_static_asset, methods=["GET"], include_in_schema=False)

    return app
