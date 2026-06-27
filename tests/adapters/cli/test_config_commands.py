"""
Summary: Tests config CLI commands.
Why: Verifies the config command surface through the public CLI entry point.
"""

from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING

from omym2.adapters.cli.main import main
from omym2.config import CONFIG_FILE_ENCODING, CONFIG_VERSION
from omym2.domain.models.app_config import INVALID_MAX_FILENAME_LENGTH_MESSAGE

if TYPE_CHECKING:
    from pathlib import Path

CONFIG_FILE_NAME = "config.toml"
INVALID_MAX_FILENAME_LENGTH = 0
SUCCESS_EXIT_CODE = 0
ERROR_EXIT_CODE = 1


def test_config_show_prints_default_toml_without_creating_missing_file(tmp_path: Path) -> None:
    """config show displays defaults when config has not been created."""
    config_path = tmp_path / CONFIG_FILE_NAME
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(["config", "show"], stdout=stdout, stderr=stderr, config_path=config_path)

    assert exit_code == SUCCESS_EXIT_CODE
    assert f"version = {CONFIG_VERSION}" in stdout.getvalue()
    assert "[path_policy]" in stdout.getvalue()
    assert stderr.getvalue() == ""
    assert not config_path.exists()


def test_config_validate_accepts_missing_default_config(tmp_path: Path) -> None:
    """config validate treats missing config as valid defaults."""
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(["config", "validate"], stdout=stdout, stderr=stderr, config_path=tmp_path / CONFIG_FILE_NAME)

    assert exit_code == SUCCESS_EXIT_CODE
    assert stdout.getvalue() == "Config is valid.\n"
    assert stderr.getvalue() == ""


def test_config_validate_reports_invalid_toml_config(tmp_path: Path) -> None:
    """config validate returns errors for invalid persisted settings."""
    config_path = tmp_path / CONFIG_FILE_NAME
    _ = config_path.write_text(
        "\n".join(
            (
                f"version = {CONFIG_VERSION}",
                "",
                "[path_policy]",
                f"max_filename_length = {INVALID_MAX_FILENAME_LENGTH}",
            )
        ),
        encoding=CONFIG_FILE_ENCODING,
    )
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(["config", "validate"], stdout=stdout, stderr=stderr, config_path=config_path)

    assert exit_code == ERROR_EXIT_CODE
    assert stdout.getvalue() == ""
    assert INVALID_MAX_FILENAME_LENGTH_MESSAGE in stderr.getvalue()
