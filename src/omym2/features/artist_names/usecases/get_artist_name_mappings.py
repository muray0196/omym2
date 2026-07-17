"""
Summary: Reads the editable original-to-English artist-name mapping snapshot.
Why: Lets Settings expose automatic results and user corrections from one source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.features.artist_names.dto import ArtistNameMappingsResult
from omym2.features.artist_names.usecases.save_artist_name_mappings import artist_name_mappings_revision

if TYPE_CHECKING:
    from omym2.features.common_ports import UnitOfWork


@dataclass(frozen=True, slots=True)
class GetArtistNameMappingsUseCase:
    """Return every editable artist-name mapping with optimistic concurrency state."""

    uow: UnitOfWork

    def execute(self) -> ArtistNameMappingsResult:
        """Read one deterministic mapping snapshot."""
        with self.uow as uow:
            mappings = uow.accepted_artist_names.list_all()
        return ArtistNameMappingsResult(
            mappings=mappings,
            revision=artist_name_mappings_revision(mappings),
        )
