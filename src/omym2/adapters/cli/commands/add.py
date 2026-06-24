"""
Summary: Implements the add CLI command.
Why: Exposes incoming import Plan creation and optional apply orchestration.
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
from omym2.adapters.fs.file_scanner import FilesystemFileScanner
from omym2.adapters.fs.file_snapshot_reader import FilesystemFileSnapshotReader
from omym2.adapters.fs.path_resolver import FilesystemPathResolver
from omym2.adapters.metadata.mutagen_reader import MetadataReadError, MutagenMetadataReader
from omym2.domain.models.plan_action import ActionStatus, ActionType
from omym2.domain.models.run import RunStatus
from omym2.features.add.dto import CreateAddPlanRequest
from omym2.features.add.ports import CreateAddPlanPorts
from omym2.features.add.usecases.create_add_plan import (
    AddLibrarySelectionError,
    AddSourceSelectionError,
    CreateAddPlanUseCase,
)
from omym2.features.apply.dto import ApplyOptions, ApplyPlanRequest
from omym2.features.apply.ports import ApplyPlanPorts
from omym2.features.apply.usecases.apply_plan import ApplyPlanError, ApplyPlanUseCase
from omym2.features.common_ports import ConfigStoreValidationError, SystemClock, Uuid7IdGenerator

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import TextIO

    from omym2.domain.models.plan import Plan
    from omym2.features.common_ports import FileSystemPath

ADD_USAGE_MESSAGE = "Usage: omym2 add [SOURCE_DIR] [--apply] [--yes]"
APPLY_FLAG = "--apply"
ERROR_EXIT_CODE = 1
SUCCESS_EXIT_CODE = 0
USAGE_EXIT_CODE = 2
YES_FLAG = "--yes"


def run_add_command(
    args: Sequence[str],
    stdout: TextIO,
    stderr: TextIO,
    config_path: Path | None = None,
    database_path: Path | None = None,
) -> int:
    """Run add and return a process exit code."""
    try:
        options = _parse_args(args)
    except ValueError:
        write_usage(stderr, ADD_USAGE_MESSAGE)
        return USAGE_EXIT_CODE

    return _run_add(options, stdout, stderr, config_path, database_path)


def _run_add(
    options: _AddCommandOptions,
    stdout: TextIO,
    stderr: TextIO,
    config_path: Path | None,
    database_path: Path | None,
) -> int:
    app_paths = default_application_paths()
    store = TomlConfigStore(config_path or app_paths.config_file)
    ports = CreateAddPlanPorts(
        uow=SQLiteUnitOfWork(database_path or app_paths.database_file),
        file_scanner=FilesystemFileScanner(),
        file_snapshot_reader=FilesystemFileSnapshotReader(metadata_reader=MutagenMetadataReader()),
        file_presence=FilesystemFilePresence(),
        config_store=store,
        path_resolver=FilesystemPathResolver(),
        clock=SystemClock(),
        id_generator=Uuid7IdGenerator(),
    )

    try:
        plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=options.source_path))
    except ConfigStoreValidationError as exc:
        write_validation_errors(stderr, exc.errors)
        return ERROR_EXIT_CODE
    except (AddLibrarySelectionError, AddSourceSelectionError) as exc:
        write_line(stderr, str(exc))
        return ERROR_EXIT_CODE
    except MetadataReadError as exc:
        write_line(stderr, f"Metadata read error: {exc}")
        return ERROR_EXIT_CODE
    except OSError as exc:
        write_line(stderr, f"Add I/O error: {exc}")
        return ERROR_EXIT_CODE

    _write_result(stdout, plan)
    if options.should_apply:
        return _apply_created_plan(plan, stdout, stderr, database_path, options=options)

    return SUCCESS_EXIT_CODE


@dataclass(frozen=True, slots=True)
class _AddCommandOptions:
    """Parsed add command options."""

    source_path: str | None
    should_apply: bool
    yes: bool


def _parse_args(args: Sequence[str]) -> _AddCommandOptions:
    source_path: str | None = None
    should_apply = False
    yes = False

    for arg in args:
        if arg == APPLY_FLAG:
            should_apply = True
        elif arg == YES_FLAG:
            yes = True
        elif not arg.startswith("-") and source_path is None:
            source_path = _normalize_source_path(arg)
        else:
            raise ValueError(ADD_USAGE_MESSAGE)

    if yes and not should_apply:
        raise ValueError(ADD_USAGE_MESSAGE)

    return _AddCommandOptions(source_path=source_path, should_apply=should_apply, yes=yes)


def _normalize_source_path(raw_path: FileSystemPath) -> str:
    return str(Path(raw_path).expanduser().resolve(strict=False))


def _write_result(stdout: TextIO, plan: Plan) -> None:
    blocked_count = sum(action.status == ActionStatus.BLOCKED for action in plan.actions)
    move_count = sum(
        action.action_type == ActionType.MOVE and action.status == ActionStatus.PLANNED for action in plan.actions
    )
    skip_count = sum(action.action_type == ActionType.SKIP for action in plan.actions)

    _ = stdout.write(f"Add plan created: {plan.plan_id}\n")
    _ = stdout.write(f"actions: {len(plan.actions)}\n")
    _ = stdout.write(f"move_actions: {move_count}\n")
    _ = stdout.write(f"skip_actions: {skip_count}\n")
    _ = stdout.write(f"blocked_actions: {blocked_count}\n")


def _apply_created_plan(
    plan: Plan,
    stdout: TextIO,
    stderr: TextIO,
    database_path: Path | None,
    *,
    options: _AddCommandOptions,
) -> int:
    if not confirm_apply(stdout, ConfirmationOptions(yes=options.yes)):
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
