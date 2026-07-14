"""
Summary: Provides the OMYM2 native desktop process entry point.
Why: Composes stable storage, diagnostics, loopback serving, and the native window.
"""

from __future__ import annotations

import logging
import platform as system_platform
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from typing import TYPE_CHECKING, Protocol

from omym2 import __version__
from omym2.adapters.config.application_paths import desktop_application_paths
from omym2.adapters.desktop.server import UvicornDesktopServer
from omym2.adapters.desktop.window import PyWebViewWindow, WindowsErrorDialog
from omym2.config import (
    DESKTOP_FAILURE_EXIT_CODE,
    DESKTOP_LOG_BACKUP_COUNT,
    DESKTOP_LOG_ENCODING,
    DESKTOP_LOG_FORMAT,
    DESKTOP_LOG_LEVEL,
    DESKTOP_LOG_MAX_BYTES,
    DESKTOP_SUCCESS_EXIT_CODE,
    DESKTOP_WINDOW_TITLE,
)
from omym2.platform.desktop_runtime import DesktopRuntime
from omym2.platform.web_composition import build_web_app

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from fastapi import FastAPI

    from omym2.adapters.config.application_paths import ApplicationPaths
    from omym2.platform.desktop_runtime import DesktopServer, DesktopWindow

LOGGER = logging.getLogger(__name__)


class DesktopErrorReporter(Protocol):
    """The user-visible fatal error behavior required by the entry point."""

    def show(self, title: str, message: str) -> None:
        """Display one concise fatal desktop error."""


def _build_desktop_web_app(config_path: Path, database_path: Path) -> FastAPI:
    return build_web_app(config_path=config_path, database_path=database_path)


def _build_desktop_server(app: FastAPI) -> DesktopServer:
    return UvicornDesktopServer(app)


def _build_desktop_window() -> DesktopWindow:
    return PyWebViewWindow()


def configure_desktop_logging(log_file: Path) -> None:
    """Route application and Uvicorn records into a bounded writable desktop log."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_file,
        maxBytes=DESKTOP_LOG_MAX_BYTES,
        backupCount=DESKTOP_LOG_BACKUP_COUNT,
        encoding=DESKTOP_LOG_ENCODING,
    )
    logging.basicConfig(
        level=DESKTOP_LOG_LEVEL,
        format=DESKTOP_LOG_FORMAT,
        handlers=(handler,),
        force=True,
    )


@dataclass(frozen=True, slots=True)
class DesktopEntryDependencies:
    """Overridable desktop composition and side effects for one process run."""

    paths_resolver: Callable[[], ApplicationPaths] = desktop_application_paths
    web_app_builder: Callable[[Path, Path], FastAPI] = _build_desktop_web_app
    server_factory: Callable[[FastAPI], DesktopServer] = _build_desktop_server
    window_factory: Callable[[], DesktopWindow] = _build_desktop_window
    logging_configurator: Callable[[Path], None] = configure_desktop_logging
    error_reporter: DesktopErrorReporter = field(default_factory=WindowsErrorDialog)


def run_desktop(dependencies: DesktopEntryDependencies | None = None) -> int:
    """Build and run OMYM2 Desktop, converting fatal failures to a GUI exit code."""
    runtime_dependencies = DesktopEntryDependencies() if dependencies is None else dependencies
    diagnostic_log_file: Path | None = None
    try:
        paths = runtime_dependencies.paths_resolver()
        runtime_dependencies.logging_configurator(paths.desktop_log_file)
        diagnostic_log_file = paths.desktop_log_file
        LOGGER.info(
            "Desktop starting version=%s os=%s application_root=%s",
            __version__,
            system_platform.platform(),
            paths.app_root,
        )
        app = runtime_dependencies.web_app_builder(paths.config_file, paths.database_file)
        runtime = DesktopRuntime(
            server=runtime_dependencies.server_factory(app),
            window=runtime_dependencies.window_factory(),
        )
        runtime.run()
    except Exception:
        LOGGER.exception("Desktop process failed")
        message = _fatal_error_message(diagnostic_log_file)
        runtime_dependencies.error_reporter.show(DESKTOP_WINDOW_TITLE, message)
        return DESKTOP_FAILURE_EXIT_CODE
    LOGGER.info("Desktop stopped gracefully")
    return DESKTOP_SUCCESS_EXIT_CODE


def _fatal_error_message(log_file: Path | None) -> str:
    if log_file is None:
        return "OMYM2 could not start and no diagnostic log could be created."
    return f"OMYM2 could not start. See the diagnostic log at {log_file}."


def main() -> int:
    """Run the OMYM2 native desktop process entry point."""
    return run_desktop()
