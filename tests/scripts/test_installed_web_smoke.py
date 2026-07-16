"""
Summary: Tests installed-package HTTP smoke verification against loopback fixtures.
Why: Keeps package gates independent of HTML copy and source-tree imports.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar, cast, override

import pytest

from omym2.config import (
    WEB_CONTENT_SECURITY_POLICY,
    WEB_CONTENT_TYPE_OPTIONS_HEADER_NAME,
    WEB_CONTENT_TYPE_OPTIONS_VALUE,
    WEB_CORRELATION_HEADER_NAME,
    WEB_CSP_HEADER_NAME,
    WEB_REFERRER_POLICY,
    WEB_REFERRER_POLICY_HEADER_NAME,
)
from scripts.web.run_web_test_server import CHILD_PATH_OVERRIDE_ENVIRONMENT_VARIABLE

PROJECT_ROOT_NOT_FOUND_MESSAGE = "Unable to locate project root from test file."
SMOKE_SCRIPT_RELATIVE_PATH = "scripts/web/smoke_installed_web.py"
SERVER_SCRIPT_RELATIVE_PATH = "scripts/web/run_web_test_server.py"
APPLICATION_ROOT_ENVIRONMENT_VARIABLE = "OMYM2_E2E_APPLICATION_ROOT"
LOOPBACK_HOST = "127.0.0.1"
EPHEMERAL_PORT = 0
SUCCESS_STATUS_CODE = 200
NOT_FOUND_STATUS_CODE = 404
LOCAL_ASSET_REFERENCE = "/assets/app-abcdefgh.js"
ASSET_BODY = b"globalThis.OMYM2 = true;"
BOOTSTRAP_BODY = json.dumps({"data": {}, "errors": []}).encode()
EXPECTED_SECURITY_HEADERS = {
    WEB_CSP_HEADER_NAME: WEB_CONTENT_SECURITY_POLICY,
    WEB_CONTENT_TYPE_OPTIONS_HEADER_NAME: WEB_CONTENT_TYPE_OPTIONS_VALUE,
    WEB_REFERRER_POLICY_HEADER_NAME: WEB_REFERRER_POLICY,
}


class _SmokeFixtureHandler(BaseHTTPRequestHandler):
    include_security_headers: ClassVar[bool] = True
    omitted_correlation_path: ClassVar[str | None] = None
    security_header_overrides: ClassVar[dict[str, str]] = {}
    asset_reference: ClassVar[str] = LOCAL_ASSET_REFERENCE

    def do_GET(self) -> None:
        if self.path == "/" or self.path.startswith("/plans/"):
            index_html = (
                '<!doctype html><html lang="en"><body><script type="module" '
                f'src="{self.asset_reference}"></script></body></html>'
            ).encode()
            self._respond(index_html, "text/html; charset=utf-8", "no-cache")
        elif self.path == LOCAL_ASSET_REFERENCE:
            self._respond(
                ASSET_BODY,
                "text/javascript; charset=utf-8",
                "public, max-age=31536000, immutable",
            )
        elif self.path == "/api/bootstrap":
            self._respond(BOOTSTRAP_BODY, "application/json", "no-cache")
        else:
            self.send_error(NOT_FOUND_STATUS_CODE)

    @override
    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def _respond(self, body: bytes, content_type: str, cache_control: str) -> None:
        self.send_response(SUCCESS_STATUS_CODE)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", cache_control)
        if self.include_security_headers:
            security_headers = EXPECTED_SECURITY_HEADERS | self.security_header_overrides
            for header, value in security_headers.items():
                self.send_header(header, value)
            if self.path != self.omitted_correlation_path:
                self.send_header(WEB_CORRELATION_HEADER_NAME, "01912345-6789-7abc-8def-0123456789ab")
        self.end_headers()
        _ = self.wfile.write(body)


class _ExternalRequestRecorder(BaseHTTPRequestHandler):
    request_count: ClassVar[int] = 0

    def do_GET(self) -> None:
        type(self).request_count += 1
        self.send_response(SUCCESS_STATUS_CODE)
        self.end_headers()
        _ = self.wfile.write(ASSET_BODY)

    @override
    def log_message(self, format: str, *args: object) -> None:
        del format, args


def test_installed_web_smoke_accepts_contract_responses() -> None:
    """Root, deep fallback, hashed asset, and Bootstrap pass without copy assertions."""
    result = _run_against_fixture(include_security_headers=True)

    assert result.returncode == 0, result.stderr
    assert "package smoke passed" in result.stdout


def test_installed_web_smoke_rejects_missing_security_headers() -> None:
    """A package missing the production header baseline cannot pass smoke."""
    result = _run_against_fixture(include_security_headers=False)

    assert result.returncode != 0
    assert "missing security headers" in result.stderr


def test_installed_web_smoke_rejects_mismatched_security_header() -> None:
    """Present but weakened headers cannot satisfy the backend-defined baseline."""
    result = _run_against_fixture(
        include_security_headers=True,
        security_header_overrides={WEB_CSP_HEADER_NAME: "default-src 'none'"},
    )

    assert result.returncode != 0
    assert "unexpected security headers" in result.stderr


@pytest.mark.parametrize(
    "omitted_correlation_path",
    ["/", "/plans/01912345-6789-7abc-8def-0123456789ab", LOCAL_ASSET_REFERENCE, "/api/bootstrap"],
)
def test_installed_web_smoke_rejects_response_without_correlation_id(omitted_correlation_path: str) -> None:
    """HTML, deep-link, asset, and API responses all retain diagnostic correlation IDs."""
    result = _run_against_fixture(
        include_security_headers=True,
        omitted_correlation_path=omitted_correlation_path,
    )

    assert result.returncode != 0
    assert "x-omym2-correlation-id" in result.stderr


def test_installed_web_smoke_rejects_external_asset_without_requesting_it() -> None:
    """A discovered absolute asset URL fails before any cross-origin connection."""
    _ExternalRequestRecorder.request_count = 0
    external_server = ThreadingHTTPServer((LOOPBACK_HOST, EPHEMERAL_PORT), _ExternalRequestRecorder)
    external_thread = threading.Thread(target=external_server.serve_forever, daemon=True)
    external_thread.start()
    try:
        external_host, external_port = cast("tuple[str, int]", external_server.server_address)
        external_reference = f"http://{external_host}:{external_port}{LOCAL_ASSET_REFERENCE}"

        result = _run_against_fixture(
            include_security_headers=True,
            asset_reference=external_reference,
        )

        assert result.returncode != 0
        assert "non-package-relative asset reference" in result.stderr
        assert _ExternalRequestRecorder.request_count == 0
    finally:
        external_server.shutdown()
        external_server.server_close()
        external_thread.join()


def test_installed_web_smoke_rejects_non_loopback_url() -> None:
    """The smoke command cannot be redirected to an external server."""
    result = subprocess.run(  # noqa: S603 -- fixed argv invokes this repository's own script.
        (sys.executable, SMOKE_SCRIPT_RELATIVE_PATH, "--base-url", "https://example.com"),
        cwd=_project_root(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "loopback HTTP" in result.stderr


def test_ephemeral_server_runner_requires_a_command() -> None:
    """The server runner fails before starting application state when no gate is supplied."""
    result = subprocess.run(  # noqa: S603 -- fixed argv invokes this repository's own script.
        (sys.executable, SERVER_SCRIPT_RELATIVE_PATH),
        cwd=_project_root(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "command is required" in result.stderr.lower()


def test_ephemeral_server_runner_seeds_registered_library_state() -> None:
    """Browser gates receive temp Config, SQLite, and deterministic file fixtures."""
    probe = (
        "import os, pathlib; "
        f"root=pathlib.Path(os.environ['{APPLICATION_ROOT_ENVIRONMENT_VARIABLE}']); "
        "assert (root/'.config/config.toml').is_file(); "
        "assert str(root/'library') in (root/'.config/config.toml').read_text(); "
        "assert (root/'library/sentinel.flac').read_bytes(); "
        "assert (root/'incoming/A-Success.flac').read_bytes(); "
        "assert (root/'incoming/Z-Failure.flac').read_bytes(); "
        "database=(root/'.data/omym2.sqlite3').read_bytes(); "
        "assert b'01912345-6789-7abc-8def-0123456789ab' in database"
    )

    result = _run_server_command(probe)

    assert result.returncode == 0, result.stderr


def test_ephemeral_server_runner_allows_isolated_m4_library_mutation() -> None:
    """Browser flows may mutate only the runner's disposable Library tree."""
    mutation = (
        "import os, pathlib; "
        f"root=pathlib.Path(os.environ['{APPLICATION_ROOT_ENVIRONMENT_VARIABLE}']); "
        "(root/'library/sentinel.flac').write_bytes(b'changed')"
    )

    result = _run_server_command(mutation)

    assert result.returncode == 0, result.stderr


