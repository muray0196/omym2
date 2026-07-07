"""
Summary: Builds the Web UI's ApiRouteContext and FastAPI app from a shared RuntimeContext.
Why: Moves Web adapter wiring to the composition root so adapters/web stays free of outbound imports.
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from omym2.adapters.web.app import create_web_app
from omym2.adapters.web.routes.api import ApiRouteContext
from omym2.config import WEB_CSRF_TOKEN_BYTES
from omym2.platform.artist_ids_composition import web_artist_language_detector, web_artist_name_resolver
from omym2.platform.feature_composition import (
    build_check_library_ports,
    build_create_add_plan_ports,
    build_create_organize_plan_ports,
    build_create_refresh_plan_ports,
    build_history_ports,
    build_plan_query_ports,
    build_settings_ports,
    build_tracks_ports,
)
from omym2.platform.runtime_context import runtime_context_for

if TYPE_CHECKING:
    from pathlib import Path

    from fastapi import FastAPI


def build_api_route_context(config_path: Path | None = None, database_path: Path | None = None) -> ApiRouteContext:
    """Build the Web UI's ApiRouteContext from one shared RuntimeContext."""
    runtime = runtime_context_for(config_path, database_path)
    return ApiRouteContext(
        check_ports_factory=lambda: build_check_library_ports(runtime),
        csrf_token=secrets.token_urlsafe(WEB_CSRF_TOKEN_BYTES),
        history_ports_factory=lambda: build_history_ports(runtime),
        plan_query_ports_factory=lambda: build_plan_query_ports(runtime),
        add_plan_ports_factory=lambda: build_create_add_plan_ports(runtime),
        organize_plan_ports_factory=lambda: build_create_organize_plan_ports(runtime),
        refresh_plan_ports_factory=lambda: build_create_refresh_plan_ports(runtime),
        settings_ports=build_settings_ports(runtime),
        tracks_ports_factory=lambda: build_tracks_ports(runtime),
        artist_id_language_detector=web_artist_language_detector(),
        artist_id_name_resolver=web_artist_name_resolver(),
    )


def build_web_app(
    config_path: Path | None = None,
    database_path: Path | None = None,
    static_dist_path: Path | None = None,
) -> FastAPI:
    """Build the localhost Web UI application from optional config, database, and static-dist paths."""
    return create_web_app(build_api_route_context(config_path, database_path), static_dist_path)
