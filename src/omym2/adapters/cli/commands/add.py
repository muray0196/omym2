"""
Summary: Implements the add CLI command.
Why: Exposes Phase 8 incoming import Plan creation.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from omym2.adapters.cli.commands.output import write_line, write_usage, write_validation_errors
from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.config.toml_config_store import TomlConfigStore
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.adapters.fs.file_presence import FilesystemFilePresence
from omym2.adapters.fs.file_scanner import FilesystemFileScanner
from omym2.adapters.fs.file_snapshot_reader import FilesystemFileSnapshotReader
from omym2.adapters.fs.path_resolver import FilesystemPathResolver
from omym2.adapters.metadata.mutagen_reader import MetadataReadError, MutagenMetadataReader
from omym2.domain.models.plan_action import ActionStatus, ActionType
from omym2.features.add.dto import CreateAddPlanRequest
from omym2.features.add.ports import CreateAddPlanPorts
from omym2.features.add.usecases.create_add_plan import (
    AddLibrarySelectionError,
    AddSourceSelectionError,
    CreateAddPlanUseCase,
)
from omym2.features.common_ports import ConfigStoreValidationError, SystemClock, Uuid7IdGenerator

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import TextIO

    from omym2.domain.models.plan import Plan
    from omym2.features.common_ports import FileSystemPath

ADD_APPLY_DEFERRED_MESSAGE = "add --apply is deferred until the apply vertical slice."
ADD_USAGE_MESSAGE = "Usage: omym2 add [SOURCE_DIR]"
APPLY_FLAG = "--apply"
ERROR_EXIT_CODE = 1
SUCCESS_EXIT_CODE = 0
USAGE_EXIT_CODE = 2


def run_add_command(
    args: Sequence[str],
    stdout: TextIO,
    stderr: TextIO,
    config_path: Path | None = None,
    database_path: Path | None = None,
) -> int:
    """Run add and return a process exit code."""
    if APPLY_FLAG in args:
        write_line(stderr, ADD_APPLY_DEFERRED_MESSAGE)
        return ERROR_EXIT_CODE

    try:
        source_path = _parse_source_path(args)
    except ValueError:
        write_usage(stderr, ADD_USAGE_MESSAGE)
        return USAGE_EXIT_CODE

    return _run_add(source_path, stdout, stderr, config_path, database_path)


def _run_add(
    source_path: str | None,
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
        plan = CreateAddPlanUseCase(ports).execute(CreateAddPlanRequest(source_path=source_path))
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
    return SUCCESS_EXIT_CODE


def _parse_source_path(args: Sequence[str]) -> str | None:
    if not args:
        return None
    if len(args) == 1 and not args[0].startswith("-"):
        return _normalize_source_path(args[0])
    raise ValueError(ADD_USAGE_MESSAGE)


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
