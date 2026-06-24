"""
Summary: Implements the plans CLI command.
Why: Exposes reviewed Plan list and detail inspection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from omym2.adapters.cli.commands.output import write_line, write_usage
from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.features.plans.dto import GetPlanDetailRequest, ListPlansRequest
from omym2.features.plans.ports import PlanQueryPorts
from omym2.features.plans.usecases.get_plan_detail import GetPlanDetailUseCase, PlanNotFoundError
from omym2.features.plans.usecases.list_plans import ListPlansUseCase
from omym2.shared.ids import PlanId, parse_uuid

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path
    from typing import TextIO

    from omym2.domain.models.plan import Plan
    from omym2.domain.models.plan_action import PlanAction
    from omym2.features.plans.dto import PlanDetail

ERROR_EXIT_CODE = 1
INVALID_PLAN_ID_MESSAGE = "Invalid Plan ID."
NO_PLANS_MESSAGE = "No plans."
PLANS_USAGE_MESSAGE = "Usage: omym2 plans [PLAN_ID]"
SUCCESS_EXIT_CODE = 0
USAGE_EXIT_CODE = 2


def run_plans_command(
    args: Sequence[str],
    stdout: TextIO,
    stderr: TextIO,
    database_path: Path | None = None,
) -> int:
    """Run plans and return a process exit code."""
    if len(args) > 1:
        write_usage(stderr, PLANS_USAGE_MESSAGE)
        return USAGE_EXIT_CODE

    if len(args) == 0:
        return _run_plan_list(stdout, database_path)
    return _run_plan_detail(args[0], stdout, stderr, database_path)


def _run_plan_list(stdout: TextIO, database_path: Path | None) -> int:
    app_paths = default_application_paths()
    ports = PlanQueryPorts(uow=SQLiteUnitOfWork(database_path or app_paths.database_file))
    plans = ListPlansUseCase(ports).execute(ListPlansRequest())

    if len(plans) == 0:
        write_line(stdout, NO_PLANS_MESSAGE)
        return SUCCESS_EXIT_CODE

    for plan in plans:
        _write_plan_row(stdout, plan)
    return SUCCESS_EXIT_CODE


def _run_plan_detail(raw_plan_id: str, stdout: TextIO, stderr: TextIO, database_path: Path | None) -> int:
    try:
        plan_id = PlanId(parse_uuid(raw_plan_id))
    except ValueError:
        write_line(stderr, INVALID_PLAN_ID_MESSAGE)
        return ERROR_EXIT_CODE

    app_paths = default_application_paths()
    ports = PlanQueryPorts(uow=SQLiteUnitOfWork(database_path or app_paths.database_file))
    try:
        detail = GetPlanDetailUseCase(ports).execute(GetPlanDetailRequest(plan_id=plan_id))
    except PlanNotFoundError as exc:
        write_line(stderr, str(exc))
        return ERROR_EXIT_CODE

    _write_plan_detail(stdout, detail)
    return SUCCESS_EXIT_CODE


def _write_plan_row(stdout: TextIO, plan: Plan) -> None:
    action_count = plan.summary.get("action_count", "0")
    row = (
        f"{plan.plan_id} type={plan.plan_type.value} status={plan.status.value} "
        f"actions={action_count} created_at={plan.created_at.isoformat()}\n"
    )
    _ = stdout.write(row)


def _write_plan_detail(stdout: TextIO, detail: PlanDetail) -> None:
    plan = detail.plan
    _ = stdout.write(f"plan_id: {plan.plan_id}\n")
    _ = stdout.write(f"library_id: {plan.library_id}\n")
    _ = stdout.write(f"type: {plan.plan_type.value}\n")
    _ = stdout.write(f"status: {plan.status.value}\n")
    _ = stdout.write(f"created_at: {plan.created_at.isoformat()}\n")
    _ = stdout.write(f"library_root_at_plan: {plan.library_root_at_plan}\n")
    _ = stdout.write(f"config_hash: {plan.config_hash}\n")
    _write_summary(stdout, plan)
    _write_actions(stdout, detail.actions)


def _write_summary(stdout: TextIO, plan: Plan) -> None:
    _ = stdout.write("summary:\n")
    for key, value in sorted(plan.summary.items()):
        _ = stdout.write(f"  {key}: {value}\n")


def _write_actions(stdout: TextIO, actions: tuple[PlanAction, ...]) -> None:
    _ = stdout.write("actions:\n")
    for action in actions:
        _ = stdout.write(f"  - action_id: {action.action_id}\n")
        _ = stdout.write(f"    type: {action.action_type.value}\n")
        _ = stdout.write(f"    status: {action.status.value}\n")
        _ = stdout.write(
            f"    reason: {_format_optional(action.reason.value if action.reason is not None else None)}\n"
        )
        _ = stdout.write(f"    source_path: {_format_optional(action.source_path)}\n")
        _ = stdout.write(f"    target_path: {_format_optional(action.target_path)}\n")


def _format_optional(value: str | None) -> str:
    if value is None:
        return "-"
    return value
