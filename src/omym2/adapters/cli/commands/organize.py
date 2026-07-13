"""
Summary: Implements the organize CLI command.
Why: Exposes Library registration, review-plan creation, and optional apply.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.adapters.cli.commands.apply_execution import confirm_and_apply_plan
from omym2.adapters.cli.commands.confirmation import ConfirmationOptions
from omym2.adapters.cli.commands.output import write_line, write_usage, write_validation_errors
from omym2.domain.models.plan_action import ActionStatus
from omym2.features.common_ports import ConfigStoreValidationError, ExclusiveOperationBusyError, MetadataReadError
from omym2.features.organize.dto import CreateOrganizePlanRequest, OrganizeLibraryResult
from omym2.features.organize.usecases.create_organize_plan import (
    OrganizeLibrarySelectionError,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import TextIO

    from omym2.domain.models.run import Run
    from omym2.features.common_ports import FileSystemPath
    from omym2.shared.ids import PlanId

APPLY_FLAG = "--apply"
ERROR_EXIT_CODE = 1
LIBRARY_OPTION = "--library"
LIBRARY_OPTION_ARG_COUNT = 2
ORGANIZE_USAGE_MESSAGE = "Usage: omym2 organize [--library PATH] [--apply] [--trust-stat]"
SUCCESS_EXIT_CODE = 0
TRUST_STAT_FLAG = "--trust-stat"
USAGE_EXIT_CODE = 2


@dataclass(frozen=True, slots=True)
class OrganizeCommandDependencies:
    """Factories for the ports needed by organize plan creation and optional apply."""

    create_organize_plan: Callable[[CreateOrganizePlanRequest], OrganizeLibraryResult]
    apply_plan: Callable[[PlanId], Run]
    normalize_library_root: Callable[[FileSystemPath], str]


def run_organize_command(
    args: Sequence[str],
    stdout: TextIO,
    stderr: TextIO,
    dependencies: OrganizeCommandDependencies,
) -> int:
    """Run organize and return a process exit code."""
    try:
        options = _parse_args(args)
    except ValueError:
        write_usage(stderr, ORGANIZE_USAGE_MESSAGE)
        return USAGE_EXIT_CODE

    return _run_organize(options, stdout, stderr, dependencies)


def _run_organize(
    options: _OrganizeCommandOptions,
    stdout: TextIO,
    stderr: TextIO,
    dependencies: OrganizeCommandDependencies,
) -> int:
    # Normalize the library root in platform composition, then pass only values onward.
    normalized_library_root = (
        dependencies.normalize_library_root(options.library_root) if options.library_root is not None else None
    )
    try:
        result = dependencies.create_organize_plan(
            CreateOrganizePlanRequest(
                trust_stat=options.trust_stat,
                library_root=normalized_library_root,
            )
        )
    except ConfigStoreValidationError as exc:
        write_validation_errors(stderr, exc.errors)
        return ERROR_EXIT_CODE
    except OrganizeLibrarySelectionError as exc:
        write_line(stderr, str(exc))
        return ERROR_EXIT_CODE
    except MetadataReadError as exc:
        write_line(stderr, f"Metadata read error: {exc}")
        return ERROR_EXIT_CODE
    except (ExclusiveOperationBusyError, OSError) as exc:
        message = str(exc) if isinstance(exc, ExclusiveOperationBusyError) else f"Organize I/O error: {exc}"
        write_line(stderr, message)
        return ERROR_EXIT_CODE

    _write_result(stdout, result)
    if options.should_apply and result.plan is not None:
        return confirm_and_apply_plan(
            result.plan.plan_id,
            stdout,
            stderr,
            dependencies.apply_plan,
            confirmation=ConfirmationOptions(),
        )

    return SUCCESS_EXIT_CODE


@dataclass(frozen=True, slots=True)
class _OrganizeCommandOptions:
    """Parsed organize command options."""

    library_root: str | None
    should_apply: bool
    trust_stat: bool


def _parse_args(args: Sequence[str]) -> _OrganizeCommandOptions:
    library_root: str | None = None
    should_apply = False
    trust_stat = False
    index = 0

    while index < len(args):
        arg = args[index]
        if arg == APPLY_FLAG:
            should_apply = True
            index += 1
            continue

        if arg == TRUST_STAT_FLAG:
            trust_stat = True
            index += 1
            continue

        if arg == LIBRARY_OPTION:
            if library_root is not None or index + 1 >= len(args) or args[index + 1].startswith("-"):
                raise ValueError(ORGANIZE_USAGE_MESSAGE)
            library_root = args[index + 1]
            index += LIBRARY_OPTION_ARG_COUNT
            continue

        raise ValueError(ORGANIZE_USAGE_MESSAGE)

    return _OrganizeCommandOptions(
        library_root=library_root,
        should_apply=should_apply,
        trust_stat=trust_stat,
    )


def _write_result(stdout: TextIO, result: OrganizeLibraryResult) -> None:
    if result.plan is None:
        _ = stdout.write(f"Library registered: {result.library.library_id}\n")
        _ = stdout.write(f"tracks: {result.track_count}\n")
        return

    blocked_count = sum(action.status == ActionStatus.BLOCKED for action in result.actions)
    _ = stdout.write(f"Organize plan created: {result.plan.plan_id}\n")
    _ = stdout.write(f"actions: {len(result.actions)}\n")
    _ = stdout.write(f"blocked_actions: {blocked_count}\n")
