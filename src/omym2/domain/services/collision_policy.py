"""
Summary: Defines pure target collision decisions.
Why: Keeps conflict judgment out of repositories and filesystem adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from omym2.domain.models.plan_action import PlanActionReason
from omym2.shared.paths import normalize_library_relative_path

if TYPE_CHECKING:
    from collections.abc import Iterable


class CollisionDecisionKind(StrEnum):
    """Supported target collision decision kinds."""

    AVAILABLE = "available"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class CollisionDecision:
    """Result of checking one target path against occupied paths."""

    kind: CollisionDecisionKind
    reason: PlanActionReason | None = None


@dataclass(frozen=True, slots=True)
class CollisionPolicy:
    """Pure policy for target path conflicts."""

    def decide(self, target_path: str, occupied_paths: Iterable[str]) -> CollisionDecision:
        """Return whether a target path is available or blocked."""
        normalized_target = normalize_library_relative_path(target_path)
        normalized_occupied = {normalize_library_relative_path(path) for path in occupied_paths}
        if normalized_target in normalized_occupied:
            return CollisionDecision(CollisionDecisionKind.BLOCKED, PlanActionReason.TARGET_EXISTS)
        return CollisionDecision(CollisionDecisionKind.AVAILABLE)
