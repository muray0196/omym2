"""
Summary: Defines resolved artist display-name outcomes and diagnostics.
Why: Preserves deterministic naming provenance without changing raw metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.accepted_artist_name import AcceptedArtistName


class ArtistNameResolutionProvenance(StrEnum):
    """Source that supplied one effective artist display name."""

    USER_PREFERENCE = "user_preference"
    ACCEPTED_MUSICBRAINZ = "accepted_musicbrainz"
    NEW_MUSICBRAINZ = "new_musicbrainz"
    ORIGINAL = "original"


class ArtistNameResolutionIssue(StrEnum):
    """Reason automatic artist-name resolution preserved the original value."""

    MISSING_SOURCE = "missing_source"
    COMPOSITE_UNSUPPORTED = "composite_unsupported"
    NON_LATIN_REQUIRED = "non_latin_required"
    AUTOMATIC_LOOKUP_DISABLED = "automatic_lookup_disabled"
    DETECTOR_UNAVAILABLE = "detector_unavailable"
    NOT_JAPANESE = "not_japanese"
    LOW_LANGUAGE_CONFIDENCE = "low_language_confidence"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    NO_CONFIDENT_MATCH = "no_confident_match"
    AMBIGUOUS_MATCH = "ambiguous_match"


@dataclass(frozen=True, slots=True)
class ArtistNameResolution:
    """One source value projected through preference, cache, and provider precedence."""

    source_name: str | None
    source_key: str | None
    resolved_name: str | None
    provenance: ArtistNameResolutionProvenance
    issue: ArtistNameResolutionIssue | None = None
    accepted_name: AcceptedArtistName | None = None


@dataclass(frozen=True, slots=True)
class ArtistNameResolutionDiagnostic:
    """Durable review snapshot of one artist-name resolution outcome."""

    source_name: str | None
    resolved_name: str | None
    provenance: ArtistNameResolutionProvenance
    issue: ArtistNameResolutionIssue | None = None

    @classmethod
    def from_resolution(cls, resolution: ArtistNameResolution) -> ArtistNameResolutionDiagnostic:
        """Copy the reviewable fields without retaining provider-cache state."""
        return cls(
            source_name=resolution.source_name,
            resolved_name=resolution.resolved_name,
            provenance=resolution.provenance,
            issue=resolution.issue,
        )


@dataclass(frozen=True, slots=True)
class ArtistNameDiagnostics:
    """Artist and album-artist diagnostics recorded for one planned action."""

    artist: ArtistNameResolutionDiagnostic
    album_artist: ArtistNameResolutionDiagnostic
