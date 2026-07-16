"""
Summary: Provides the OMYM2 native desktop process entry point.
Why: Composes stable storage, diagnostics, loopback serving, and the native window.
"""

from __future__ import annotations

import logging
import platform as system_platform
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from omym2 import __version__
from omym2.adapters.config.application_paths import desktop_application_paths
from omym2.adapters.config.toml_config_store import TomlConfigStore
from omym2.adapters.desktop.server import UvicornDesktopServer
from omym2.adapters.desktop.window import PyWebViewWindow, WindowsErrorDialog
from omym2.config import (
    DESKTOP_FAILURE_EXIT_CODE,
    DESKTOP_SUCCESS_EXIT_CODE,
    DESKTOP_WINDOW_TITLE,
)
from omym2.platform.desktop_runtime import DesktopRuntime
from omym2.platform.logging_composition import (
    configure_application_logging,
    resolve_log_file,
    sensitive_log_values,
)
from omym2.platform.web_composition import build_web_app

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from fastapi import FastAPI

    from omym2.adapters.config.application_paths import ApplicationPaths
    from omym2.domain.models.app_config import LoggingConfig
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


def configure_desktop_logging(
    log_file: Path,
    config: LoggingConfig,
    sensitive_values: tuple[str, ...],
) -> None:
    """Route application and Uvicorn records through shared bounded logging."""
    configure_application_logging(log_file, config, sensitive_values=sensitive_values)


@dataclass(frozen=True, slots=True)
class DesktopEntryDependencies:
    """Overridable desktop composition and side effects for one process run."""

    paths_resolver: Callable[[], ApplicationPaths] = desktop_application_paths
    web_app_builder: Callable[[Path, Path], FastAPI] = _build_desktop_web_app
    server_factory: Callable[[FastAPI], DesktopServer] = _build_desktop_server
    window_factory: Callable[[], DesktopWindow] = _build_desktop_window
    logging_configurator: Callable[[Path, LoggingConfig, tuple[str, ...]], None] = configure_desktop_logging
    error_reporter: DesktopErrorReporter = field(default_factory=WindowsErrorDialog)


def run_desktop(dependencies: DesktopEntryDependencies | None = None) -> int:
    """Build and run OMYM2 Desktop, converting fatal failures to a GUI exit code."""
    runtime_dependencies = DesktopEntryDependencies() if dependencies is None else dependencies
    diagnostic_log_file: Path | None = None
    try:
        paths = runtime_dependencies.paths_resolver()
        config = TomlConfigStore(paths.config_file).load()
        resolved_log_file = resolve_log_file(paths.app_root, paths.desktop_log_file, config.logging)
        runtime_dependencies.logging_configurator(
            resolved_log_file,
            config.logging,
            sensitive_log_values(paths, config),
        )
        diagnostic_log_file = resolved_log_file
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
