"""
Summary: Resolves OMYM2 application storage paths.
Why: Keeps config and internal data locations consistent across adapters.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from omym2.config import (
    CONFIG_DIRECTORY_NAME,
    CONFIG_FILE_NAME,
    DATA_DIRECTORY_NAME,
    DESKTOP_APPLICATION_DIRECTORY_NAME,
    DESKTOP_LOG_DIRECTORY_NAME,
    DESKTOP_LOG_FILE_NAME,
    DESKTOP_SUPPORTED_PLATFORM,
    DESKTOP_WINDOWS_DATA_ENVIRONMENT_VARIABLE,
    EXCLUSIVE_OPERATION_LOCK_FILE_NAME,
    SQLITE_DATABASE_FILE_NAME,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


class DesktopApplicationPathError(RuntimeError):
    """Raised when a stable writable desktop application root cannot be resolved."""


@dataclass(frozen=True, slots=True)
class ApplicationPaths:
    """Resolved filesystem paths for OMYM2-owned files."""

    app_root: Path

    @property
    def config_dir(self) -> Path:
        """Return the directory containing user-editable TOML config."""
        return self.app_root / CONFIG_DIRECTORY_NAME

    @property
    def config_file(self) -> Path:
        """Return the expected TOML config file path."""
        return self.config_dir / CONFIG_FILE_NAME

    @property
    def data_dir(self) -> Path:
        """Return the internal data directory reserved for OMYM2."""
        return self.app_root / DATA_DIRECTORY_NAME

    @property
    def database_file(self) -> Path:
        """Return the expected SQLite database file path."""
        return self.data_dir / SQLITE_DATABASE_FILE_NAME

    @property
    def exclusive_operation_lock_file(self) -> Path:
        """Return the shared cross-process mutation lock file path."""
        return self.data_dir / EXCLUSIVE_OPERATION_LOCK_FILE_NAME

    @property
    def log_dir(self) -> Path:
        """Return the desktop diagnostic log directory."""
        return self.data_dir / DESKTOP_LOG_DIRECTORY_NAME

    @property
    def desktop_log_file(self) -> Path:
        """Return the desktop diagnostic log file path."""
        return self.log_dir / DESKTOP_LOG_FILE_NAME


def default_application_paths(app_root: Path | None = None) -> ApplicationPaths:
    """Resolve application paths from the runtime application root."""
    return ApplicationPaths(app_root=Path.cwd() if app_root is None else app_root)


def desktop_application_paths(
    *,
    platform: str | None = None,
    environment: Mapping[str, str] | None = None,
) -> ApplicationPaths:
    """Resolve the stable per-user application root for the supported desktop platform."""
    runtime_platform = sys.platform if platform is None else platform
    if runtime_platform != DESKTOP_SUPPORTED_PLATFORM:
        msg = f"OMYM2 Desktop does not support platform {runtime_platform!r}."
        raise DesktopApplicationPathError(msg)
    runtime_environment = os.environ if environment is None else environment
    local_app_data = runtime_environment.get(DESKTOP_WINDOWS_DATA_ENVIRONMENT_VARIABLE)
    if not local_app_data:
        msg = f"{DESKTOP_WINDOWS_DATA_ENVIRONMENT_VARIABLE} is required to locate OMYM2 Desktop data."
        raise DesktopApplicationPathError(msg)
    return ApplicationPaths(Path(local_app_data) / DESKTOP_APPLICATION_DIRECTORY_NAME)
