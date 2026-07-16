"""
Summary: Tests the real desktop Uvicorn adapter against the composed FastAPI application.
Why: Proves the native server path preserves the packaged SPA, JSON API, and HTTP protections.
"""

from __future__ import annotations

import json
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from http.client import HTTPConnection
from threading import Event
from typing import TYPE_CHECKING, cast
from uuid import UUID

import pytest

from omym2.adapters.desktop.server import UvicornDesktopServer
from omym2.adapters.web.app import create_web_app
from omym2.config import (
    DESKTOP_LOOPBACK_HOST,
    HTTP_FORBIDDEN_STATUS,
    HTTP_OK_STATUS,
    OPERATION_RECONCILE_INTERVAL_SECONDS,
    OPERATION_WORKER_COUNT,
    WEB_API_BOOTSTRAP_ROUTE,
    WEB_API_CHECK_RUN_ROUTE,
    WEB_CONTENT_SECURITY_POLICY,
    WEB_CORRELATION_HEADER_NAME,
    WEB_CSP_HEADER_NAME,
    WEB_HTML_ACCEPT_MEDIA_TYPE,
    WEB_STATIC_ASSET_ROUTE,
)
from omym2.domain.models.operation import CheckCompletedResult, Operation, OperationStatus
from omym2.features.check.dto import CheckLibraryRequest, CheckLibraryResult
from omym2.features.check.usecases.check_library import CheckLibraryUseCase
from omym2.platform.web_composition import build_api_route_context, build_web_app
from omym2.shared.ids import CheckRunId

if TYPE_CHECKING:
    from pathlib import Path

HASHED_ASSET_FILE_NAME = "desktop-shell-12345678.js"
INDEX_CONTENT = "<!doctype html><html><body>OMYM2 Desktop</body></html>"
ASSET_CONTENT = "window.__OMYM2_DESKTOP__ = true;"
CHECKED_AT = datetime(2026, 7, 14, tzinfo=UTC)
CHECK_RUN_ID = CheckRunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345603"))
IDEMPOTENCY_KEY = UUID("018f6a4f-3c2d-7b8a-9abc-def012345604")


def test_real_desktop_server_serves_existing_ui_api_and_security_contract(tmp_path: Path) -> None:
    """The desktop path is the normal production FastAPI app on a dynamic private listener."""
    static_dist = tmp_path / "static_dist"
    assets = static_dist / WEB_STATIC_ASSET_ROUTE.removeprefix("/")
    assets.mkdir(parents=True)
    _ = (static_dist / "index.html").write_text(INDEX_CONTENT, encoding="utf-8")
    _ = (assets / HASHED_ASSET_FILE_NAME).write_text(ASSET_CONTENT, encoding="utf-8")
    config_file = tmp_path / ".config" / "config.toml"
    database_file = tmp_path / ".data" / "omym2.sqlite3"
    app = build_web_app(config_file, database_file, static_dist_path=static_dist)
    server = UvicornDesktopServer(app)
    url = server.start()
    port = server.port
    assert port is not None

    try:
        root_status, root_headers, root_body = _request(
            port, "GET", "/", headers={"Accept": WEB_HTML_ACCEPT_MEDIA_TYPE}
        )
        deep_status, _deep_headers, deep_body = _request(
            port,
            "GET",
            "/plans/019f0000-0000-7000-8000-000000000001",
            headers={"Accept": WEB_HTML_ACCEPT_MEDIA_TYPE},
        )
        asset_status, _asset_headers, asset_body = _request(
            port,
            "GET",
            f"{WEB_STATIC_ASSET_ROUTE}/{HASHED_ASSET_FILE_NAME}",
        )
        bootstrap_status, _bootstrap_headers, bootstrap_body = _request(port, "GET", WEB_API_BOOTSTRAP_ROUTE)
        csrf_status, _csrf_headers, _csrf_body = _request(
            port,
            "POST",
            WEB_API_CHECK_RUN_ROUTE,
            body=b"{}",
            headers={"Content-Type": "application/json"},
        )
    finally:
        server.stop()

    assert url == f"http://{DESKTOP_LOOPBACK_HOST}:{port}/"
    assert root_status == HTTP_OK_STATUS
    assert root_body.decode() == INDEX_CONTENT
    assert deep_status == HTTP_OK_STATUS
    assert deep_body.decode() == INDEX_CONTENT
    assert asset_status == HTTP_OK_STATUS
    assert asset_body.decode() == ASSET_CONTENT
    assert bootstrap_status == HTTP_OK_STATUS
    bootstrap_payload = cast("object", json.loads(bootstrap_body))
    assert isinstance(bootstrap_payload, dict)
    typed_bootstrap_payload = cast("dict[str, object]", bootstrap_payload)
    assert isinstance(typed_bootstrap_payload.get("data"), dict)
    assert csrf_status == HTTP_FORBIDDEN_STATUS
    assert root_headers[WEB_CSP_HEADER_NAME.lower()] == WEB_CONTENT_SECURITY_POLICY
    assert root_headers[WEB_CORRELATION_HEADER_NAME.lower()]

    with pytest.raises(ConnectionRefusedError):
        _ = _request(port, "GET", WEB_API_BOOTSTRAP_ROUTE)


