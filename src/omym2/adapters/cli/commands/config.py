"""
Summary: Implements config-related CLI commands.
Why: Exposes TOML-backed settings inspection and validation to users.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.config.toml_config_store import TomlConfigStore, dump_config_toml
from omym2.features.common_ports import ConfigStoreValidationError
from omym2.features.settings.ports import SettingsPorts
from omym2.features.settings.usecases.load_settings import LoadSettingsUseCase
from omym2.features.settings.usecases.validate_settings import ValidateSettingsUseCase

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path
    from typing import TextIO

CONFIG_VALIDATE_SUCCESS_MESSAGE = "Config is valid."
CONFIG_USAGE_MESSAGE = "Usage: omym2 config {show|validate}"
ERROR_EXIT_CODE = 1
SHOW_SUBCOMMAND = "show"
SUCCESS_EXIT_CODE = 0
USAGE_EXIT_CODE = 2
VALIDATE_SUBCOMMAND = "validate"


def run_config_command(
    args: Sequence[str],
    stdout: TextIO,
    stderr: TextIO,
    config_path: Path | None = None,
) -> int:
    """Run a config subcommand and return a process exit code."""
    if len(args) != 1:
        _write_usage(stderr)
        return USAGE_EXIT_CODE

    store = TomlConfigStore(config_path or default_application_paths().config_file)
    ports = SettingsPorts(config_store=store)
    subcommand = args[0]

    if subcommand == SHOW_SUBCOMMAND:
        return _show_config(ports, stdout, stderr)
    if subcommand == VALIDATE_SUBCOMMAND:
        return _validate_config(ports, stdout, stderr)

    _write_usage(stderr)
    return USAGE_EXIT_CODE


def _show_config(ports: SettingsPorts, stdout: TextIO, stderr: TextIO) -> int:
    try:
        config = LoadSettingsUseCase(ports).execute()
    except ConfigStoreValidationError as exc:
        _write_validation_errors(stderr, exc.errors)
        return ERROR_EXIT_CODE
    except OSError as exc:
        _write_io_error(stderr, exc)
        return ERROR_EXIT_CODE

    _ = stdout.write(dump_config_toml(config))
    return SUCCESS_EXIT_CODE


def _validate_config(ports: SettingsPorts, stdout: TextIO, stderr: TextIO) -> int:
    try:
        result = ValidateSettingsUseCase(ports).execute()
    except OSError as exc:
        _write_io_error(stderr, exc)
        return ERROR_EXIT_CODE

    if not result.valid:
        _write_validation_errors(stderr, result.errors)
        return ERROR_EXIT_CODE

    _ = stdout.write(f"{CONFIG_VALIDATE_SUCCESS_MESSAGE}\n")
    return SUCCESS_EXIT_CODE


def _write_usage(stderr: TextIO) -> None:
    _ = stderr.write(f"{CONFIG_USAGE_MESSAGE}\n")


def _write_validation_errors(stderr: TextIO, errors: tuple[str, ...]) -> None:
    stderr.writelines(f"{error}\n" for error in errors)


def _write_io_error(stderr: TextIO, exc: OSError) -> None:
    _ = stderr.write(f"Config I/O error: {exc}\n")
