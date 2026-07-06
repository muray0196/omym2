"""
Summary: Serializes Web API response payloads.
Why: Keeps JSON contracts explicit instead of exposing domain objects directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from omym2.config import (
    ALLOWED_ALBUM_YEAR_RESOLUTION_METHODS,
    ALLOWED_COLLISION_DUPLICATE_HASH_POLICIES,
    ALLOWED_COLLISION_MISSING_METADATA_POLICIES,
    ALLOWED_COLLISION_TARGET_EXISTS_POLICIES,
    ALLOWED_COMMAND_MODES,
    ALLOWED_PATH_POLICY_DISC_NUMBER_CONDITIONS,
    ALLOWED_PATH_POLICY_DISC_NUMBER_STYLES,
    ALLOWED_UI_THEMES,
)

if TYPE_CHECKING:
    from omym2.adapters.web.schemas.settings_changes import SettingsChange
    from omym2.domain.models.app_config import AppConfig
    from omym2.domain.models.check_issue import CheckIssue
    from omym2.domain.models.file_event import FileEvent
    from omym2.domain.models.library import Library
    from omym2.domain.models.plan import Plan
    from omym2.domain.models.plan_action import PlanAction
    from omym2.domain.models.run import Run
    from omym2.domain.models.track import Track
    from omym2.domain.models.track_metadata import TrackMetadata
    from omym2.features.artist_ids.dto import GenerateArtistIdsResult
    from omym2.features.organize.dto import OrganizeLibraryResult
    from omym2.features.plans.dto import PlanDetail
    from omym2.features.settings.dto import PathPolicyPreviewResult, ValidateSettingsResult


def serialize_app_config(config: AppConfig) -> dict[str, object]:
    """Return a JSON-safe AppConfig payload."""
    return {
        "version": config.version,
        "paths": {"library": config.paths.library, "incoming": config.paths.incoming},
        "add": {"default_mode": config.add.default_mode, "auto_apply": config.add.auto_apply},
        "organize": {
            "default_mode": config.organize.default_mode,
            "auto_apply": config.organize.auto_apply,
            "only_misplaced": config.organize.only_misplaced,
        },
        "refresh": {"default_mode": config.refresh.default_mode, "auto_apply": config.refresh.auto_apply},
        "path_policy": {
            "template": config.path_policy.template,
            "unknown_artist": config.path_policy.unknown_artist,
            "unknown_album": config.path_policy.unknown_album,
            "sanitize": config.path_policy.sanitize,
            "max_filename_length": config.path_policy.max_filename_length,
            "disc_number_style": config.path_policy.disc_number_style,
            "disc_number_condition": config.path_policy.disc_number_condition,
        },
        "artist_ids": {
            "max_length": config.artist_ids.max_length,
            "fallback_id": config.artist_ids.fallback_id,
            "entries": dict(sorted((config.artist_ids.entries or {}).items())),
        },
        "metadata": {
            "prefer_album_artist": config.metadata.prefer_album_artist,
            "require_title": config.metadata.require_title,
            "require_artist": config.metadata.require_artist,
            "require_album": config.metadata.require_album,
            "album_year_resolution": config.metadata.album_year_resolution,
        },
        "collision": {
            "on_target_exists": config.collision.on_target_exists,
            "on_duplicate_hash": config.collision.on_duplicate_hash,
            "on_missing_metadata": config.collision.on_missing_metadata,
        },
        "ui": {"theme": config.ui.theme, "show_advanced_settings": config.ui.show_advanced_settings},
    }


def serialize_settings_choices() -> dict[str, object]:
    """Return supported settings choices for select controls."""
    return {
        "command_modes": sorted(ALLOWED_COMMAND_MODES),
        "duplicate_hash_policies": sorted(ALLOWED_COLLISION_DUPLICATE_HASH_POLICIES),
        "missing_metadata_policies": sorted(ALLOWED_COLLISION_MISSING_METADATA_POLICIES),
        "target_exists_policies": sorted(ALLOWED_COLLISION_TARGET_EXISTS_POLICIES),
        "album_year_resolution_methods": sorted(ALLOWED_ALBUM_YEAR_RESOLUTION_METHODS),
        "disc_number_styles": sorted(ALLOWED_PATH_POLICY_DISC_NUMBER_STYLES),
        "disc_number_conditions": sorted(ALLOWED_PATH_POLICY_DISC_NUMBER_CONDITIONS),
        "ui_themes": sorted(ALLOWED_UI_THEMES),
    }


def serialize_validation_result(result: ValidateSettingsResult) -> dict[str, object]:
    """Return a JSON-safe validation result."""
    return {"valid": result.valid, "errors": list(result.errors), "config_hash": result.config_hash}


def serialize_path_preview(result: PathPolicyPreviewResult) -> dict[str, object]:
    """Return a JSON-safe path policy preview result."""
    return {"path": result.path, "errors": list(result.errors)}


def serialize_artist_id_generation(result: GenerateArtistIdsResult) -> dict[str, object]:
    """Return a JSON-safe artist ID generation result."""
    return {
        "entries": [
            {
                "source_artist": entry.source_artist,
                "generation_artist": entry.generation_artist,
                "artist_id": entry.artist_id,
                "saved": entry.saved,
                "overwritten": entry.overwritten,
            }
            for entry in result.entries
        ]
    }


def serialize_settings_change(change: SettingsChange) -> dict[str, object]:
    """Return a JSON-safe settings change."""
    return {"label": change.label, "before": change.before, "after": change.after}


def serialize_run_summary(run: Run) -> dict[str, object]:
    """Return a JSON-safe Run summary."""
    return {
        "run_id": str(run.run_id),
        "plan_id": str(run.plan_id),
        "library_id": str(run.library_id),
        "status": run.status.value,
        "started_at": run.started_at.isoformat(),
        "completed_at": None if run.completed_at is None else run.completed_at.isoformat(),
        "error_summary": run.error_summary,
    }


def serialize_run_detail(run: Run, file_events: tuple[FileEvent, ...]) -> dict[str, object]:
    """Return a JSON-safe Run detail payload."""
    return {"run": serialize_run_summary(run), "file_events": [serialize_file_event(event) for event in file_events]}


def serialize_file_event(event: FileEvent) -> dict[str, object]:
    """Return a JSON-safe FileEvent payload."""
    return {
        "event_id": str(event.event_id),
        "library_id": str(event.library_id),
        "run_id": str(event.run_id),
        "plan_action_id": str(event.plan_action_id),
        "event_type": event.event_type.value,
        "source_path": event.source_path,
        "target_path": event.target_path,
        "status": event.status.value,
        "started_at": event.started_at.isoformat(),
        "completed_at": None if event.completed_at is None else event.completed_at.isoformat(),
        "error_code": event.error_code,
        "error_message": event.error_message,
        "sequence_no": event.sequence_no,
    }


def serialize_check_issue(issue: CheckIssue) -> dict[str, object]:
    """Return a JSON-safe check issue."""
    return {
        "issue_type": issue.issue_type.value,
        "library_id": str(issue.library_id),
        "path": issue.path,
        "track_id": None if issue.track_id is None else str(issue.track_id),
        "plan_id": None if issue.plan_id is None else str(issue.plan_id),
        "detail": issue.detail,
    }


def serialize_track_summary(track: Track) -> dict[str, object]:
    """Return a JSON-safe Track summary."""
    return {
        "track_id": str(track.track_id),
        "library_id": str(track.library_id),
        "current_path": track.current_path,
        "canonical_path": track.canonical_path,
        "content_hash": track.content_hash,
        "metadata_hash": track.metadata_hash,
        "metadata": serialize_track_metadata(track.metadata),
        "status": track.status.value,
        "first_seen_at": track.first_seen_at.isoformat(),
        "last_seen_at": track.last_seen_at.isoformat(),
        "updated_at": track.updated_at.isoformat(),
    }


def serialize_track_metadata(metadata: TrackMetadata) -> dict[str, object]:
    """Return a JSON-safe TrackMetadata payload."""
    return {
        "title": metadata.title,
        "artist": metadata.artist,
        "album": metadata.album,
        "album_artist": metadata.album_artist,
        "genre": metadata.genre,
        "year": metadata.year,
        "track_number": metadata.track_number,
        "track_total": metadata.track_total,
        "disc_number": metadata.disc_number,
        "disc_total": metadata.disc_total,
    }


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


def serialize_plan_detail(detail: PlanDetail) -> dict[str, object]:
    """Return a JSON-safe Plan detail payload."""
    return serialize_plan_detail_parts(
        detail.plan,
        detail.actions,
        total_action_count=detail.total_action_count,
    )


def serialize_plan_detail_parts(
    plan: Plan,
    actions: tuple[PlanAction, ...],
    *,
    total_action_count: int | None = None,
) -> dict[str, object]:
    """Return Plan detail fields from a Plan and selected actions."""
    return {
        "plan": serialize_plan_header(plan),
        "actions": [serialize_plan_action(action) for action in actions],
        "total_action_count": len(actions) if total_action_count is None else total_action_count,
    }


def serialize_organize_registration(result: OrganizeLibraryResult) -> dict[str, object]:
    """Return the clean registration payload for organize without a Plan."""
    return {
        "library": serialize_library_registration(result.library),
        "track_count": result.track_count,
    }


def serialize_library_registration(library: Library) -> dict[str, object]:
    """Return a JSON-safe Library registration summary."""
    return {
        "library_id": str(library.library_id),
        "root_path": library.root_path,
        "path_policy_hash": library.path_policy_hash,
        "registered_at": None if library.registered_at is None else library.registered_at.isoformat(),
        "status": library.status.value,
        "created_at": library.created_at.isoformat(),
        "updated_at": library.updated_at.isoformat(),
    }
