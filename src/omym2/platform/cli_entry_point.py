"""
Summary: Provides the OMYM2 process entry point.
Why: Builds the CLI dependency bundle once per invocation and dispatches through adapters.cli.main.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from omym2.adapters.cli.main import main as _dispatch_cli
from omym2.platform.cli_composition import build_command_dependencies

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path
    from typing import TextIO


def run_cli(
    argv: Sequence[str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    config_path: Path | None = None,
    database_path: Path | None = None,
) -> int:
    """Build the CLI dependency bundle for one invocation and run the CLI."""
    dependencies = build_command_dependencies(config_path, database_path)
    return _dispatch_cli(argv, stdout, stderr, dependencies=dependencies)


def main() -> int:
    """Run the OMYM2 CLI process entry point."""
    return run_cli()
