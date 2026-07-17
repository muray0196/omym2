"""
Summary: Implements path policy preview for settings screens.
Why: Lets adapters show generated paths without duplicating domain policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.domain.services.album_disc import infer_album_disc_totals
from omym2.domain.services.artist_name import artist_name_projections, artist_name_sources
from omym2.domain.services.path_policy import PathPolicy
from omym2.features.settings.dto import PathPolicyPreviewResult

if TYPE_CHECKING:
    from omym2.features.common_ports import ArtistNameResolutionReader
    from omym2.features.settings.dto import PathPolicyPreviewRequest


@dataclass(frozen=True, slots=True)
class PreviewPathPolicyUseCase:
    """Render a sample canonical path using the supplied path policy."""

    artist_name_resolver: ArtistNameResolutionReader

    def execute(self, request: PathPolicyPreviewRequest) -> PathPolicyPreviewResult:
        """Return the rendered preview path or validation errors."""
        album_disc_totals = infer_album_disc_totals(
            (request.metadata,),
            unknown_artist=request.path_policy.unknown_artist,
            unknown_album=request.path_policy.unknown_album,
        )
        resolutions = self.artist_name_resolver.resolve_many(artist_name_sources((request.metadata,)))
        artist_names = artist_name_projections(
            (request.metadata,),
            tuple(resolution.resolved_name for resolution in resolutions),
        )[0]
        try:
            preview_path = PathPolicy.from_path_policy_config(request.path_policy, request.artist_ids).canonical_path(
                request.metadata,
                request.file_extension,
                album_disc_total=album_disc_totals.for_metadata(request.metadata),
                artist_names=artist_names,
            )
        except ValueError as exc:
            return PathPolicyPreviewResult(path=None, errors=(str(exc),))
        return PathPolicyPreviewResult(path=preview_path, errors=())
