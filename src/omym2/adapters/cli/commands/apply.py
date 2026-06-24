"""
Summary: Implements the apply CLI command.
Why: Exposes reviewed Plan execution through the public command surface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from omym2.adapters.cli.commands.confirmation import (
    APPLY_CANCELLED_MESSAGE,
    ConfirmationOptions,
    confirm_apply,
)
from omym2.adapters.cli.commands.output import write_line, write_usage
from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.adapters.fs.file_mover import FilesystemFileMover
from omym2.adapters.fs.file_snapshot_reader import FilesystemFileSnapshotReader
from omym2.adapters.fs.path_resolver import FilesystemPathResolver
from omym2.adapters.metadata.mutagen_reader import MutagenMetadataReader
from omym2.domain.models.plan import PlanStatus
from omym2.domain.models.run import RunStatus
from omym2.features.apply.dto import ApplyOptions, ApplyPlanRequest
from omym2.features.apply.ports import ApplyPlanPorts
from omym2.features.apply.usecases.apply_plan import (
    ApplyPlanError,
    ApplyPlanUseCase,
)
from omym2.features.common_ports import SystemClock, Uuid7IdGenerator
from omym2.shared.ids import PlanId, parse_uuid

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path
    from typing import TextIO

    from omym2.domain.models.run import Run

APPLY_USAGE_MESSAGE = "Usage: omym2 apply <PLAN_ID|latest> [--yes]"
ERROR_EXIT_CODE = 1
INVALID_PLAN_ID_MESSAGE = "Invalid Plan ID."
LATEST_PLAN_SELECTOR = "latest"
NO_READY_PLAN_MESSAGE = "No ready Plan exists."
SUCCESS_EXIT_CODE = 0
USAGE_EXIT_CODE = 2
YES_FLAG = "--yes"


def run_apply_command(
    args: Sequence[str],
    stdout: TextIO,
    stderr: TextIO,
    database_path: Path | None = None,
) -> int:
    """Run apply and return a process exit code."""
    try:
        plan_selector, yes = _parse_args(args)
    except ValueError:
        write_usage(stderr, APPLY_USAGE_MESSAGE)
        return USAGE_EXIT_CODE

    app_paths = default_application_paths()
    uow = SQLiteUnitOfWork(database_path or app_paths.database_file)

    try:
        plan_id = _selected_plan_id(uow, plan_selector)
    except PlanSelectionError as exc:
        write_line(stderr, str(exc))
        return ERROR_EXIT_CODE

    if not confirm_apply(stdout, ConfirmationOptions(yes=yes)):
        write_line(stderr, APPLY_CANCELLED_MESSAGE)
        return ERROR_EXIT_CODE

    return _run_selected_plan(plan_id, stdout, stderr, database_path)


class PlanSelectionError(ValueError):
    """Raised when a CLI Plan selector cannot be resolved."""


def _run_selected_plan(
    plan_id: PlanId,
    stdout: TextIO,
    stderr: TextIO,
    database_path: Path | None,
) -> int:
    app_paths = default_application_paths()
    ports = ApplyPlanPorts(
        uow=SQLiteUnitOfWork(database_path or app_paths.database_file),
        file_mover=FilesystemFileMover(),
        file_snapshot_reader=FilesystemFileSnapshotReader(metadata_reader=MutagenMetadataReader()),
        path_resolver=FilesystemPathResolver(),
        clock=SystemClock(),
        id_generator=Uuid7IdGenerator(),
    )

    try:
        run = ApplyPlanUseCase(ports).execute(ApplyPlanRequest(plan_id=plan_id, options=ApplyOptions(yes=True)))
    except ApplyPlanError as exc:
        write_line(stderr, str(exc))
        return ERROR_EXIT_CODE

    if run is None:
        write_line(stderr, "Plan expired before apply; no run created.")
        return ERROR_EXIT_CODE

    _write_run_result(stdout, run)
    if run.status in {RunStatus.FAILED, RunStatus.PARTIAL_FAILED}:
        return ERROR_EXIT_CODE
    return SUCCESS_EXIT_CODE


def _parse_args(args: Sequence[str]) -> tuple[str, bool]:
    positional_args: list[str] = []
    yes = False

    for arg in args:
        if arg == YES_FLAG:
            yes = True
        elif arg.startswith("-"):
            raise ValueError(APPLY_USAGE_MESSAGE)
        else:
            positional_args.append(arg)

    if len(positional_args) != 1:
        raise ValueError(APPLY_USAGE_MESSAGE)

    return positional_args[0], yes


def _selected_plan_id(uow: SQLiteUnitOfWork, selector: str) -> PlanId:
    if selector == LATEST_PLAN_SELECTOR:
        latest_plan_id = _latest_ready_plan_id(uow)
        if latest_plan_id is None:
            raise PlanSelectionError(NO_READY_PLAN_MESSAGE)
        return latest_plan_id

    try:
        return PlanId(parse_uuid(selector))
    except ValueError as exc:
        raise PlanSelectionError(INVALID_PLAN_ID_MESSAGE) from exc


def _latest_ready_plan_id(uow: SQLiteUnitOfWork) -> PlanId | None:
    with uow:
        ready_plans = [
            plan
            for library in uow.libraries.list_all()
            for plan in uow.plans.list_by_library(library.library_id)
            if plan.status == PlanStatus.READY
        ]

    if len(ready_plans) == 0:
        return None

    latest_plan = max(ready_plans, key=lambda plan: (plan.created_at, str(plan.plan_id)))
    return latest_plan.plan_id


def _write_run_result(stdout: TextIO, run: Run) -> None:
    _ = stdout.write(f"Apply run completed: {run.run_id}\n")
    _ = stdout.write(f"status: {run.status.value}\n")
