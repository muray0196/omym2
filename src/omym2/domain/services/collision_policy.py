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

    def decide(
        self,
        target_path: str,
        occupied_paths: Iterable[str],
        *,
        batch_target_count: int = 1,
    ) -> CollisionDecision:
        """Return whether a target path is available or blocked.

        `batch_target_count` is the number of distinct sources in the current
        plan batch that resolve to `target_path`. A value greater than one
        means the batch itself claims `target_path` more than once, which
        blocks independently of `occupied_paths` membership.
        """
        normalized_target = normalize_library_relative_path(target_path)
        normalized_occupied = {normalize_library_relative_path(path) for path in occupied_paths}
        if normalized_target in normalized_occupied or batch_target_count > 1:
            return CollisionDecision(CollisionDecisionKind.BLOCKED, PlanActionReason.TARGET_EXISTS)
        return CollisionDecision(CollisionDecisionKind.AVAILABLE)
