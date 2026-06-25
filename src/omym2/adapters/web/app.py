"""
Summary: Builds the local Web UI application.
Why: Wires browser routes to settings usecases without involving CLI code.
"""

from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.config.toml_config_store import TomlConfigStore
from omym2.adapters.web.routes.settings import SettingsRouteContext, create_settings_router
from omym2.config import (
    WEB_APP_TITLE,
    WEB_CSRF_TOKEN_BYTES,
    WEB_ROOT_ROUTE,
    WEB_SETTINGS_ROUTE,
    WEB_STATIC_DIRECTORY_NAME,
    WEB_STATIC_ROUTE,
    WEB_TEMPLATE_DIRECTORY_NAME,
)
from omym2.features.settings.ports import SettingsPorts


def create_web_app(config_path: Path | None = None) -> FastAPI:
    """Create the localhost settings console application."""
    package_dir = Path(__file__).resolve().parent
    templates = Jinja2Templates(directory=str(package_dir / WEB_TEMPLATE_DIRECTORY_NAME))
    store = TomlConfigStore(config_path or default_application_paths().config_file)

    app = FastAPI(title=WEB_APP_TITLE)
    app.mount(
        WEB_STATIC_ROUTE,
        StaticFiles(directory=package_dir / WEB_STATIC_DIRECTORY_NAME),
        name=WEB_STATIC_DIRECTORY_NAME,
    )
    app.include_router(
        create_settings_router(
            SettingsRouteContext(
                csrf_token=secrets.token_urlsafe(WEB_CSRF_TOKEN_BYTES),
                ports=SettingsPorts(config_store=store),
                templates=templates,
            )
        )
    )

    def redirect_to_settings() -> RedirectResponse:
        """Send the local console root to the settings screen."""
        return RedirectResponse(WEB_SETTINGS_ROUTE)

    app.add_api_route(WEB_ROOT_ROUTE, redirect_to_settings, methods=["GET"], include_in_schema=False)

    return app
