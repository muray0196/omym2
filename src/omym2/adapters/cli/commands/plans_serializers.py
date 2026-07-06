"""
Summary: Serializes plans CLI JSON payloads.
Why: Keeps machine-readable Plan output contracts explicit and testable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.plan import Plan
    from omym2.domain.models.plan_action import PlanAction
    from omym2.features.plans.dto import PlanDetail


def serialize_plan_row(plan: Plan) -> dict[str, object]:
    """Return a JSON-safe Plan list row."""
    return {
        "plan_id": str(plan.plan_id),
        "library_id": str(plan.library_id),
        "plan_type": plan.plan_type.value,
        "status": plan.status.value,
        "created_at": plan.created_at.isoformat(),
        "summary": dict(plan.summary),
    }


def serialize_plan_header(plan: Plan) -> dict[str, object]:
    """Return a JSON-safe Plan detail header."""
    return {
        **serialize_plan_row(plan),
        "config_hash": plan.config_hash,
        "library_root_at_plan": plan.library_root_at_plan,
    }


def serialize_plan_action(action: PlanAction) -> dict[str, object]:
    """Return a JSON-safe PlanAction payload."""
    return {
        "action_id": str(action.action_id),
        "plan_id": str(action.plan_id),
        "library_id": str(action.library_id),
        "track_id": None if action.track_id is None else str(action.track_id),
        "action_type": action.action_type.value,
        "source_path": action.source_path,
        "target_path": action.target_path,
        "content_hash_at_plan": action.content_hash_at_plan,
        "metadata_hash_at_plan": action.metadata_hash_at_plan,
        "status": action.status.value,
        "reason": None if action.reason is None else action.reason.value,
        "sort_order": action.sort_order,
    }


def serialize_plan_list_response(plans: tuple[Plan, ...]) -> dict[str, object]:
    """Return the plans list JSON response payload."""
    return {"plans": [serialize_plan_row(plan) for plan in plans]}


def serialize_plan_detail_response(detail: PlanDetail) -> dict[str, object]:
    """Return the plan detail JSON response payload.

    total_action_count reflects the unfiltered action count so scripts can
    detect --actions/--blocked-only filtered output.
    """
    return {
        "plan": serialize_plan_header(detail.plan),
        "actions": [serialize_plan_action(action) for action in detail.actions],
        "total_action_count": detail.total_action_count,
    }
