"""
Summary: Implements the settings Web UI launcher command.
Why: Gives users the documented `omym2 settings` entry point.
"""

from __future__ import annotations

import webbrowser
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, TextIO
from urllib.parse import urlunparse

from omym2.adapters.cli.commands.output import write_line, write_usage
from omym2.config import WEB_DEFAULT_HOST, WEB_DEFAULT_PORT, WEB_SETTINGS_ROUTE, WEB_URL_SCHEME

if TYPE_CHECKING:
    from fastapi import FastAPI

ERROR_EXIT_CODE = 1
SETTINGS_USAGE_MESSAGE = "Usage: omym2 settings"
SUCCESS_EXIT_CODE = 0
USAGE_EXIT_CODE = 2

type BrowserOpener = Callable[[str], bool]
type ServerRunner = Callable[["FastAPI", str, int], None]


def _run_server(app: FastAPI, host: str, port: int) -> None:
    import uvicorn  # noqa: PLC0415  # Intentional settings-only server import.

    uvicorn.run(app, host=host, port=port)


@dataclass(frozen=True, slots=True)
class SettingsCommandDependencies:
    """Overridable side effects for launching the settings console."""

    browser_opener: BrowserOpener = webbrowser.open
    server_runner: ServerRunner = _run_server


@dataclass(frozen=True, slots=True)
class SettingsCommandPorts:
    """Ports needed to build the settings Web UI application."""

    web_app_factory: Callable[[], FastAPI]


def run_settings_command(
    args: Sequence[str],
    stdout: TextIO,
    stderr: TextIO,
    ports: SettingsCommandPorts,
    dependencies: SettingsCommandDependencies | None = None,
) -> int:
    """Run the local settings console until the server stops."""
    if args:
        write_usage(stderr, SETTINGS_USAGE_MESSAGE)
        return USAGE_EXIT_CODE

    command_dependencies = SettingsCommandDependencies() if dependencies is None else dependencies
    settings_url = _settings_url(WEB_DEFAULT_HOST, WEB_DEFAULT_PORT)
    _ = command_dependencies.browser_opener(settings_url)
    write_line(stdout, f"Settings console: {settings_url}")

    try:
        command_dependencies.server_runner(ports.web_app_factory(), WEB_DEFAULT_HOST, WEB_DEFAULT_PORT)
    except OSError as exc:
        write_line(stderr, f"Settings server error: {exc}")
        return ERROR_EXIT_CODE
    return SUCCESS_EXIT_CODE


def _settings_url(host: str, port: int) -> str:
    return urlunparse((WEB_URL_SCHEME, f"{host}:{port}", WEB_SETTINGS_ROUTE, "", "", ""))
