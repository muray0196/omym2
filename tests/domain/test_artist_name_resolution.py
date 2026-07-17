"""
Summary: Tests typed artist display-name resolution outcomes.
Why: Keeps naming provenance and fallback diagnostics explicit and stable.
"""

from __future__ import annotations

from datetime import UTC, datetime

from omym2.domain.models.accepted_artist_name import (
    AcceptedArtistName,
    ArtistNameProvider,
    SelectedArtistNameKind,
)
from omym2.domain.models.artist_name_resolution import (
    ArtistNameResolution,
    ArtistNameResolutionDiagnostic,
    ArtistNameResolutionIssue,
    ArtistNameResolutionProvenance,
)

SOURCE_NAME = "宇多田ヒカル"
RESOLVED_NAME = "Hikaru Utada"
MUSICBRAINZ_ARTIST_ID = "db2f4f3a-f0c2-4c96-bea3-636f4b44f57b"


def test_artist_name_resolution_values_are_stable_strings() -> None:
    """Persistence and review callers receive the documented closed values."""
    assert tuple(item.value for item in ArtistNameResolutionProvenance) == (
        "user_preference",
        "accepted_musicbrainz",
        "new_musicbrainz",
        "original",
    )
    assert tuple(item.value for item in ArtistNameResolutionIssue) == (
        "missing_source",
        "composite_unsupported",
        "automatic_lookup_disabled",
        "romanization_not_required",
        "provider_unavailable",
        "no_confident_match",
        "ambiguous_match",
    )


def test_artist_name_resolution_carries_the_accepted_match() -> None:
    """A provider-backed result retains the complete sticky cache record."""
    accepted_name = _accepted_name()

    resolution = ArtistNameResolution(
        source_name=SOURCE_NAME,
        source_key=SOURCE_NAME,
        resolved_name=RESOLVED_NAME,
        provenance=ArtistNameResolutionProvenance.NEW_MUSICBRAINZ,
        accepted_name=accepted_name,
    )

    assert resolution.accepted_name == accepted_name
    assert resolution.issue is None


def test_artist_name_resolution_diagnostic_copies_only_durable_review_fields() -> None:
    """Plan review diagnostics do not retain the accepted cache record or source key."""
    resolution = ArtistNameResolution(
        source_name=SOURCE_NAME,
        source_key=SOURCE_NAME,
        resolved_name=RESOLVED_NAME,
        provenance=ArtistNameResolutionProvenance.NEW_MUSICBRAINZ,
        accepted_name=_accepted_name(),
    )

    diagnostic = ArtistNameResolutionDiagnostic.from_resolution(resolution)

    assert diagnostic == ArtistNameResolutionDiagnostic(
        source_name=SOURCE_NAME,
        resolved_name=RESOLVED_NAME,
        provenance=ArtistNameResolutionProvenance.NEW_MUSICBRAINZ,
    )


def _accepted_name() -> AcceptedArtistName:
    return AcceptedArtistName(
        source_key=SOURCE_NAME,
        source_name=SOURCE_NAME,
        resolved_name=RESOLVED_NAME,
        provider=ArtistNameProvider.MUSICBRAINZ,
        provider_artist_id=MUSICBRAINZ_ARTIST_ID,
        selected_name_kind=SelectedArtistNameKind.ALIAS,
        selected_locale="en",
        accepted_at=datetime(2026, 7, 15, 12, tzinfo=UTC),
    )
