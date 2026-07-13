"""
Summary: Tests production serving for the packaged Vite SPA.
Why: Keeps API, hashed assets, and HTML fallback isolated and securely cached.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from fastapi.testclient import TestClient

from omym2.adapters.config.default_config import default_app_config
from omym2.adapters.web.app import create_web_app
from omym2.adapters.web.routes.api_context import ApiRouteContext
from omym2.config import (
    HTTP_BAD_REQUEST_STATUS,
    HTTP_INTERNAL_ERROR_STATUS,
    HTTP_METHOD_NOT_ALLOWED_STATUS,
    HTTP_NOT_FOUND_STATUS,
    HTTP_OK_STATUS,
    HTTP_SERVICE_UNAVAILABLE_STATUS,
    WEB_API_BOOTSTRAP_ROUTE,
    WEB_ASSET_CACHE_CONTROL,
    WEB_CONTENT_SECURITY_POLICY,
    WEB_CORRELATION_HEADER_NAME,
    WEB_INDEX_CACHE_CONTROL,
)
from omym2.features.bootstrap.dto import BootstrapCapabilities, BootstrapReason, BootstrapResult
from omym2.features.common_ports import ConfigSnapshot, ConfigSnapshotState

if TYPE_CHECKING:
    from pathlib import Path

HASHED_ASSET_ROUTE = "/assets/app-12345678.js"
HTML_HEADERS = {"Accept": "text/html"}
SENSITIVE_ERROR_DETAIL = "sensitive detail"


def test_root_and_deep_html_routes_serve_no_cache_index(tmp_path: Path) -> None:
    """React Router owns every accepted browser route including unknown paths."""
    client = _client(_static_dist(tmp_path))

    for route in ("/", "/plans/123", "/not-found"):
        response = client.get(route, headers=HTML_HEADERS)
        assert response.status_code == HTTP_OK_STATUS
        assert "Vite Test Shell" in response.text
        assert response.headers["Cache-Control"] == WEB_INDEX_CACHE_CONTROL
        assert response.headers["Content-Security-Policy"] == WEB_CONTENT_SECURITY_POLICY


def test_spa_fallback_requires_explicit_html_accept(tmp_path: Path) -> None:
    """Missing, wildcard, and non-HTML Accept values never receive index HTML."""
    client = _client(_static_dist(tmp_path))

    for headers in ({}, {"Accept": "*/*"}, {"Accept": "application/json"}):
        response = client.get("/deep", headers=headers)
        assert response.status_code == HTTP_NOT_FOUND_STATUS
        assert "Vite Test Shell" not in response.text


def test_only_existing_hashed_assets_are_served_immutably(tmp_path: Path) -> None:
    """The asset namespace neither serves unhashed files nor falls back to HTML."""
    client = _client(_static_dist(tmp_path))

    response = client.get(HASHED_ASSET_ROUTE)
    assert response.status_code == HTTP_OK_STATUS
    assert response.text == "window.__VITE_TEST__ = true;"
    assert response.headers["Cache-Control"] == WEB_ASSET_CACHE_CONTROL

    for route in ("/assets/app.js", "/assets/missing-12345678.js", "/assets"):
        missing = client.get(route, headers=HTML_HEADERS)
        assert missing.status_code == HTTP_NOT_FOUND_STATUS
        assert "Vite Test Shell" not in missing.text


def test_api_routes_never_fall_through_to_spa(tmp_path: Path) -> None:
    """Unknown API paths and known method errors keep typed JSON envelopes."""
    client = _client(_static_dist(tmp_path))

    missing = client.get("/api/not-real", headers=HTML_HEADERS)
    missing_post = client.post("/api/not-real", headers=HTML_HEADERS)
    wrong_method = client.post(WEB_API_BOOTSTRAP_ROUTE, headers=HTML_HEADERS)

    assert missing.status_code == HTTP_NOT_FOUND_STATUS
    missing_payload = cast("dict[str, object]", missing.json())
    missing_errors = missing_payload["errors"]
    assert isinstance(missing_errors, list)
    missing_error = cast("dict[str, object]", missing_errors[0])
    assert missing_error["code"] == "api_not_found"
    assert set(missing_error) == {"code", "message", "retryable"}
    assert missing_post.status_code == HTTP_NOT_FOUND_STATUS
    assert missing_post.json()["errors"][0]["code"] == "api_not_found"
    assert wrong_method.status_code == HTTP_METHOD_NOT_ALLOWED_STATUS
    assert wrong_method.json()["errors"][0]["code"] == "method_not_allowed"


def test_missing_build_keeps_api_available_and_returns_ui_503(tmp_path: Path) -> None:
    """Absent packaged frontend does not disable the JSON API."""
    client = _client(tmp_path / "missing")

    ui_response = client.get("/", headers=HTML_HEADERS)
    api_response = client.get(WEB_API_BOOTSTRAP_ROUTE)

    assert ui_response.status_code == HTTP_SERVICE_UNAVAILABLE_STATUS
    assert api_response.status_code == HTTP_OK_STATUS


def test_non_get_dotfile_and_traversal_ui_requests_are_rejected(tmp_path: Path) -> None:
    """Fallback never accepts unsupported methods or hidden/traversal paths."""
    client = _client(_static_dist(tmp_path))

    assert client.post("/plans", headers=HTML_HEADERS).status_code == HTTP_METHOD_NOT_ALLOWED_STATUS
    assert client.get("/.env", headers=HTML_HEADERS).status_code == HTTP_NOT_FOUND_STATUS
    assert client.get("/%2e%2e/secret", headers=HTML_HEADERS).status_code == HTTP_NOT_FOUND_STATUS


def test_untrusted_host_is_rejected(tmp_path: Path) -> None:
    """Production host validation rejects UI and API requests without leaking route details."""
    app = create_web_app(_context(), _static_dist(tmp_path))
    client = TestClient(app, base_url="http://example.invalid")

    assert client.get("/", headers=HTML_HEADERS).status_code == HTTP_BAD_REQUEST_STATUS
    api_response = client.get(WEB_API_BOOTSTRAP_ROUTE)
    assert api_response.status_code == HTTP_NOT_FOUND_STATUS
    assert api_response.json()["errors"][0]["code"] == "api_not_found"
    assert api_response.headers[WEB_CORRELATION_HEADER_NAME]


def test_unexpected_api_error_is_redacted_and_keeps_common_headers(tmp_path: Path) -> None:
    """Outer error handling preserves correlation and security response headers."""
    context = ApiRouteContext(
        csrf_token="csrf-test",  # noqa: S106  # Deterministic non-secret test value.
        get_bootstrap=_raise_unexpected,
    )
    app = create_web_app(context, _static_dist(tmp_path), allowed_hosts=("testserver",))
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get(WEB_API_BOOTSTRAP_ROUTE)

    assert response.status_code == HTTP_INTERNAL_ERROR_STATUS
    assert response.json()["errors"][0]["code"] == "internal_error"
    assert "sensitive detail" not in response.text
    assert response.headers[WEB_CORRELATION_HEADER_NAME]
    assert response.headers["Content-Security-Policy"] == WEB_CONTENT_SECURITY_POLICY


def _client(static_dist: Path) -> TestClient:
    return TestClient(create_web_app(_context(), static_dist), base_url="http://localhost")


def _context() -> ApiRouteContext:
    return ApiRouteContext(
        csrf_token="csrf-test",  # noqa: S106  # Deterministic non-secret test value.
        get_bootstrap=_bootstrap_result,
    )


def _bootstrap_result() -> BootstrapResult:
    return BootstrapResult(
        config_snapshot=ConfigSnapshot(
            state=ConfigSnapshotState.MISSING,
            config=default_app_config(),
            config_revision="v1:test",
        ),
        config_valid=True,
        active_library=None,
        effective_library_status=None,
        is_library_registered=False,
        is_path_policy_current=False,
        config_reason=None,
        library_reasons=(BootstrapReason.LIBRARY_UNREGISTERED,),
        state_storage_available=True,
        runtime_capabilities=BootstrapCapabilities(
            can_read_state=True,
            can_change_settings=True,
            can_start_operations=False,
            read_state_disabled_reasons=(),
            change_settings_disabled_reasons=(),
            start_operations_disabled_reasons=(BootstrapReason.LIBRARY_UNREGISTERED,),
        ),
        active_operation_id=None,
    )


def _raise_unexpected() -> BootstrapResult:
    raise RuntimeError(SENSITIVE_ERROR_DETAIL)


def _static_dist(tmp_path: Path) -> Path:
    static_dist = tmp_path / "static_dist"
    assets = static_dist / "assets"
    assets.mkdir(parents=True)
    _ = (static_dist / "index.html").write_text(
        "<!doctype html><html><body>Vite Test Shell</body></html>",
        encoding="utf-8",
    )
    _ = (assets / "app-12345678.js").write_text("window.__VITE_TEST__ = true;", encoding="utf-8")
    return static_dist
