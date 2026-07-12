"""
Summary: Composes the renewed Web Bootstrap API and packaged SPA.
Why: Keeps concrete Config and SQLite adapters out of inbound Web modules.
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from omym2.adapters.db.sqlite.library_snapshot_reader import SQLiteLibrarySnapshotReader
from omym2.adapters.web.app import create_web_app
from omym2.adapters.web.routes.api_context import ApiRouteContext
from omym2.config import WEB_CSRF_TOKEN_BYTES
from omym2.features.bootstrap.ports import BootstrapPorts
from omym2.features.bootstrap.usecases.get_bootstrap import GetBootstrapUseCase
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
