"""
Summary: Tests application path resolution.
Why: Protects documented config and internal data locations.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from omym2.adapters.config.application_paths import default_application_paths
from omym2.config import (
    APP_ROOT_DIRECTORY_NAME,
    CONFIG_DIRECTORY_NAME,
    CONFIG_FILE_NAME,
    DATA_DIRECTORY_NAME,
    SQLITE_DATABASE_FILE_NAME,
)


def test_config_path_resolves_under_app_root_config(tmp_path: Path) -> None:
    """The TOML config path is under the app root .config directory."""
    paths = default_application_paths(tmp_path)

    assert paths.app_root == tmp_path
    assert paths.config_dir == tmp_path / CONFIG_DIRECTORY_NAME
    assert paths.config_file == tmp_path / CONFIG_DIRECTORY_NAME / CONFIG_FILE_NAME


def test_db_path_is_under_app_root_data(tmp_path: Path) -> None:
    """The SQLite path is reserved under the app root .data directory."""
    paths = default_application_paths(tmp_path)

    assert paths.data_dir == tmp_path / DATA_DIRECTORY_NAME
    assert paths.database_file == tmp_path / DATA_DIRECTORY_NAME / SQLITE_DATABASE_FILE_NAME


def test_default_app_root_uses_home_directory_not_cwd(tmp_path: Path) -> None:
    """Default storage ignores cwd so planted local state is not trusted."""
    home = tmp_path / "home"
    cwd = tmp_path / "attacker"
    home.mkdir()
    cwd.mkdir()
    previous_cwd = Path.cwd()
    try:
        with patch("pathlib.Path.home", return_value=home):
            os.chdir(cwd)
            paths = default_application_paths()
    finally:
        os.chdir(previous_cwd)

    assert paths.app_root == home / APP_ROOT_DIRECTORY_NAME
    assert paths.database_file == (home / APP_ROOT_DIRECTORY_NAME / DATA_DIRECTORY_NAME / SQLITE_DATABASE_FILE_NAME)
    assert paths.database_file != cwd / DATA_DIRECTORY_NAME / SQLITE_DATABASE_FILE_NAME
