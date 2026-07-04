"""
Summary: Tests React SPA serving from FastAPI.
Why: Verifies browser routes are React entrypoints and APIs stay JSON-only.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from omym2.adapters.web.app import create_web_app
from omym2.config import (
    CONFIG_FILE_ENCODING,
    WEB_API_PREFIX,
    WEB_API_SETTINGS_ROUTE,
    WEB_CHECK_ROUTE,
    WEB_HISTORY_ROUTE,
    WEB_NEXT_STATIC_ROUTE,
    WEB_PATH_POLICY_ROUTE,
    WEB_ROOT_ROUTE,
    WEB_SETTINGS_ROUTE,
    WEB_STATIC_EXPORT_MISSING_MESSAGE,
    WEB_TRACKS_ROUTE,
)

MISSING_BUILD_STATUS_CODE = 503
NOT_FOUND_STATUS_CODE = 404
POST_REMOVED_STATUS_CODE = 405
SUCCESS_STATUS_CODE = 200
DISALLOWED_STATIC_EXPORT_SUFFIXES = (".db", ".key", ".log", ".map", ".pem", ".sqlite", ".sqlite3")
DISALLOWED_STATIC_EXPORT_TEXT = (
    "@vercel/analytics",
    "/_vercel/insights",
    "va.vercel-scripts.com",
    "BEGIN PRIVATE KEY",
    'omym2 add "',
    'omym2 refresh "',
)
STATIC_EXPORT_TEXT_SUFFIXES = (".css", ".html", ".js", ".json", ".svg", ".txt", ".webmanifest", ".xml")


def test_spa_routes_return_react_index(tmp_path: Path) -> None:
    """Known browser routes return the React entry document."""
    static_dist = _static_dist(tmp_path)
    client = TestClient(create_web_app(tmp_path / "config.toml", tmp_path / "omym2.sqlite3", static_dist))

    for route in (
        WEB_ROOT_ROUTE,
        WEB_SETTINGS_ROUTE,
        WEB_PATH_POLICY_ROUTE,
        WEB_HISTORY_ROUTE,
        f"{WEB_HISTORY_ROUTE}/018f6a4f-3c2d-7b8a-9abc-def01234567d",
        WEB_CHECK_ROUTE,
        WEB_TRACKS_ROUTE,
    ):
        response = client.get(route)

        assert response.status_code == SUCCESS_STATUS_CODE
        assert "OMYM2 React Test Shell" in response.text


def test_default_packaged_web_build_is_served() -> None:
    """The committed Next static export is available through the default app factory."""
    client = TestClient(create_web_app())

    response = client.get(WEB_ROOT_ROUTE)

    assert response.status_code == SUCCESS_STATUS_CODE
    assert "OMYM2 Console" in response.text


def test_default_packaged_web_build_excludes_risky_static_artifacts() -> None:
    """Packaged static assets exclude common secret, debug, and analytics artifacts."""
    static_dist = Path(__file__).parents[3] / "src" / "omym2" / "adapters" / "web" / "static_dist"

    for static_file in static_dist.rglob("*"):
        if not static_file.is_file():
            continue
        assert static_file.suffix.lower() not in DISALLOWED_STATIC_EXPORT_SUFFIXES
        if static_file.suffix.lower() not in STATIC_EXPORT_TEXT_SUFFIXES:
            continue
        content = static_file.read_text(encoding=CONFIG_FILE_ENCODING)
        for disallowed_text in DISALLOWED_STATIC_EXPORT_TEXT:
            assert disallowed_text not in content


def test_next_static_assets_are_served_from_web_build(tmp_path: Path) -> None:
    """Next static assets are served separately from SPA entry routes."""
    static_dist = _static_dist(tmp_path)
    client = TestClient(create_web_app(tmp_path / "config.toml", tmp_path / "omym2.sqlite3", static_dist))

    response = client.get(f"{WEB_NEXT_STATIC_ROUTE}/app.js")

    assert response.status_code == SUCCESS_STATUS_CODE
    assert "window.__OMYM2_TEST__" in response.text


def test_root_static_assets_are_served_from_web_build(tmp_path: Path) -> None:
    """Root public files emitted by the static export are served directly."""
    static_dist = _static_dist(tmp_path)
    client = TestClient(create_web_app(tmp_path / "config.toml", tmp_path / "omym2.sqlite3", static_dist))

    response = client.get("/icon.svg")

    assert response.status_code == SUCCESS_STATUS_CODE
    assert "omym2-test-icon" in response.text


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
    assert spa_response.text == WEB_STATIC_EXPORT_MISSING_MESSAGE
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
    assets_dir = static_dist / "_next" / "static"
    assets_dir.mkdir(parents=True)
    _ = (static_dist / "index.html").write_text(
        '<!doctype html><html><body><div id="root">OMYM2 React Test Shell</div></body></html>',
        encoding=CONFIG_FILE_ENCODING,
    )
    _ = (assets_dir / "app.js").write_text("window.__OMYM2_TEST__ = true;", encoding=CONFIG_FILE_ENCODING)
    _ = (static_dist / "icon.svg").write_text("<svg>omym2-test-icon</svg>", encoding=CONFIG_FILE_ENCODING)
    return static_dist
