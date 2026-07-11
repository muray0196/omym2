"""
Summary: Resolves OMYM2 application storage paths.
Why: Keeps config and internal data locations consistent across adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from omym2.config import (
    APP_ROOT_DIRECTORY_NAME,
    CONFIG_DIRECTORY_NAME,
    CONFIG_FILE_NAME,
    DATA_DIRECTORY_NAME,
    SQLITE_DATABASE_FILE_NAME,
)


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


def default_application_paths(app_root: Path | None = None) -> ApplicationPaths:
    """Resolve application paths from the trusted default root unless overridden."""
    resolved_app_root = Path.home() / APP_ROOT_DIRECTORY_NAME if app_root is None else app_root
    return ApplicationPaths(app_root=resolved_app_root)
