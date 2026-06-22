"""
Summary: Tests application path resolution.
Why: Protects documented config and internal data locations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from omym2.adapters.config.application_paths import default_application_paths
from omym2.config import (
    APP_DIRECTORY_NAME,
    CONFIG_DIRECTORY_NAME,
    CONFIG_FILE_NAME,
    DATA_DIRECTORY_NAME,
    SQLITE_DATABASE_FILE_NAME,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_config_path_resolves_under_app_root_config(tmp_path: Path) -> None:
    """The TOML config path is under ~/omym2/config/config.toml."""
    paths = default_application_paths(tmp_path)

    assert paths.app_root == tmp_path / APP_DIRECTORY_NAME
    assert paths.config_dir == tmp_path / APP_DIRECTORY_NAME / CONFIG_DIRECTORY_NAME
    assert paths.config_file == tmp_path / APP_DIRECTORY_NAME / CONFIG_DIRECTORY_NAME / CONFIG_FILE_NAME


def test_db_path_is_under_app_root_data(tmp_path: Path) -> None:
    """The future SQLite path is reserved under ~/omym2/.data/."""
    paths = default_application_paths(tmp_path)

    assert paths.data_dir == tmp_path / APP_DIRECTORY_NAME / DATA_DIRECTORY_NAME
    assert paths.database_file == tmp_path / APP_DIRECTORY_NAME / DATA_DIRECTORY_NAME / SQLITE_DATABASE_FILE_NAME
