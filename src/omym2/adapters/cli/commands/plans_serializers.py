"""
Summary: Serializes plans CLI JSON payloads.
Why: Keeps machine-readable Plan output contracts explicit and testable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.artist_name_resolution import (
        ArtistNameDiagnostics,
        ArtistNameResolutionDiagnostic,
    )
    from omym2.domain.models.plan import Plan
    from omym2.domain.models.plan_action import PlanAction
    from omym2.features.plans.dto import PlanDetail
    from omym2.shared.ids import ActionId


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


def serialize_plan_action(
    action: PlanAction,
    depends_on_action_ids: tuple[ActionId, ...],
) -> dict[str, object]:
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
        "companion_asset_id": None if action.companion_asset_id is None else str(action.companion_asset_id),
        "owner_action_id": None if action.owner_action_id is None else str(action.owner_action_id),
        "depends_on_action_ids": [str(action_id) for action_id in depends_on_action_ids],
        "artist_name_diagnostics": _serialize_artist_name_diagnostics(action.artist_name_diagnostics),
    }


def _serialize_artist_name_diagnostics(diagnostics: ArtistNameDiagnostics | None) -> dict[str, object] | None:
    """Return the recorded artist and album-artist review snapshot."""
    if diagnostics is None:
        return None
    return {
        "artist": _serialize_artist_name_diagnostic(diagnostics.artist),
        "album_artist": _serialize_artist_name_diagnostic(diagnostics.album_artist),
    }


def _serialize_artist_name_diagnostic(diagnostic: ArtistNameResolutionDiagnostic) -> dict[str, object]:
    """Return one field's recorded resolution evidence."""
    return {
        "source_name": diagnostic.source_name,
        "resolved_name": diagnostic.resolved_name,
        "provenance": diagnostic.provenance.value,
        "issue": None if diagnostic.issue is None else diagnostic.issue.value,
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
        "actions": [
            serialize_plan_action(action, detail.action_dependencies.get(action.action_id, ()))
            for action in detail.actions
        ],
        "total_action_count": detail.total_action_count,
    }
