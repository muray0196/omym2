"""
Summary: Tests accepted provider artist-name provenance.
Why: Keeps sticky cache records complete and timezone-stable before persistence.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from omym2.domain.models.accepted_artist_name import (
    EMPTY_ACCEPTED_ARTIST_NAME_FIELD_MESSAGE,
    INVALID_PROVIDER_ARTIST_ID_MESSAGE,
    INVALID_SELECTED_LOCALE_MESSAGE,
    AcceptedArtistName,
    ArtistNameProvider,
    SelectedArtistNameKind,
)

SOURCE_NAME = "宇多田ヒカル"
RESOLVED_NAME = "Hikaru Utada"
MUSICBRAINZ_ARTIST_ID = "db2f4f3a-f0c2-4c96-bea3-636f4b44f57b"
TOKYO_OFFSET_HOURS = 9


def test_accepted_artist_name_normalizes_acceptance_time_to_utc() -> None:
    """Accepted provider provenance stores one unambiguous UTC instant."""
    accepted_at = datetime(2026, 7, 15, 20, tzinfo=timezone(timedelta(hours=TOKYO_OFFSET_HOURS)))

    accepted_name = _accepted_name(accepted_at=accepted_at)

    assert accepted_name.accepted_at == datetime(2026, 7, 15, 11, tzinfo=UTC)


def test_accepted_artist_name_canonicalizes_musicbrainz_identity() -> None:
    """MusicBrainz identities use the canonical lowercase hyphenated UUID form."""
    accepted_name = replace(_accepted_name(), provider_artist_id=MUSICBRAINZ_ARTIST_ID.upper())

    assert accepted_name.provider_artist_id == MUSICBRAINZ_ARTIST_ID


def test_accepted_artist_name_rejects_invalid_musicbrainz_identity() -> None:
    """Malformed provider identities cannot become sticky cache records."""
    with pytest.raises(ValueError, match=INVALID_PROVIDER_ARTIST_ID_MESSAGE):
        _ = replace(_accepted_name(), provider_artist_id="not-a-mbid")


@pytest.mark.parametrize("field", ["source_key", "source_name", "resolved_name", "provider_artist_id"])
def test_accepted_artist_name_rejects_blank_required_text(field: str) -> None:
    """Every lookup and provenance text field must contain visible text."""
    with pytest.raises(ValueError, match=EMPTY_ACCEPTED_ARTIST_NAME_FIELD_MESSAGE):
        _ = replace(_accepted_name(), **{field: "   "})


@pytest.mark.parametrize(
    ("selected_name_kind", "selected_locale"),
    [(SelectedArtistNameKind.NAME, "en"), (SelectedArtistNameKind.ALIAS, " ")],
)
def test_accepted_artist_name_rejects_invalid_locale_provenance(
    selected_name_kind: SelectedArtistNameKind,
    selected_locale: str,
) -> None:
    """Only a selected alias may carry a nonblank locale."""
    with pytest.raises(ValueError, match=INVALID_SELECTED_LOCALE_MESSAGE):
        _ = replace(
            _accepted_name(),
            selected_name_kind=selected_name_kind,
            selected_locale=selected_locale,
        )


def _accepted_name(*, accepted_at: datetime | None = None) -> AcceptedArtistName:
    return AcceptedArtistName(
        source_key=SOURCE_NAME,
        source_name=SOURCE_NAME,
        resolved_name=RESOLVED_NAME,
        provider=ArtistNameProvider.MUSICBRAINZ,
        provider_artist_id=MUSICBRAINZ_ARTIST_ID,
        selected_name_kind=SelectedArtistNameKind.ALIAS,
        selected_locale="en",
        accepted_at=accepted_at or datetime(2026, 7, 15, 11, tzinfo=UTC),
    )
