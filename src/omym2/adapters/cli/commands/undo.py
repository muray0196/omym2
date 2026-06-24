"""
Summary: Implements the undo CLI command.
Why: Creates and optionally applies undo Plans from durable Run history.
"""

from __future__ import annotations

from dataclasses import dataclass
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
from omym2.adapters.fs.file_presence import FilesystemFilePresence
from omym2.adapters.fs.file_snapshot_reader import FilesystemFileSnapshotReader
from omym2.adapters.fs.path_resolver import FilesystemPathResolver
from omym2.adapters.metadata.mutagen_reader import MetadataReadError, MutagenMetadataReader
from omym2.domain.models.plan_action import ActionStatus
from omym2.domain.models.run import RunStatus
from omym2.features.apply.dto import ApplyOptions, ApplyPlanRequest
from omym2.features.apply.ports import ApplyPlanPorts
from omym2.features.apply.usecases.apply_plan import ApplyPlanError, ApplyPlanUseCase
from omym2.features.common_ports import SystemClock, Uuid7IdGenerator
from omym2.features.undo.dto import CreateUndoPlanRequest
from omym2.features.undo.ports import CreateUndoPlanPorts
from omym2.features.undo.usecases.create_undo_plan import CreateUndoPlanUseCase, UndoPlanError
from omym2.shared.ids import RunId, parse_uuid

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path
    from typing import TextIO

    from omym2.domain.models.plan import Plan

APPLY_FLAG = "--apply"
ERROR_EXIT_CODE = 1
INVALID_RUN_ID_MESSAGE = "Invalid Run ID."
SUCCESS_EXIT_CODE = 0
UNDO_USAGE_MESSAGE = "Usage: omym2 undo <RUN_ID> [--apply]"
USAGE_EXIT_CODE = 2


def run_undo_command(
    args: Sequence[str],
    stdout: TextIO,
    stderr: TextIO,
    database_path: Path | None = None,
) -> int:
    """Run undo and return a process exit code."""
    try:
        options = _parse_args(args)
    except ValueError:
        write_usage(stderr, UNDO_USAGE_MESSAGE)
        return USAGE_EXIT_CODE

    app_paths = default_application_paths()
    ports = CreateUndoPlanPorts(
        uow=SQLiteUnitOfWork(database_path or app_paths.database_file),
        file_snapshot_reader=FilesystemFileSnapshotReader(metadata_reader=MutagenMetadataReader()),
        file_presence=FilesystemFilePresence(),
        path_resolver=FilesystemPathResolver(),
        clock=SystemClock(),
        id_generator=Uuid7IdGenerator(),
    )

    try:
        plan = CreateUndoPlanUseCase(ports).execute(CreateUndoPlanRequest(options.run_id))
    except UndoPlanError as exc:
        write_line(stderr, str(exc))
        return ERROR_EXIT_CODE
    except MetadataReadError as exc:
        write_line(stderr, f"Metadata read error: {exc}")
        return ERROR_EXIT_CODE
    except OSError as exc:
        write_line(stderr, f"Undo I/O error: {exc}")
        return ERROR_EXIT_CODE

    _write_result(stdout, plan)
    if options.should_apply:
        return _apply_created_plan(plan, stdout, stderr, database_path)

    return SUCCESS_EXIT_CODE


@dataclass(frozen=True, slots=True)
class _UndoCommandOptions:
    """Parsed undo command options."""

    run_id: RunId
    should_apply: bool


def _parse_args(args: Sequence[str]) -> _UndoCommandOptions:
    run_id: RunId | None = None
    should_apply = False

    for arg in args:
        if arg == APPLY_FLAG:
            should_apply = True
        elif arg.startswith("-") or run_id is not None:
            raise ValueError(UNDO_USAGE_MESSAGE)
        else:
            try:
                run_id = RunId(parse_uuid(arg))
            except ValueError as exc:
                raise ValueError(INVALID_RUN_ID_MESSAGE) from exc

    if run_id is None:
        raise ValueError(UNDO_USAGE_MESSAGE)

    return _UndoCommandOptions(run_id=run_id, should_apply=should_apply)


def _write_result(stdout: TextIO, plan: Plan) -> None:
    blocked_count = sum(action.status == ActionStatus.BLOCKED for action in plan.actions)
    _ = stdout.write(f"Undo plan created: {plan.plan_id}\n")
    _ = stdout.write(f"actions: {len(plan.actions)}\n")
    _ = stdout.write(f"move_actions: {len(plan.actions) - blocked_count}\n")
    _ = stdout.write(f"blocked_actions: {blocked_count}\n")


def _apply_created_plan(plan: Plan, stdout: TextIO, stderr: TextIO, database_path: Path | None) -> int:
    if not confirm_apply(stdout, ConfirmationOptions()):
        write_line(stderr, APPLY_CANCELLED_MESSAGE)
        return ERROR_EXIT_CODE

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
        run = ApplyPlanUseCase(ports).execute(ApplyPlanRequest(plan.plan_id, options=ApplyOptions(yes=True)))
    except ApplyPlanError as exc:
        write_line(stderr, str(exc))
        return ERROR_EXIT_CODE

    if run is None:
        write_line(stderr, "Plan expired before apply; no run created.")
        return ERROR_EXIT_CODE

    _ = stdout.write(f"Apply run completed: {run.run_id}\n")
    _ = stdout.write(f"status: {run.status.value}\n")
    if run.status in {RunStatus.FAILED, RunStatus.PARTIAL_FAILED}:
        return ERROR_EXIT_CODE
    return SUCCESS_EXIT_CODE
