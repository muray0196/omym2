"""
Summary: Implements the check CLI command.
Why: Reports read-only DB and filesystem consistency issues.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from omym2.adapters.cli.commands.output import write_line, write_usage, write_validation_errors
from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.config.toml_config_store import TomlConfigStore
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.adapters.fs.file_scanner import FilesystemFileScanner
from omym2.adapters.fs.file_snapshot_reader import FilesystemFileSnapshotReader
from omym2.adapters.fs.path_resolver import FilesystemPathResolver
from omym2.adapters.metadata.mutagen_reader import MetadataReadError, MutagenMetadataReader
from omym2.features.check.dto import CheckLibraryRequest
from omym2.features.check.ports import CheckLibraryPorts
from omym2.features.check.usecases.check_library import CheckLibraryError, CheckLibraryUseCase
from omym2.features.common_ports import ConfigStoreValidationError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path
    from typing import TextIO

    from omym2.domain.models.check_issue import CheckIssue

CHECK_USAGE_MESSAGE = "Usage: omym2 check"
ERROR_EXIT_CODE = 1
NO_ISSUES_MESSAGE = "No issues."
SUCCESS_EXIT_CODE = 0
USAGE_EXIT_CODE = 2


def run_check_command(
    args: Sequence[str],
    stdout: TextIO,
    stderr: TextIO,
    config_path: Path | None = None,
    database_path: Path | None = None,
) -> int:
    """Run check and return a process exit code."""
    if len(args) != 0:
        write_usage(stderr, CHECK_USAGE_MESSAGE)
        return USAGE_EXIT_CODE

    return _run_check(stdout, stderr, config_path, database_path)


def _run_check(
    stdout: TextIO,
    stderr: TextIO,
    config_path: Path | None,
    database_path: Path | None,
) -> int:
    app_paths = default_application_paths()
    ports = CheckLibraryPorts(
        uow=SQLiteUnitOfWork(database_path or app_paths.database_file),
        file_scanner=FilesystemFileScanner(),
        file_snapshot_reader=FilesystemFileSnapshotReader(metadata_reader=MutagenMetadataReader()),
        config_store=TomlConfigStore(config_path or app_paths.config_file),
        path_resolver=FilesystemPathResolver(),
    )

    try:
        issues = CheckLibraryUseCase(ports).execute(CheckLibraryRequest())
    except ConfigStoreValidationError as exc:
        write_validation_errors(stderr, exc.errors)
        return ERROR_EXIT_CODE
    except CheckLibraryError as exc:
        write_line(stderr, str(exc))
        return ERROR_EXIT_CODE
    except MetadataReadError as exc:
        write_line(stderr, f"Metadata read error: {exc}")
        return ERROR_EXIT_CODE
    except OSError as exc:
        write_line(stderr, f"Check I/O error: {exc}")
        return ERROR_EXIT_CODE

    if len(issues) == 0:
        write_line(stdout, NO_ISSUES_MESSAGE)
        return SUCCESS_EXIT_CODE

    for issue in issues:
        _write_issue(stdout, issue)
    return ERROR_EXIT_CODE


def _write_issue(stdout: TextIO, issue: CheckIssue) -> None:
    row = (
        f"{issue.issue_type.value} library={issue.library_id} path={_optional(issue.path)} "
        f"track={_optional_id(issue.track_id)} plan={_optional_id(issue.plan_id)} detail={_optional(issue.detail)}\n"
    )
    _ = stdout.write(row)


def _optional(value: str | None) -> str:
    return "-" if value is None else value


def _optional_id(value: object | None) -> str:
    return "-" if value is None else str(value)
