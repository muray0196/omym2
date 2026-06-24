"""
Summary: Implements config-related CLI commands.
Why: Exposes TOML-backed settings inspection and validation to users.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from omym2.adapters.cli.commands.output import write_line, write_usage, write_validation_errors
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
        write_usage(stderr, CONFIG_USAGE_MESSAGE)
        return USAGE_EXIT_CODE

    store = TomlConfigStore(config_path or default_application_paths().config_file)
    ports = SettingsPorts(config_store=store)
    subcommand = args[0]

    if subcommand == SHOW_SUBCOMMAND:
        return _show_config(ports, stdout, stderr)
    if subcommand == VALIDATE_SUBCOMMAND:
        return _validate_config(ports, stdout, stderr)

    write_usage(stderr, CONFIG_USAGE_MESSAGE)
    return USAGE_EXIT_CODE


def _show_config(ports: SettingsPorts, stdout: TextIO, stderr: TextIO) -> int:
    try:
        config = LoadSettingsUseCase(ports).execute()
    except ConfigStoreValidationError as exc:
        write_validation_errors(stderr, exc.errors)
        return ERROR_EXIT_CODE
    except OSError as exc:
        write_line(stderr, f"Config I/O error: {exc}")
        return ERROR_EXIT_CODE

    _ = stdout.write(dump_config_toml(config))
    return SUCCESS_EXIT_CODE


def _validate_config(ports: SettingsPorts, stdout: TextIO, stderr: TextIO) -> int:
    try:
        result = ValidateSettingsUseCase(ports).execute()
    except OSError as exc:
        write_line(stderr, f"Config I/O error: {exc}")
        return ERROR_EXIT_CODE

    if not result.valid:
        write_validation_errors(stderr, result.errors)
        return ERROR_EXIT_CODE

    write_line(stdout, CONFIG_VALIDATE_SUCCESS_MESSAGE)
    return SUCCESS_EXIT_CODE
