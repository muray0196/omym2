"""
Summary: Implements the refresh CLI command.
Why: Exposes relocation Plan creation after external tag correction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.adapters.cli.commands.apply_execution import confirm_and_apply_plan
from omym2.adapters.cli.commands.confirmation import ConfirmationOptions
from omym2.adapters.cli.commands.output import write_line, write_usage, write_validation_errors
from omym2.domain.models.plan_action import ActionStatus, ActionType
from omym2.features.common_ports import ConfigStoreValidationError, MetadataReadError
from omym2.features.refresh.dto import CreateRefreshPlanRequest
from omym2.features.refresh.usecases.create_refresh_plan import (
    CreateRefreshPlanUseCase,
    RefreshLibrarySelectionError,
    RefreshTargetSelectionError,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import TextIO

    from omym2.domain.models.plan import Plan
    from omym2.features.apply.ports import ApplyPlanPorts
    from omym2.features.common_ports import FileSystemPath
    from omym2.features.refresh.ports import CreateRefreshPlanPorts

ALL_FLAG = "--all"
APPLY_FLAG = "--apply"
ERROR_EXIT_CODE = 1
REFRESH_USAGE_MESSAGE = "Usage: omym2 refresh (<file|dir>|--all) [--apply]"
SUCCESS_EXIT_CODE = 0
USAGE_EXIT_CODE = 2


@dataclass(frozen=True, slots=True)
class RefreshCommandDependencies:
    """Factories for the ports needed by refresh plan creation and optional apply."""

    create_refresh_plan_ports_factory: Callable[[], CreateRefreshPlanPorts]
    apply_plan_ports_factory: Callable[[], ApplyPlanPorts]
    normalize_target_path: Callable[[FileSystemPath], str]


def run_refresh_command(
    args: Sequence[str],
    stdout: TextIO,
    stderr: TextIO,
    dependencies: RefreshCommandDependencies,
) -> int:
    """Run refresh and return a process exit code."""
    try:
        options = _parse_args(args)
    except ValueError:
        write_usage(stderr, REFRESH_USAGE_MESSAGE)
        return USAGE_EXIT_CODE

    return _run_refresh(options, stdout, stderr, dependencies)


def _run_refresh(
    options: _RefreshCommandOptions,
    stdout: TextIO,
    stderr: TextIO,
    dependencies: RefreshCommandDependencies,
) -> int:
    target_path = dependencies.normalize_target_path(options.target_path) if options.target_path is not None else None
    ports = dependencies.create_refresh_plan_ports_factory()

    try:
        plan = CreateRefreshPlanUseCase(ports).execute(
            CreateRefreshPlanRequest(target_path=target_path, include_all=options.include_all)
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
        return confirm_and_apply_plan(
            plan.plan_id,
            stdout,
            stderr,
            dependencies.apply_plan_ports_factory,
            confirmation=ConfirmationOptions(),
        )

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
            target_path = arg
        else:
            raise ValueError(REFRESH_USAGE_MESSAGE)

    if sum((target_path is not None, include_all)) != 1:
        raise ValueError(REFRESH_USAGE_MESSAGE)

    return _RefreshCommandOptions(target_path=target_path, include_all=include_all, should_apply=should_apply)


def _write_result(stdout: TextIO, plan: Plan) -> None:
    blocked_count = sum(action.status == ActionStatus.BLOCKED for action in plan.actions)
    move_count = sum(
        action.action_type == ActionType.MOVE and action.status == ActionStatus.PLANNED for action in plan.actions
    )

    _ = stdout.write(f"Refresh plan created: {plan.plan_id}\n")
    _ = stdout.write(f"actions: {len(plan.actions)}\n")
    _ = stdout.write(f"move_actions: {move_count}\n")
    _ = stdout.write(f"blocked_actions: {blocked_count}\n")
