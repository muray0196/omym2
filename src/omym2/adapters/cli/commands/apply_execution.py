"""
Summary: Provides shared apply-execution helpers for CLI commands that create then optionally apply a Plan.
Why: Removes the duplicated ApplyPlanPorts execution, result printing, and exit-code mapping from 5 command modules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from omym2.adapters.cli.commands.confirmation import (
    APPLY_CANCELLED_MESSAGE,
    ConfirmationOptions,
    confirm_apply,
)
from omym2.adapters.cli.commands.output import write_line
from omym2.domain.models.run import RunStatus
from omym2.features.apply.usecases.apply_plan import ApplyPlanError
from omym2.features.common_ports import ExclusiveOperationBusyError

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import TextIO

    from omym2.domain.models.run import Run
    from omym2.shared.ids import PlanId

ERROR_EXIT_CODE = 1
SUCCESS_EXIT_CODE = 0


def execute_and_report_apply(
    plan_id: PlanId,
    stdout: TextIO,
    stderr: TextIO,
    apply_plan: Callable[[PlanId], Run],
) -> int:
    """Run the composed Apply flow, print its result lines, and map the exit code."""
    try:
        run = apply_plan(plan_id)
    except (ApplyPlanError, ExclusiveOperationBusyError) as exc:
        write_line(stderr, str(exc))
        return ERROR_EXIT_CODE

    _ = stdout.write(f"Apply run completed: {run.run_id}\n")
    _ = stdout.write(f"status: {run.status.value}\n")
    if run.status in {RunStatus.FAILED, RunStatus.PARTIAL_FAILED}:
        return ERROR_EXIT_CODE
    return SUCCESS_EXIT_CODE


def confirm_and_apply_plan(
    plan_id: PlanId,
    stdout: TextIO,
    stderr: TextIO,
    apply_plan: Callable[[PlanId], Run],
    *,
    confirmation: ConfirmationOptions,
) -> int:
    """Confirm the apply with the user, then execute and report it."""
    if not confirm_apply(stdout, confirmation):
        write_line(stderr, APPLY_CANCELLED_MESSAGE)
        return ERROR_EXIT_CODE
    return execute_and_report_apply(plan_id, stdout, stderr, apply_plan)
