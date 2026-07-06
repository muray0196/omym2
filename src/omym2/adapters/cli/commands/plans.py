"""
Summary: Implements the plans CLI command with filter, summary, diff, and JSON views.
Why: Exposes reviewed Plan list and detail inspection as the pre-apply review gate.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.adapters.cli.commands.output import write_json, write_line, write_usage
from omym2.adapters.cli.commands.plans_serializers import (
    serialize_plan_detail_response,
    serialize_plan_list_response,
)
from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.domain.models.plan import PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType
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

ACTIONS_OPTION = "--actions"
BLOCKED_ONLY_FLAG = "--blocked-only"
DIFF_FLAG = "--diff"
ERROR_EXIT_CODE = 1
FLAG_PREFIX = "-"
INVALID_PLAN_ID_MESSAGE = "Invalid Plan ID."
JSON_FLAG = "--json"
LIMIT_OPTION = "--limit"
NO_MATCHING_ACTIONS_MESSAGE = "No actions match filter."
NO_MATCHING_PLANS_MESSAGE = "No plans match filter."
NO_PLANS_MESSAGE = "No plans."
PLANS_DETAIL_USAGE_MESSAGE = (
    "Usage: omym2 plans <PLAN_ID> [--actions STATUS] [--blocked-only] [--summary] [--diff] [--json]"
)
PLANS_LIST_USAGE_MESSAGE = "Usage: omym2 plans [--status STATUS] [--type TYPE] [--limit N] [--json]"
STATUS_OPTION = "--status"
SUCCESS_EXIT_CODE = 0
SUMMARY_FLAG = "--summary"
TYPE_OPTION = "--type"
USAGE_EXIT_CODE = 2
VALUE_OPTION_ARG_COUNT = 2

_DETAIL_BOOLEAN_FLAGS = frozenset({BLOCKED_ONLY_FLAG, SUMMARY_FLAG, DIFF_FLAG, JSON_FLAG})


def run_plans_command(
    args: Sequence[str],
    stdout: TextIO,
    stderr: TextIO,
    database_path: Path | None = None,
) -> int:
    """Run plans and return a process exit code."""
    if len(args) > 0 and not args[0].startswith(FLAG_PREFIX):
        try:
            detail_options = _parse_detail_args(args[1:])
        except ValueError:
            write_usage(stderr, PLANS_DETAIL_USAGE_MESSAGE)
            return USAGE_EXIT_CODE
        return _run_plan_detail(args[0], detail_options, stdout, stderr, database_path)

    try:
        list_options = _parse_list_args(args)
    except ValueError:
        write_usage(stderr, PLANS_LIST_USAGE_MESSAGE)
        return USAGE_EXIT_CODE
    return _run_plan_list(list_options, stdout, database_path)


@dataclass(frozen=True, slots=True)
class _PlanListOptions:
    """Parsed plans list mode options."""

    status: PlanStatus | None
    plan_type: PlanType | None
    limit: int | None
    as_json: bool


@dataclass(frozen=True, slots=True)
class _PlanDetailOptions:
    """Parsed plans detail mode options."""

    action_status: ActionStatus | None
    summary: bool
    diff: bool
    as_json: bool


def _parse_list_args(args: Sequence[str]) -> _PlanListOptions:
    status: PlanStatus | None = None
    plan_type: PlanType | None = None
    limit: int | None = None
    as_json = False
    index = 0

    while index < len(args):
        arg = args[index]
        if arg == JSON_FLAG:
            as_json = True
            index += 1
            continue

        if arg == STATUS_OPTION:
            if status is not None or index + 1 >= len(args):
                raise ValueError(PLANS_LIST_USAGE_MESSAGE)
            status = PlanStatus(args[index + 1])
            index += VALUE_OPTION_ARG_COUNT
            continue

        if arg == TYPE_OPTION:
            if plan_type is not None or index + 1 >= len(args):
                raise ValueError(PLANS_LIST_USAGE_MESSAGE)
            plan_type = PlanType(args[index + 1])
            index += VALUE_OPTION_ARG_COUNT
            continue

        if arg == LIMIT_OPTION:
            if limit is not None or index + 1 >= len(args):
                raise ValueError(PLANS_LIST_USAGE_MESSAGE)
            limit = _parse_positive_int(args[index + 1])
            index += VALUE_OPTION_ARG_COUNT
            continue

        raise ValueError(PLANS_LIST_USAGE_MESSAGE)

    return _PlanListOptions(status=status, plan_type=plan_type, limit=limit, as_json=as_json)


def _parse_detail_args(args: Sequence[str]) -> _PlanDetailOptions:
    action_status: ActionStatus | None = None
    enabled_flags: set[str] = set()
    index = 0

    while index < len(args):
        arg = args[index]
        if arg in _DETAIL_BOOLEAN_FLAGS:
            enabled_flags.add(arg)
            index += 1
            continue

        if arg == ACTIONS_OPTION:
            if action_status is not None or index + 1 >= len(args):
                raise ValueError(PLANS_DETAIL_USAGE_MESSAGE)
            action_status = ActionStatus(args[index + 1])
            index += VALUE_OPTION_ARG_COUNT
            continue

        raise ValueError(PLANS_DETAIL_USAGE_MESSAGE)

    return _validated_detail_options(action_status, enabled_flags)


def _validated_detail_options(action_status: ActionStatus | None, enabled_flags: set[str]) -> _PlanDetailOptions:
    """Resolve --blocked-only sugar and reject invalid detail flag combinations."""
    if BLOCKED_ONLY_FLAG in enabled_flags:
        if action_status is not None:
            raise ValueError(PLANS_DETAIL_USAGE_MESSAGE)
        action_status = ActionStatus.BLOCKED

    summary = SUMMARY_FLAG in enabled_flags
    diff = DIFF_FLAG in enabled_flags
    as_json = JSON_FLAG in enabled_flags
    if summary and (action_status is not None or diff):
        raise ValueError(PLANS_DETAIL_USAGE_MESSAGE)
    if as_json and (summary or diff):
        raise ValueError(PLANS_DETAIL_USAGE_MESSAGE)

    return _PlanDetailOptions(action_status=action_status, summary=summary, diff=diff, as_json=as_json)


def _parse_positive_int(raw_value: str) -> int:
    value = int(raw_value)
    if value <= 0:
        raise ValueError(PLANS_LIST_USAGE_MESSAGE)
    return value


def _run_plan_list(options: _PlanListOptions, stdout: TextIO, database_path: Path | None) -> int:
    app_paths = default_application_paths()
    ports = PlanQueryPorts(uow=SQLiteUnitOfWork(database_path or app_paths.database_file))
    request = ListPlansRequest(status=options.status, plan_type=options.plan_type, limit=options.limit)
    plans = ListPlansUseCase(ports).execute(request)

    if options.as_json:
        write_json(stdout, serialize_plan_list_response(plans))
        return SUCCESS_EXIT_CODE

    if len(plans) == 0:
        has_filter = options.status is not None or options.plan_type is not None
        write_line(stdout, NO_MATCHING_PLANS_MESSAGE if has_filter else NO_PLANS_MESSAGE)
        return SUCCESS_EXIT_CODE

    for plan in plans:
        _write_plan_row(stdout, plan)
    return SUCCESS_EXIT_CODE


def _run_plan_detail(
    raw_plan_id: str,
    options: _PlanDetailOptions,
    stdout: TextIO,
    stderr: TextIO,
    database_path: Path | None,
) -> int:
    try:
        plan_id = PlanId(parse_uuid(raw_plan_id))
    except ValueError:
        write_line(stderr, INVALID_PLAN_ID_MESSAGE)
        return ERROR_EXIT_CODE

    app_paths = default_application_paths()
    ports = PlanQueryPorts(uow=SQLiteUnitOfWork(database_path or app_paths.database_file))
    try:
        detail = GetPlanDetailUseCase(ports).execute(
            GetPlanDetailRequest(plan_id=plan_id, action_status=options.action_status)
        )
    except PlanNotFoundError as exc:
        write_line(stderr, str(exc))
        return ERROR_EXIT_CODE

    if options.as_json:
        write_json(stdout, serialize_plan_detail_response(detail))
        return SUCCESS_EXIT_CODE

    filtered = options.action_status is not None
    if options.summary:
        _write_plan_summary(stdout, detail)
    elif options.diff:
        _write_plan_diff(stdout, detail, filtered=filtered)
    else:
        _write_plan_detail(stdout, detail, filtered=filtered)
    return SUCCESS_EXIT_CODE


def _write_plan_row(stdout: TextIO, plan: Plan) -> None:
    action_count = plan.summary.get("action_count", "0")
    row = (
        f"{plan.plan_id} type={plan.plan_type.value} status={plan.status.value} "
        f"actions={action_count} created_at={plan.created_at.isoformat()}\n"
    )
    _ = stdout.write(row)


def _write_plan_detail(stdout: TextIO, detail: PlanDetail, *, filtered: bool) -> None:
    _write_plan_header(stdout, detail.plan)
    _write_summary(stdout, detail.plan)
    if filtered and len(detail.actions) == 0:
        write_line(stdout, NO_MATCHING_ACTIONS_MESSAGE)
        return
    _write_actions(stdout, detail.actions)


def _write_plan_summary(stdout: TextIO, detail: PlanDetail) -> None:
    """Write header, persisted summary, and live tallies over recorded actions."""
    _write_plan_header(stdout, detail.plan)
    _write_summary(stdout, detail.plan)
    status_counts = Counter(action.status for action in detail.actions)
    _ = stdout.write("action_status_counts:\n")
    for status in ActionStatus:
        _ = stdout.write(f"  {status.value}: {status_counts[status]}\n")
    type_counts = Counter(action.action_type for action in detail.actions)
    _ = stdout.write("action_type_counts:\n")
    for action_type in ActionType:
        _ = stdout.write(f"  {action_type.value}: {type_counts[action_type]}\n")


def _write_plan_diff(stdout: TextIO, detail: PlanDetail, *, filtered: bool) -> None:
    """Write header and one arrow-style line per (filtered) recorded action."""
    _write_plan_header(stdout, detail.plan)
    if filtered and len(detail.actions) == 0:
        write_line(stdout, NO_MATCHING_ACTIONS_MESSAGE)
        return
    _ = stdout.write("diff:\n")
    for action in detail.actions:
        _ = stdout.write(f"{_diff_line(action)}\n")


def _diff_line(action: PlanAction) -> str:
    reason_suffix = "" if action.reason is None else f":{action.reason.value}"
    marker = f"[{action.action_type.value}|{action.status.value}{reason_suffix}]"
    if action.source_path is not None and action.source_path == action.target_path:
        return f"  {marker} {action.source_path} (no path change)"
    return f"  {marker} {_format_optional(action.source_path)} -> {_format_optional(action.target_path)}"


def _write_plan_header(stdout: TextIO, plan: Plan) -> None:
    _ = stdout.write(f"plan_id: {plan.plan_id}\n")
    _ = stdout.write(f"library_id: {plan.library_id}\n")
    _ = stdout.write(f"type: {plan.plan_type.value}\n")
    _ = stdout.write(f"status: {plan.status.value}\n")
    _ = stdout.write(f"created_at: {plan.created_at.isoformat()}\n")
    _ = stdout.write(f"library_root_at_plan: {plan.library_root_at_plan}\n")
    _ = stdout.write(f"config_hash: {plan.config_hash}\n")


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
