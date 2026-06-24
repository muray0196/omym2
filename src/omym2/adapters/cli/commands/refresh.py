"""
Summary: Implements the refresh CLI command.
Why: Exposes relocation Plan creation after external tag correction.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from omym2.adapters.cli.commands.confirmation import (
    APPLY_CANCELLED_MESSAGE,
    ConfirmationOptions,
    confirm_apply,
)
from omym2.adapters.cli.commands.output import write_line, write_usage, write_validation_errors
from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.config.toml_config_store import TomlConfigStore
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.adapters.fs.file_mover import FilesystemFileMover
from omym2.adapters.fs.file_presence import FilesystemFilePresence
from omym2.adapters.fs.file_snapshot_reader import FilesystemFileSnapshotReader
from omym2.adapters.fs.path_resolver import FilesystemPathResolver
from omym2.adapters.metadata.mutagen_reader import MetadataReadError, MutagenMetadataReader
from omym2.domain.models.plan_action import ActionStatus, ActionType
from omym2.domain.models.run import RunStatus
from omym2.features.apply.dto import ApplyOptions, ApplyPlanRequest
from omym2.features.apply.ports import ApplyPlanPorts
from omym2.features.apply.usecases.apply_plan import ApplyPlanError, ApplyPlanUseCase
from omym2.features.common_ports import ConfigStoreValidationError, SystemClock, Uuid7IdGenerator
from omym2.features.refresh.dto import CreateRefreshPlanRequest
from omym2.features.refresh.ports import CreateRefreshPlanPorts
from omym2.features.refresh.usecases.create_refresh_plan import (
    CreateRefreshPlanUseCase,
    RefreshLibrarySelectionError,
    RefreshTargetSelectionError,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import TextIO

    from omym2.domain.models.plan import Plan
    from omym2.features.common_ports import FileSystemPath

ALL_FLAG = "--all"
APPLY_FLAG = "--apply"
ERROR_EXIT_CODE = 1
REFRESH_USAGE_MESSAGE = "Usage: omym2 refresh (<file|dir>|--all) [--apply]"
SUCCESS_EXIT_CODE = 0
USAGE_EXIT_CODE = 2


def run_refresh_command(
    args: Sequence[str],
    stdout: TextIO,
    stderr: TextIO,
    config_path: Path | None = None,
    database_path: Path | None = None,
) -> int:
    """Run refresh and return a process exit code."""
    try:
        options = _parse_args(args)
    except ValueError:
        write_usage(stderr, REFRESH_USAGE_MESSAGE)
        return USAGE_EXIT_CODE

    return _run_refresh(options, stdout, stderr, config_path, database_path)


def _run_refresh(
    options: _RefreshCommandOptions,
    stdout: TextIO,
    stderr: TextIO,
    config_path: Path | None,
    database_path: Path | None,
) -> int:
    app_paths = default_application_paths()
    ports = CreateRefreshPlanPorts(
        uow=SQLiteUnitOfWork(database_path or app_paths.database_file),
        file_snapshot_reader=FilesystemFileSnapshotReader(metadata_reader=MutagenMetadataReader()),
        file_presence=FilesystemFilePresence(),
        config_store=TomlConfigStore(config_path or app_paths.config_file),
        path_resolver=FilesystemPathResolver(),
        clock=SystemClock(),
        id_generator=Uuid7IdGenerator(),
    )

    try:
        plan = CreateRefreshPlanUseCase(ports).execute(
            CreateRefreshPlanRequest(target_path=options.target_path, include_all=options.include_all)
        )
    except ConfigStoreValidationError as exc:
        write_validation_errors(stderr, exc.errors)
        return ERROR_EXIT_CODE
    except (RefreshLibrarySelectionError, RefreshTargetSelectionError) as exc:
        write_line(stderr, str(exc))
        return ERROR_EXIT_CODE
    except MetadataReadError as exc:
        write_line(stderr, f"Metadata read error: {exc}")
        return ERROR_EXIT_CODE
    except OSError as exc:
        write_line(stderr, f"Refresh I/O error: {exc}")
        return ERROR_EXIT_CODE

    _write_result(stdout, plan)
    if options.should_apply:
        return _apply_created_plan(plan, stdout, stderr, database_path)

    return SUCCESS_EXIT_CODE


@dataclass(frozen=True, slots=True)
class _RefreshCommandOptions:
    """Parsed refresh command options."""

    target_path: str | None
    include_all: bool
    should_apply: bool


def _parse_args(args: Sequence[str]) -> _RefreshCommandOptions:
    target_path: str | None = None
    include_all = False
    should_apply = False

    for arg in args:
        if arg == APPLY_FLAG:
            should_apply = True
        elif arg == ALL_FLAG:
            include_all = True
        elif not arg.startswith("-") and target_path is None:
            target_path = _normalize_target_path(arg)
        else:
            raise ValueError(REFRESH_USAGE_MESSAGE)

    if sum((target_path is not None, include_all)) != 1:
        raise ValueError(REFRESH_USAGE_MESSAGE)

    return _RefreshCommandOptions(target_path=target_path, include_all=include_all, should_apply=should_apply)


def _normalize_target_path(raw_path: FileSystemPath) -> str:
    return str(Path(raw_path).expanduser().resolve(strict=False))


def _write_result(stdout: TextIO, plan: Plan) -> None:
    blocked_count = sum(action.status == ActionStatus.BLOCKED for action in plan.actions)
    move_count = sum(
        action.action_type == ActionType.MOVE and action.status == ActionStatus.PLANNED for action in plan.actions
    )

    _ = stdout.write(f"Refresh plan created: {plan.plan_id}\n")
    _ = stdout.write(f"actions: {len(plan.actions)}\n")
    _ = stdout.write(f"move_actions: {move_count}\n")
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
