"""
Summary: Defines the initial OMYM2 CLI entry point.
Why: Establishes the command adapter boundary before feature commands exist.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import TYPE_CHECKING

from omym2.adapters.cli.commands.add import run_add_command
from omym2.adapters.cli.commands.apply import run_apply_command
from omym2.adapters.cli.commands.check import run_check_command
from omym2.adapters.cli.commands.config import run_config_command
from omym2.adapters.cli.commands.history import run_history_command
from omym2.adapters.cli.commands.inspect import run_inspect_command
from omym2.adapters.cli.commands.organize import run_organize_command
from omym2.adapters.cli.commands.plans import run_plans_command
from omym2.adapters.cli.commands.refresh import run_refresh_command
from omym2.adapters.cli.commands.settings import run_settings_command
from omym2.adapters.cli.commands.undo import run_undo_command

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path
    from typing import TextIO

ADD_COMMAND = "add"
APPLY_COMMAND = "apply"
CHECK_COMMAND = "check"
CONFIG_COMMAND = "config"
HISTORY_COMMAND = "history"
INSPECT_COMMAND = "inspect"
ORGANIZE_COMMAND = "organize"
PLANS_COMMAND = "plans"
REFRESH_COMMAND = "refresh"
SETTINGS_COMMAND = "settings"
UNDO_COMMAND = "undo"
SUCCESS_EXIT_CODE = 0
UNKNOWN_COMMAND_EXIT_CODE = 2
type CommandCallback = Callable[[], int]


def main(
    argv: Sequence[str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    config_path: Path | None = None,
    database_path: Path | None = None,
) -> int:
    """Run the OMYM2 CLI and return a process exit code."""
    output = sys.stdout if stdout is None else stdout
    error_output = sys.stderr if stderr is None else stderr
    args = tuple(sys.argv[1:] if argv is None else argv)

    if len(args) == 0:
        return SUCCESS_EXIT_CODE

    command, *command_args = args
    command_runners: dict[str, CommandCallback] = {
        ADD_COMMAND: lambda: run_add_command(command_args, output, error_output, config_path, database_path),
        APPLY_COMMAND: lambda: run_apply_command(command_args, output, error_output, database_path),
        CHECK_COMMAND: lambda: run_check_command(command_args, output, error_output, config_path, database_path),
        CONFIG_COMMAND: lambda: run_config_command(command_args, output, error_output, config_path),
        HISTORY_COMMAND: lambda: run_history_command(command_args, output, error_output, database_path),
        INSPECT_COMMAND: lambda: run_inspect_command(command_args, output, error_output, config_path),
        ORGANIZE_COMMAND: lambda: run_organize_command(command_args, output, error_output, config_path, database_path),
        PLANS_COMMAND: lambda: run_plans_command(command_args, output, error_output, database_path),
        REFRESH_COMMAND: lambda: run_refresh_command(command_args, output, error_output, config_path, database_path),
        SETTINGS_COMMAND: lambda: run_settings_command(command_args, output, error_output, config_path),
        UNDO_COMMAND: lambda: run_undo_command(command_args, output, error_output, database_path),
    }
    runner = command_runners.get(command)
    if runner is None:
        _ = error_output.write(f"Unknown command: {command}\n")
        exit_code = UNKNOWN_COMMAND_EXIT_CODE
    else:
        exit_code = runner()

    return exit_code
