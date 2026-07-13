"""
Summary: Implements the add CLI command.
Why: Exposes incoming import Plan creation and optional apply orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.adapters.cli.commands.apply_execution import confirm_and_apply_plan
from omym2.adapters.cli.commands.confirmation import ConfirmationOptions
from omym2.adapters.cli.commands.output import write_line, write_usage, write_validation_errors
from omym2.domain.models.plan_action import ActionStatus, ActionType
from omym2.features.add.dto import CreateAddPlanRequest
from omym2.features.add.usecases.create_add_plan import (
    AddLibrarySelectionError,
    AddSourceSelectionError,
)
from omym2.features.common_ports import ConfigStoreValidationError, ExclusiveOperationBusyError, MetadataReadError

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import TextIO

    from omym2.domain.models.plan import Plan
    from omym2.domain.models.run import Run
    from omym2.features.common_ports import FileSystemPath
    from omym2.shared.ids import PlanId

ADD_USAGE_MESSAGE = "Usage: omym2 add [SOURCE_DIR] [--apply] [--yes]"
APPLY_FLAG = "--apply"
ERROR_EXIT_CODE = 1
SUCCESS_EXIT_CODE = 0
USAGE_EXIT_CODE = 2
YES_FLAG = "--yes"


@dataclass(frozen=True, slots=True)
class AddCommandDependencies:
    """Factories for the ports needed by add plan creation and optional apply."""

    create_add_plan: Callable[[CreateAddPlanRequest], Plan]
    apply_plan: Callable[[PlanId], Run]
    normalize_source_path: Callable[[FileSystemPath], str]


def run_add_command(
    args: Sequence[str],
    stdout: TextIO,
    stderr: TextIO,
    dependencies: AddCommandDependencies,
) -> int:
    """Run add and return a process exit code."""
    try:
        options = _parse_args(args)
    except ValueError:
        write_usage(stderr, ADD_USAGE_MESSAGE)
        return USAGE_EXIT_CODE

    return _run_add(options, stdout, stderr, dependencies)


def _run_add(
    options: _AddCommandOptions,
    stdout: TextIO,
    stderr: TextIO,
    dependencies: AddCommandDependencies,
) -> int:
    source_path = dependencies.normalize_source_path(options.source_path) if options.source_path is not None else None
    try:
        # Keep the normalization decision in platform wiring, not command adapters.
        plan = dependencies.create_add_plan(CreateAddPlanRequest(source_path=source_path))
    except ConfigStoreValidationError as exc:
        write_validation_errors(stderr, exc.errors)
        return ERROR_EXIT_CODE
    except (AddLibrarySelectionError, AddSourceSelectionError) as exc:
        write_line(stderr, str(exc))
        return ERROR_EXIT_CODE
    except MetadataReadError as exc:
        write_line(stderr, f"Metadata read error: {exc}")
        return ERROR_EXIT_CODE
    except (ExclusiveOperationBusyError, OSError) as exc:
        message = str(exc) if isinstance(exc, ExclusiveOperationBusyError) else f"Add I/O error: {exc}"
        write_line(stderr, message)
        return ERROR_EXIT_CODE

    _write_result(stdout, plan)
    if options.should_apply:
        return confirm_and_apply_plan(
            plan.plan_id,
            stdout,
            stderr,
            dependencies.apply_plan,
            confirmation=ConfirmationOptions(yes=options.yes),
        )

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
            source_path = arg
        else:
            raise ValueError(ADD_USAGE_MESSAGE)

    if yes and not should_apply:
        raise ValueError(ADD_USAGE_MESSAGE)

    return _AddCommandOptions(source_path=source_path, should_apply=should_apply, yes=yes)


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
