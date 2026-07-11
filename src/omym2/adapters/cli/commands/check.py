"""
Summary: Implements the check CLI command.
Why: Reports read-only DB and filesystem consistency issues.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from omym2.adapters.cli.commands.output import write_line, write_usage, write_validation_errors
from omym2.features.check.dto import CheckLibraryRequest
from omym2.features.check.usecases.check_library import CheckLibraryError, CheckLibraryUseCase
from omym2.features.common_ports import ConfigStoreValidationError, MetadataReadError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import TextIO

    from omym2.domain.models.check_issue import CheckIssue
    from omym2.features.check.ports import CheckLibraryPorts

CHECK_USAGE_MESSAGE = "Usage: omym2 check [--trust-stat]"
ERROR_EXIT_CODE = 1
NO_ISSUES_MESSAGE = "No issues."
SUCCESS_EXIT_CODE = 0
TRUST_STAT_FLAG = "--trust-stat"
USAGE_EXIT_CODE = 2


def run_check_command(
    args: Sequence[str],
    stdout: TextIO,
    stderr: TextIO,
    ports: CheckLibraryPorts,
) -> int:
    """Run check and return a process exit code."""
    if len(args) > 1 or (len(args) == 1 and args[0] != TRUST_STAT_FLAG):
        write_usage(stderr, CHECK_USAGE_MESSAGE)
        return USAGE_EXIT_CODE

    return _run_check(ports, stdout, stderr, trust_stat=len(args) == 1)


def _run_check(
    ports: CheckLibraryPorts,
    stdout: TextIO,
    stderr: TextIO,
    *,
    trust_stat: bool,
) -> int:
    try:
        result = CheckLibraryUseCase(ports).execute(CheckLibraryRequest(trust_stat=trust_stat))
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

    issues = result.issues
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
