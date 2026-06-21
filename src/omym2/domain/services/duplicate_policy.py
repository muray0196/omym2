"""
Summary: Defines pure duplicate content decisions.
Why: Keeps duplicate judgment separate from repositories and file scanners.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from omym2.domain.models.plan_action import PlanActionReason

if TYPE_CHECKING:
    from collections.abc import Iterable


class DuplicateDecisionKind(StrEnum):
    """Supported duplicate content decision kinds."""

    UNIQUE = "unique"
    SKIP = "skip"


@dataclass(frozen=True, slots=True)
class DuplicateDecision:
    """Result of checking one content hash against known hashes."""

    kind: DuplicateDecisionKind
    reason: PlanActionReason | None = None


@dataclass(frozen=True, slots=True)
class DuplicatePolicy:
    """Pure policy for duplicate content hashes."""

    def decide(self, content_hash: str, known_hashes: Iterable[str]) -> DuplicateDecision:
        """Return whether content should be imported or skipped."""
        if content_hash in set(known_hashes):
            return DuplicateDecision(DuplicateDecisionKind.SKIP, PlanActionReason.DUPLICATE_HASH)
        return DuplicateDecision(DuplicateDecisionKind.UNIQUE)
