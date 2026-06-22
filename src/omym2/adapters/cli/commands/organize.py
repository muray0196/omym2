"""
Summary: Implements the organize CLI command.
Why: Exposes Phase 7 Library registration and review-plan creation.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.config.toml_config_store import TomlConfigStore
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.adapters.fs.file_scanner import FilesystemFileScanner
from omym2.adapters.fs.file_snapshot_reader import FilesystemFileSnapshotReader
from omym2.adapters.fs.path_resolver import FilesystemPathResolver
from omym2.adapters.metadata.mutagen_reader import MetadataReadError, MutagenMetadataReader
from omym2.domain.models.plan_action import ActionStatus
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
ORGANIZE_APPLY_DEFERRED_MESSAGE = "organize --apply is deferred until the apply vertical slice."
ORGANIZE_USAGE_MESSAGE = "Usage: omym2 organize [--library PATH]"
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
    exit_code = SUCCESS_EXIT_CODE
    if APPLY_FLAG in args:
        _ = stderr.write(f"{ORGANIZE_APPLY_DEFERRED_MESSAGE}\n")
        exit_code = ERROR_EXIT_CODE
    else:
        try:
            library_root = _parse_library_root(args)
        except ValueError:
            _write_usage(stderr)
            exit_code = USAGE_EXIT_CODE
        else:
            exit_code = _run_organize(library_root, stdout, stderr, config_path, database_path)
    return exit_code


def _run_organize(
    library_root: str | None,
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
        result = CreateOrganizePlanUseCase(ports).execute(CreateOrganizePlanRequest(library_root=library_root))
    except ConfigStoreValidationError as exc:
        _write_validation_errors(stderr, exc.errors)
        return ERROR_EXIT_CODE
    except OrganizeLibrarySelectionError as exc:
        _ = stderr.write(f"{exc}\n")
        return ERROR_EXIT_CODE
    except MetadataReadError as exc:
        _ = stderr.write(f"Metadata read error: {exc}\n")
        return ERROR_EXIT_CODE
    except OSError as exc:
        _ = stderr.write(f"Organize I/O error: {exc}\n")
        return ERROR_EXIT_CODE

    _write_result(stdout, result)
    return SUCCESS_EXIT_CODE


def _parse_library_root(args: Sequence[str]) -> str | None:
    if len(args) == 0:
        return None
    if len(args) == LIBRARY_OPTION_ARG_COUNT and args[0] == LIBRARY_OPTION:
        return _normalize_library_root(args[1])
    raise ValueError(ORGANIZE_USAGE_MESSAGE)


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


def _write_usage(stderr: TextIO) -> None:
    _ = stderr.write(f"{ORGANIZE_USAGE_MESSAGE}\n")


def _write_validation_errors(stderr: TextIO, errors: tuple[str, ...]) -> None:
    stderr.writelines(f"{error}\n" for error in errors)
