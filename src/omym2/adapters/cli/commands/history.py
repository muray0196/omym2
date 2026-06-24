"""
Summary: Implements the history CLI command.
Why: Exposes Run history without coupling CLI output to persistence details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from omym2.adapters.cli.commands.output import write_line, write_usage
from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.features.history.dto import ListRunsRequest
from omym2.features.history.ports import HistoryPorts
from omym2.features.history.usecases.list_runs import ListRunsUseCase

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path
    from typing import TextIO

    from omym2.domain.models.run import Run

HISTORY_USAGE_MESSAGE = "Usage: omym2 history"
NO_RUNS_MESSAGE = "No runs."
SUCCESS_EXIT_CODE = 0
USAGE_EXIT_CODE = 2


def run_history_command(
    args: Sequence[str],
    stdout: TextIO,
    stderr: TextIO,
    database_path: Path | None = None,
) -> int:
    """Run history and return a process exit code."""
    if len(args) != 0:
        write_usage(stderr, HISTORY_USAGE_MESSAGE)
        return USAGE_EXIT_CODE

    app_paths = default_application_paths()
    ports = HistoryPorts(uow=SQLiteUnitOfWork(database_path or app_paths.database_file))
    runs = ListRunsUseCase(ports).execute(ListRunsRequest())

    if len(runs) == 0:
        write_line(stdout, NO_RUNS_MESSAGE)
        return SUCCESS_EXIT_CODE

    for run in runs:
        _write_run_row(stdout, run)
    return SUCCESS_EXIT_CODE


def _write_run_row(stdout: TextIO, run: Run) -> None:
    completed_at = "-" if run.completed_at is None else run.completed_at.isoformat()
    row = (
        f"{run.run_id} plan={run.plan_id} library={run.library_id} status={run.status.value} "
        f"started_at={run.started_at.isoformat()} completed_at={completed_at}\n"
    )
    _ = stdout.write(row)
