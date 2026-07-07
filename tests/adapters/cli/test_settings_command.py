"""
Summary: Tests settings CLI launcher behavior.
Why: Keeps `omym2 settings` wired without starting a real web server in tests.
"""

from __future__ import annotations

from io import StringIO

from fastapi import FastAPI

from omym2.adapters.cli.commands.settings import (
    SettingsCommandDependencies,
    SettingsCommandPorts,
    run_settings_command,
)
from omym2.config import WEB_DEFAULT_HOST, WEB_DEFAULT_PORT, WEB_SETTINGS_ROUTE

ERROR_EXIT_CODE = 1
SERVER_FAILURE_MESSAGE = "port unavailable"
SUCCESS_EXIT_CODE = 0
USAGE_EXIT_CODE = 2


def test_settings_command_opens_browser_and_runs_server() -> None:
    """The settings command opens the local URL and starts the supplied server runner."""
    stdout = StringIO()
    stderr = StringIO()
    opened_urls: list[str] = []
    served: list[tuple[str, int]] = []

    def open_browser(url: str) -> bool:
        opened_urls.append(url)
        return True

    def run_server(app: object, host: str, port: int) -> None:
        _ = app
        served.append((host, port))

    exit_code = run_settings_command(
        (),
        stdout,
        stderr,
        SettingsCommandPorts(web_app_factory=FastAPI),
        dependencies=SettingsCommandDependencies(browser_opener=open_browser, server_runner=run_server),
    )

    expected_url = f"http://{WEB_DEFAULT_HOST}:{WEB_DEFAULT_PORT}{WEB_SETTINGS_ROUTE}"
    assert exit_code == SUCCESS_EXIT_CODE
    assert opened_urls == [expected_url]
    assert served == [(WEB_DEFAULT_HOST, WEB_DEFAULT_PORT)]
    assert expected_url in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_settings_command_rejects_arguments() -> None:
    """The settings command does not accept positional arguments."""
    stdout = StringIO()
    stderr = StringIO()

    exit_code = run_settings_command(("unexpected",), stdout, stderr, SettingsCommandPorts(web_app_factory=FastAPI))

    assert exit_code == USAGE_EXIT_CODE
    assert stdout.getvalue() == ""
    assert "Usage: omym2 settings" in stderr.getvalue()


def test_settings_command_reports_server_start_failure() -> None:
    """Server startup errors are returned as command failures."""
    stdout = StringIO()
    stderr = StringIO()

    def fail_server(app: object, host: str, port: int) -> None:
        _ = (app, host, port)
        raise OSError(SERVER_FAILURE_MESSAGE)

    exit_code = run_settings_command(
        (),
        stdout,
        stderr,
        SettingsCommandPorts(web_app_factory=FastAPI),
        dependencies=SettingsCommandDependencies(browser_opener=lambda _: True, server_runner=fail_server),
    )

    assert exit_code == ERROR_EXIT_CODE
    assert "Settings server error: port unavailable" in stderr.getvalue()
