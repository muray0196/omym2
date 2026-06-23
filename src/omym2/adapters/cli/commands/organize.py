"""
Summary: Implements the organize CLI command.
Why: Exposes Library registration, review-plan creation, and optional apply.
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
from omym2.adapters.fs.file_scanner import FilesystemFileScanner
from omym2.adapters.fs.file_snapshot_reader import FilesystemFileSnapshotReader
from omym2.adapters.fs.path_resolver import FilesystemPathResolver
from omym2.adapters.metadata.mutagen_reader import MetadataReadError, MutagenMetadataReader
from omym2.domain.models.plan_action import ActionStatus
from omym2.domain.models.run import RunStatus
from omym2.features.apply.dto import ApplyOptions, ApplyPlanRequest
from omym2.features.apply.ports import ApplyPlanPorts
from omym2.features.apply.usecases.apply_plan import ApplyPlanError, ApplyPlanUseCase
from omym2.features.common_ports import ConfigStoreValidationError, SystemClock, Uuid7IdGenerator
from omym2.features.organize.dto import CreateOrganizePlanRequest, OrganizeLibraryResult
from omym2.features.organize.ports import CreateOrganizePlanPorts
from omym2.features.organize.usecases.create_organize_plan import (
    CreateOrganizePlanUseCase,
    OrganizeLibrarySelectionError,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import TextIO

    from omym2.features.common_ports import FileSystemPath

APPLY_FLAG = "--apply"
ERROR_EXIT_CODE = 1
LIBRARY_OPTION = "--library"
LIBRARY_OPTION_ARG_COUNT = 2
ORGANIZE_USAGE_MESSAGE = "Usage: omym2 organize [--library PATH] [--apply]"
SUCCESS_EXIT_CODE = 0
USAGE_EXIT_CODE = 2


def run_organize_command(
    args: Sequence[str],
    stdout: TextIO,
    stderr: TextIO,
    config_path: Path | None = None,
    database_path: Path | None = None,
) -> int:
    """Run organize and return a process exit code."""
    try:
        options = _parse_args(args)
    except ValueError:
        write_usage(stderr, ORGANIZE_USAGE_MESSAGE)
        return USAGE_EXIT_CODE

    return _run_organize(options, stdout, stderr, config_path, database_path)


def _run_organize(
    options: _OrganizeCommandOptions,
    stdout: TextIO,
    stderr: TextIO,
    config_path: Path | None,
    database_path: Path | None,
) -> int:
    app_paths = default_application_paths()
    store = TomlConfigStore(config_path or app_paths.config_file)
    ports = CreateOrganizePlanPorts(
        uow=SQLiteUnitOfWork(database_path or app_paths.database_file),
        file_scanner=FilesystemFileScanner(),
        file_snapshot_reader=FilesystemFileSnapshotReader(metadata_reader=MutagenMetadataReader()),
        config_store=store,
        path_resolver=FilesystemPathResolver(),
        clock=SystemClock(),
        id_generator=Uuid7IdGenerator(),
    )

    try:
        result = CreateOrganizePlanUseCase(ports).execute(CreateOrganizePlanRequest(library_root=options.library_root))
    except ConfigStoreValidationError as exc:
        write_validation_errors(stderr, exc.errors)
        return ERROR_EXIT_CODE
    except OrganizeLibrarySelectionError as exc:
        write_line(stderr, str(exc))
        return ERROR_EXIT_CODE
    except MetadataReadError as exc:
        write_line(stderr, f"Metadata read error: {exc}")
        return ERROR_EXIT_CODE
    except OSError as exc:
        write_line(stderr, f"Organize I/O error: {exc}")
        return ERROR_EXIT_CODE

    _write_result(stdout, result)
    if options.should_apply and result.plan is not None:
        return _apply_created_plan(result, stdout, stderr, database_path)

    return SUCCESS_EXIT_CODE


@dataclass(frozen=True, slots=True)
class _OrganizeCommandOptions:
    """Parsed organize command options."""

    library_root: str | None
    should_apply: bool


def _parse_args(args: Sequence[str]) -> _OrganizeCommandOptions:
    library_root: str | None = None
    should_apply = False
    index = 0

    while index < len(args):
        arg = args[index]
        if arg == APPLY_FLAG:
            should_apply = True
            index += 1
            continue

        if arg == LIBRARY_OPTION:
            if library_root is not None or index + 1 >= len(args):
                raise ValueError(ORGANIZE_USAGE_MESSAGE)
            library_root = _normalize_library_root(args[index + 1])
            index += LIBRARY_OPTION_ARG_COUNT
            continue

        raise ValueError(ORGANIZE_USAGE_MESSAGE)

    return _OrganizeCommandOptions(library_root=library_root, should_apply=should_apply)


def _normalize_library_root(raw_path: FileSystemPath) -> str:
    return str(Path(raw_path).expanduser().resolve(strict=False))


def _write_result(stdout: TextIO, result: OrganizeLibraryResult) -> None:
    if result.plan is None:
        _ = stdout.write(f"Library registered: {result.library.library_id}\n")
        _ = stdout.write(f"tracks: {result.track_count}\n")
        return

    blocked_count = sum(action.status == ActionStatus.BLOCKED for action in result.actions)
    _ = stdout.write(f"Organize plan created: {result.plan.plan_id}\n")
    _ = stdout.write(f"actions: {len(result.actions)}\n")
    _ = stdout.write(f"blocked_actions: {blocked_count}\n")


def _apply_created_plan(
    result: OrganizeLibraryResult,
    stdout: TextIO,
    stderr: TextIO,
    database_path: Path | None,
) -> int:
    if result.plan is None:
        return SUCCESS_EXIT_CODE

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
        run = ApplyPlanUseCase(ports).execute(ApplyPlanRequest(result.plan.plan_id, options=ApplyOptions(yes=True)))
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
