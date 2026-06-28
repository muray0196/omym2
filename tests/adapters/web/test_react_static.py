"""
Summary: Tests React SPA serving from FastAPI.
Why: Verifies browser routes are React entrypoints and APIs stay JSON-only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from omym2.adapters.web.app import create_web_app
from omym2.config import (
    CONFIG_FILE_ENCODING,
    WEB_API_PREFIX,
    WEB_API_SETTINGS_ROUTE,
    WEB_ASSETS_ROUTE,
    WEB_CHECK_ROUTE,
    WEB_HISTORY_ROUTE,
    WEB_REACT_BUILD_MISSING_MESSAGE,
    WEB_ROOT_ROUTE,
    WEB_SETTINGS_ROUTE,
    WEB_TRACKS_ROUTE,
)

if TYPE_CHECKING:
    from pathlib import Path

MISSING_BUILD_STATUS_CODE = 503
NOT_FOUND_STATUS_CODE = 404
POST_REMOVED_STATUS_CODE = 405
SUCCESS_STATUS_CODE = 200


def test_spa_routes_return_react_index(tmp_path: Path) -> None:
    """Known browser routes return the React entry document."""
    static_dist = _static_dist(tmp_path)
    client = TestClient(create_web_app(tmp_path / "config.toml", tmp_path / "omym2.sqlite3", static_dist))

    for route in (
        WEB_ROOT_ROUTE,
        WEB_SETTINGS_ROUTE,
        WEB_HISTORY_ROUTE,
        f"{WEB_HISTORY_ROUTE}/018f6a4f-3c2d-7b8a-9abc-def01234567d",
        WEB_CHECK_ROUTE,
        WEB_TRACKS_ROUTE,
    ):
        response = client.get(route)

        assert response.status_code == SUCCESS_STATUS_CODE
        assert "OMYM2 React Test Shell" in response.text


def test_default_packaged_react_build_is_served() -> None:
    """The committed Vite build is available through the default app factory."""
    client = TestClient(create_web_app())

    response = client.get(WEB_ROOT_ROUTE)

    assert response.status_code == SUCCESS_STATUS_CODE
    assert '<div id="root"></div>' in response.text


def test_assets_are_served_from_react_build(tmp_path: Path) -> None:
    """Vite assets are served separately from SPA entry routes."""
    static_dist = _static_dist(tmp_path)
    client = TestClient(create_web_app(tmp_path / "config.toml", tmp_path / "omym2.sqlite3", static_dist))

    response = client.get(f"{WEB_ASSETS_ROUTE}/app.js")

    assert response.status_code == SUCCESS_STATUS_CODE
    assert "window.__OMYM2_TEST__" in response.text


def test_api_routes_do_not_fall_through_to_spa(tmp_path: Path) -> None:
    """Unknown API routes return API 404 instead of React index."""
    static_dist = _static_dist(tmp_path)
    client = TestClient(create_web_app(tmp_path / "config.toml", tmp_path / "omym2.sqlite3", static_dist))

    response = client.get(f"{WEB_API_PREFIX}/not-real")

    assert response.status_code == NOT_FOUND_STATUS_CODE
    assert "OMYM2 React Test Shell" not in response.text


def test_missing_react_build_returns_503_without_breaking_api(tmp_path: Path) -> None:
    """Missing built assets fail browser routes clearly while APIs still work."""
    client = TestClient(create_web_app(tmp_path / "config.toml", tmp_path / "omym2.sqlite3", tmp_path / "missing"))

    spa_response = client.get(WEB_SETTINGS_ROUTE)
    api_response = client.get(WEB_API_SETTINGS_ROUTE)

    assert spa_response.status_code == MISSING_BUILD_STATUS_CODE
    assert spa_response.text == WEB_REACT_BUILD_MISSING_MESSAGE
    assert api_response.status_code == SUCCESS_STATUS_CODE
    assert api_response.json()["config"]["version"] == 1


def test_old_settings_post_route_is_removed(tmp_path: Path) -> None:
    """The server-rendered settings form POST is intentionally gone."""
    static_dist = _static_dist(tmp_path)
    client = TestClient(create_web_app(tmp_path / "config.toml", tmp_path / "omym2.sqlite3", static_dist))

    response = client.post(WEB_SETTINGS_ROUTE, data={"form_action": "save"})

    assert response.status_code == POST_REMOVED_STATUS_CODE


def _static_dist(tmp_path: Path) -> Path:
    static_dist = tmp_path / "static_dist"
    assets_dir = static_dist / "assets"
    assets_dir.mkdir(parents=True)
    _ = (static_dist / "index.html").write_text(
        '<!doctype html><html><body><div id="root">OMYM2 React Test Shell</div></body></html>',
        encoding=CONFIG_FILE_ENCODING,
    )
    _ = (assets_dir / "app.js").write_text("window.__OMYM2_TEST__ = true;", encoding=CONFIG_FILE_ENCODING)
    return static_dist
