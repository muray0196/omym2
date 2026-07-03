"""
Summary: Implements path policy preview for settings screens.
Why: Lets adapters show generated paths without duplicating domain policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.domain.services.path_policy import PathPolicy
from omym2.features.settings.dto import PathPolicyPreviewResult

if TYPE_CHECKING:
    from omym2.features.settings.dto import PathPolicyPreviewRequest


@dataclass(frozen=True, slots=True)
class PreviewPathPolicyUseCase:
    """Render a sample canonical path using the supplied path policy."""

    def execute(self, request: PathPolicyPreviewRequest) -> PathPolicyPreviewResult:
        """Return the rendered preview path or validation errors."""
        try:
            preview_path = PathPolicy.from_path_policy_config(request.path_policy, request.artist_ids).canonical_path(
                request.metadata,
                request.file_extension,
            )
        except ValueError as exc:
            return PathPolicyPreviewResult(path=None, errors=(str(exc),))
        return PathPolicyPreviewResult(path=preview_path, errors=())
