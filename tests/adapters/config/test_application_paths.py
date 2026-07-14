"""
Summary: Tests application path resolution.
Why: Protects documented config and internal data locations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from omym2.adapters.config.application_paths import (
    DesktopApplicationPathError,
    default_application_paths,
    desktop_application_paths,
)
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
    from pathlib import Path


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


def test_exclusive_operation_lock_path_is_under_app_root_data(tmp_path: Path) -> None:
    """The cross-process mutation lock shares the application data directory."""
    paths = default_application_paths(tmp_path)

    assert paths.exclusive_operation_lock_file == (tmp_path / DATA_DIRECTORY_NAME / EXCLUSIVE_OPERATION_LOCK_FILE_NAME)


def test_desktop_paths_use_stable_windows_local_application_data(tmp_path: Path) -> None:
    """Desktop state stays under the supported user's local application-data directory."""
    local_app_data = tmp_path / "Unicode 音楽" / "Local App Data"

    paths = desktop_application_paths(
        platform=DESKTOP_SUPPORTED_PLATFORM,
        environment={DESKTOP_WINDOWS_DATA_ENVIRONMENT_VARIABLE: str(local_app_data)},
    )

    expected_root = local_app_data / DESKTOP_APPLICATION_DIRECTORY_NAME
    assert paths.app_root == expected_root
    assert paths.config_file == expected_root / CONFIG_DIRECTORY_NAME / CONFIG_FILE_NAME
    assert paths.database_file == expected_root / DATA_DIRECTORY_NAME / SQLITE_DATABASE_FILE_NAME


def test_desktop_log_path_is_outside_replaceable_application_files(tmp_path: Path) -> None:
    """Desktop diagnostics share the stable internal data root, not the executable directory."""
    paths = desktop_application_paths(
        platform=DESKTOP_SUPPORTED_PLATFORM,
        environment={DESKTOP_WINDOWS_DATA_ENVIRONMENT_VARIABLE: str(tmp_path)},
    )

    assert paths.log_dir == paths.data_dir / DESKTOP_LOG_DIRECTORY_NAME
    assert paths.desktop_log_file == paths.data_dir / DESKTOP_LOG_DIRECTORY_NAME / DESKTOP_LOG_FILE_NAME


def test_desktop_paths_do_not_depend_on_process_working_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Launching from a shortcut or replacement directory preserves desktop state identity."""
    local_app_data = tmp_path / "local"
    environment = {DESKTOP_WINDOWS_DATA_ENVIRONMENT_VARIABLE: str(local_app_data)}
    first = desktop_application_paths(platform=DESKTOP_SUPPORTED_PLATFORM, environment=environment)
    other_working_directory = tmp_path / "replacement-app"
    other_working_directory.mkdir()
    monkeypatch.chdir(other_working_directory)

    second = desktop_application_paths(platform=DESKTOP_SUPPORTED_PLATFORM, environment=environment)

    assert second == first


def test_desktop_paths_reject_unsupported_platform() -> None:
    """The Windows-first release does not imply unvalidated cross-platform support."""
    unsupported_platform = "linux"

    with pytest.raises(DesktopApplicationPathError, match="does not support"):
        _ = desktop_application_paths(platform=unsupported_platform, environment={})


def test_desktop_paths_require_windows_local_application_data() -> None:
    """A missing stable Windows data root fails instead of falling back to the launch directory."""
    with pytest.raises(DesktopApplicationPathError, match=DESKTOP_WINDOWS_DATA_ENVIRONMENT_VARIABLE):
        _ = desktop_application_paths(platform=DESKTOP_SUPPORTED_PLATFORM, environment={})