def test_server_shutdown_waits_for_accepted_operation_to_finish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Window-close shutdown keeps the worker alive until its durable Operation is terminal."""
    work_started = Event()
    release_work = Event()
    shutdown_started = Event()

    def blocking_check(_usecase: CheckLibraryUseCase, _request: CheckLibraryRequest) -> CheckLibraryResult:
        work_started.set()
        _ = release_work.wait()
        return CheckLibraryResult(issues=(), checked_at=CHECKED_AT, check_run_ids=(CHECK_RUN_ID,))

    monkeypatch.setattr(CheckLibraryUseCase, "execute", blocking_check)
    config_file = tmp_path / ".config" / "config.toml"
    database_file = tmp_path / ".data" / "omym2.sqlite3"
    context = build_api_route_context(config_file, database_file)
    close_runtime = context.close_runtime
    assert close_runtime is not None

    def close_runtime_after_marking() -> None:
        shutdown_started.set()
        close_runtime()

    app = create_web_app(replace(context, close_runtime=close_runtime_after_marking), tmp_path / "missing-static")
    server = UvicornDesktopServer(app)
    _ = server.start()
    stop_executor: ThreadPoolExecutor | None = None
    stop_future: Future[None] | None = None
    try:
        operations = context.operations
        assert operations is not None
        accepted = operations.start_check(CheckLibraryRequest(trust_stat=False), IDEMPOTENCY_KEY)
        assert isinstance(accepted.lookup, Operation)
        assert work_started.wait(OPERATION_RECONCILE_INTERVAL_SECONDS)
        stop_executor = ThreadPoolExecutor(max_workers=OPERATION_WORKER_COUNT)
        stop_future = stop_executor.submit(server.stop)
        assert shutdown_started.wait(OPERATION_RECONCILE_INTERVAL_SECONDS)
        assert not stop_future.done()
    finally:
        release_work.set()
        if stop_executor is None:
            server.stop()
        else:
            stop_executor.shutdown(wait=True)

    assert stop_future is not None
    stop_future.result()
    operation = operations.get_operation(accepted.lookup.operation_id)
    assert operation.status is OperationStatus.SUCCEEDED
    assert operation.result == CheckCompletedResult(check_run_ids=(CHECK_RUN_ID,), issue_count=0)


def _request(
    port: int,
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    connection = HTTPConnection(DESKTOP_LOOPBACK_HOST, port)
    try:
        connection.request(method, path, body=body, headers={} if headers is None else headers)
        response = connection.getresponse()
        response_body = response.read()
        response_headers = {name.lower(): value for name, value in response.getheaders()}
        return response.status, response_headers, response_body
    finally:
        connection.close()
