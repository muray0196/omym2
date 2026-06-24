"""
Summary: Defines the Library check usecase contract.
Why: Allows later consistency checks to depend on read-only ports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.check_issue import CheckIssue
    from omym2.features.check.dto import CheckLibraryRequest
    from omym2.features.check.ports import CheckLibraryPorts

USECASE_DEFERRED_MESSAGE = "Check library behavior is deferred until the check vertical slice phase."


@dataclass(frozen=True, slots=True)
class CheckLibraryUseCase:
    """Contract for checking Library consistency."""

    ports: CheckLibraryPorts

    def execute(self, request: CheckLibraryRequest) -> tuple[CheckIssue, ...]:
        """Report read-only consistency issues for a Library."""
        # Phase 3 fixes the call shape only; Phase 11 owns check behavior.
        del request
        raise NotImplementedError(USECASE_DEFERRED_MESSAGE)
