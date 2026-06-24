"""
Summary: Defines the initial OMYM2 CLI entry point.
Why: Establishes the command adapter boundary before feature commands exist.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from omym2.adapters.cli.commands.add import run_add_command
from omym2.adapters.cli.commands.apply import run_apply_command
from omym2.adapters.cli.commands.config import run_config_command
from omym2.adapters.cli.commands.inspect import run_inspect_command
from omym2.adapters.cli.commands.organize import run_organize_command
from omym2.adapters.cli.commands.plans import run_plans_command
from omym2.adapters.cli.commands.refresh import run_refresh_command

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path
    from typing import TextIO

ADD_COMMAND = "add"
APPLY_COMMAND = "apply"
CONFIG_COMMAND = "config"
INSPECT_COMMAND = "inspect"
ORGANIZE_COMMAND = "organize"
PLANS_COMMAND = "plans"
REFRESH_COMMAND = "refresh"
SUCCESS_EXIT_CODE = 0
UNKNOWN_COMMAND_EXIT_CODE = 2


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
    if command == ADD_COMMAND:
        exit_code = run_add_command(command_args, output, error_output, config_path, database_path)
    elif command == APPLY_COMMAND:
        exit_code = run_apply_command(command_args, output, error_output, database_path)
    elif command == CONFIG_COMMAND:
        exit_code = run_config_command(command_args, output, error_output, config_path)
    elif command == INSPECT_COMMAND:
        exit_code = run_inspect_command(command_args, output, error_output, config_path)
    elif command == ORGANIZE_COMMAND:
        exit_code = run_organize_command(command_args, output, error_output, config_path, database_path)
    elif command == PLANS_COMMAND:
        exit_code = run_plans_command(command_args, output, error_output, database_path)
    elif command == REFRESH_COMMAND:
        exit_code = run_refresh_command(command_args, output, error_output, config_path, database_path)
    else:
        _ = error_output.write(f"Unknown command: {command}\n")
        exit_code = UNKNOWN_COMMAND_EXIT_CODE

    return exit_code
