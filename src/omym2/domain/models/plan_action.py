"""
Summary: Defines planned file operation actions.
Why: Preserves reviewed action data for later apply execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePath
from typing import TYPE_CHECKING

from omym2.shared.paths import normalize_library_relative_path

if TYPE_CHECKING:
    from omym2.shared.ids import ActionId, LibraryId, PlanId, TrackId


class ActionType(StrEnum):
    """Supported planned action types."""

    MOVE = "move"
    SKIP = "skip"
    REFRESH_METADATA = "refresh_metadata"


class ActionStatus(StrEnum):
    """Supported planned action statuses."""

    PLANNED = "planned"
    BLOCKED = "blocked"
    APPLIED = "applied"
    FAILED = "failed"


class PlanActionReason(StrEnum):
    """Documented reasons for blocked, skipped, or failed actions."""

    TARGET_EXISTS = "target_exists"
    MISSING_REQUIRED_METADATA = "missing_required_metadata"
    INVALID_PATH = "invalid_path"
    SOURCE_MISSING = "source_missing"
    SOURCE_CHANGED = "source_changed"
    DUPLICATE_HASH = "duplicate_hash"
    OPERATION_INTERRUPTED = "operation_interrupted"


@dataclass(frozen=True, slots=True)
class PlanAction:
    """One reviewed operation inside a Plan."""

    action_id: ActionId
    plan_id: PlanId
    library_id: LibraryId
    track_id: TrackId | None
    action_type: ActionType
    source_path: str | None
    target_path: str | None
    content_hash_at_plan: str | None
    metadata_hash_at_plan: str | None
    status: ActionStatus
    reason: PlanActionReason | None
    sort_order: int

    def __post_init__(self) -> None:
        """Normalize Library-managed path references stored in the action."""
        if self.source_path is not None and not PurePath(self.source_path).is_absolute():
            object.__setattr__(self, "source_path", normalize_library_relative_path(self.source_path))
        if self.target_path is not None and not PurePath(self.target_path).is_absolute():
            object.__setattr__(self, "target_path", normalize_library_relative_path(self.target_path))

    def mark_applied(self) -> PlanAction:
        """Return this action as applied after successful processing."""
        return self._with_status(ActionStatus.APPLIED, self.reason)

    def mark_blocked(self, reason: PlanActionReason) -> PlanAction:
        """Return this action as blocked by a plan-time issue."""
        return self._with_status(ActionStatus.BLOCKED, reason)

    def mark_failed(self, reason: PlanActionReason | None = None) -> PlanAction:
        """Return this action as failed by an apply-time issue."""
        return self._with_status(ActionStatus.FAILED, reason)

    def _with_status(self, status: ActionStatus, reason: PlanActionReason | None) -> PlanAction:
        return PlanAction(
            action_id=self.action_id,
            plan_id=self.plan_id,
            library_id=self.library_id,
            track_id=self.track_id,
            action_type=self.action_type,
            source_path=self.source_path,
            target_path=self.target_path,
            content_hash_at_plan=self.content_hash_at_plan,
            metadata_hash_at_plan=self.metadata_hash_at_plan,
            status=status,
            reason=reason,
            sort_order=self.sort_order,
        )
