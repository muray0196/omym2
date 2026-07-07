"""
Summary: Implements the undo CLI command.
Why: Creates and optionally applies undo Plans from durable Run history.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.adapters.cli.commands.apply_execution import confirm_and_apply_plan
from omym2.adapters.cli.commands.confirmation import ConfirmationOptions
from omym2.adapters.cli.commands.output import write_line, write_usage
from omym2.domain.models.plan_action import ActionStatus
from omym2.features.common_ports import MetadataReadError
from omym2.features.undo.dto import CreateUndoPlanRequest
from omym2.features.undo.usecases.create_undo_plan import CreateUndoPlanUseCase, UndoPlanError
from omym2.shared.ids import RunId, parse_uuid

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import TextIO

    from omym2.domain.models.plan import Plan
    from omym2.features.apply.ports import ApplyPlanPorts
    from omym2.features.undo.ports import CreateUndoPlanPorts

APPLY_FLAG = "--apply"
ERROR_EXIT_CODE = 1
INVALID_RUN_ID_MESSAGE = "Invalid Run ID."
SUCCESS_EXIT_CODE = 0
UNDO_USAGE_MESSAGE = "Usage: omym2 undo <RUN_ID> [--apply]"
USAGE_EXIT_CODE = 2


@dataclass(frozen=True, slots=True)
class UndoCommandDependencies:
    """Factories for the ports needed by undo plan creation and optional apply."""

    create_undo_plan_ports_factory: Callable[[], CreateUndoPlanPorts]
    apply_plan_ports_factory: Callable[[], ApplyPlanPorts]


def run_undo_command(
    args: Sequence[str],
    stdout: TextIO,
    stderr: TextIO,
    dependencies: UndoCommandDependencies,
) -> int:
    """Run undo and return a process exit code."""
    try:
        options = _parse_args(args)
    except ValueError:
        write_usage(stderr, UNDO_USAGE_MESSAGE)
        return USAGE_EXIT_CODE

    ports = dependencies.create_undo_plan_ports_factory()

    try:
        plan = CreateUndoPlanUseCase(ports).execute(CreateUndoPlanRequest(options.run_id))
    except UndoPlanError as exc:
        write_line(stderr, str(exc))
        return ERROR_EXIT_CODE
    except MetadataReadError as exc:
        write_line(stderr, f"Metadata read error: {exc}")
        return ERROR_EXIT_CODE
    except OSError as exc:
        write_line(stderr, f"Undo I/O error: {exc}")
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
class _UndoCommandOptions:
    """Parsed undo command options."""

    run_id: RunId
    should_apply: bool


def _parse_args(args: Sequence[str]) -> _UndoCommandOptions:
    run_id: RunId | None = None
    should_apply = False

    for arg in args:
        if arg == APPLY_FLAG:
            should_apply = True
        elif arg.startswith("-") or run_id is not None:
            raise ValueError(UNDO_USAGE_MESSAGE)
        else:
            try:
                run_id = RunId(parse_uuid(arg))
            except ValueError as exc:
                raise ValueError(INVALID_RUN_ID_MESSAGE) from exc

    if run_id is None:
        raise ValueError(UNDO_USAGE_MESSAGE)

    return _UndoCommandOptions(run_id=run_id, should_apply=should_apply)


def _write_result(stdout: TextIO, plan: Plan) -> None:
    blocked_count = sum(action.status == ActionStatus.BLOCKED for action in plan.actions)
    _ = stdout.write(f"Undo plan created: {plan.plan_id}\n")
    _ = stdout.write(f"actions: {len(plan.actions)}\n")
    _ = stdout.write(f"move_actions: {len(plan.actions) - blocked_count}\n")
    _ = stdout.write(f"blocked_actions: {blocked_count}\n")