def test_ephemeral_server_runner_can_restore_node_path_only_for_the_child() -> None:
    """Performance drivers may receive Node while the installed server process remains poisoned."""
    expected_child_path = "child-only-path"
    environment = os.environ.copy()
    environment["PATH"] = "server-no-node-path"
    environment[CHILD_PATH_OVERRIDE_ENVIRONMENT_VARIABLE] = expected_child_path

    result = _run_server_command(
        f"import os; assert os.environ['PATH'] == {expected_child_path!r}",
        environment=environment,
    )

    assert result.returncode == 0, result.stderr


def _run_against_fixture(
    *,
    include_security_headers: bool,
    omitted_correlation_path: str | None = None,
    security_header_overrides: dict[str, str] | None = None,
    asset_reference: str = LOCAL_ASSET_REFERENCE,
) -> subprocess.CompletedProcess[str]:
    handler = type(
        "ConfiguredSmokeFixtureHandler",
        (_SmokeFixtureHandler,),
        {
            "include_security_headers": include_security_headers,
            "omitted_correlation_path": omitted_correlation_path,
            "security_header_overrides": security_header_overrides or {},
            "asset_reference": asset_reference,
        },
    )
    server = ThreadingHTTPServer((LOOPBACK_HOST, EPHEMERAL_PORT), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = cast("tuple[str, int]", server.server_address)
        return subprocess.run(  # noqa: S603 -- fixed argv invokes this repository's own script.
            (sys.executable, SMOKE_SCRIPT_RELATIVE_PATH, "--base-url", f"http://{host}:{port}"),
            cwd=_project_root(),
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def _run_server_command(
    code: str,
    *,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- fixed argv invokes this repository's own server runner.
        (
            sys.executable,
            SERVER_SCRIPT_RELATIVE_PATH,
            "--",
            sys.executable,
            "-c",
            code,
        ),
        cwd=_project_root(),
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError(PROJECT_ROOT_NOT_FOUND_MESSAGE)
