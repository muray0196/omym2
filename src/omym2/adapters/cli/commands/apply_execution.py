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
from omym2.features.apply.dto import ApplyOptions, ApplyPlanRequest
from omym2.features.apply.usecases.apply_plan import ApplyPlanError, ApplyPlanUseCase

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import TextIO

    from omym2.features.apply.ports import ApplyPlanPorts
    from omym2.shared.ids import PlanId

ERROR_EXIT_CODE = 1
SUCCESS_EXIT_CODE = 0


def execute_and_report_apply(
    plan_id: PlanId,
    stdout: TextIO,
    stderr: TextIO,
    apply_plan_ports_factory: Callable[[], ApplyPlanPorts],
) -> int:
    """Build apply ports, run ApplyPlanUseCase, print the standard result lines, and map the exit code."""
    ports = apply_plan_ports_factory()

    try:
        run = ApplyPlanUseCase(ports).execute(ApplyPlanRequest(plan_id, options=ApplyOptions(yes=True)))
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


def confirm_and_apply_plan(
    plan_id: PlanId,
    stdout: TextIO,
    stderr: TextIO,
    apply_plan_ports_factory: Callable[[], ApplyPlanPorts],
    *,
    confirmation: ConfirmationOptions,
) -> int:
    """Confirm the apply with the user, then execute and report it."""
    if not confirm_apply(stdout, confirmation):
        write_line(stderr, APPLY_CANCELLED_MESSAGE)
        return ERROR_EXIT_CODE
    return execute_and_report_apply(plan_id, stdout, stderr, apply_plan_ports_factory)
