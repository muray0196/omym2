"""
Summary: Tests editable artist-name mapping provenance.
Why: Keeps MusicBrainz and user mappings complete and timezone-stable before persistence.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from omym2.domain.models.accepted_artist_name import (
    EMPTY_ACCEPTED_ARTIST_NAME_FIELD_MESSAGE,
    INVALID_PROVIDER_ARTIST_ID_MESSAGE,
    INVALID_PROVIDER_PROVENANCE_MESSAGE,
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


@pytest.mark.parametrize("field", ["source_key", "source_name", "resolved_name"])
def test_accepted_artist_name_rejects_blank_required_text(field: str) -> None:
    """Every lookup and provenance text field must contain visible text."""
    with pytest.raises(ValueError, match=EMPTY_ACCEPTED_ARTIST_NAME_FIELD_MESSAGE):
        _ = replace(_accepted_name(), **{field: "   "})


def test_user_artist_name_mapping_has_no_provider_provenance() -> None:
    """A manual correction is represented in the same mapping without fake MusicBrainz data."""
    mapping = AcceptedArtistName(
        source_key=SOURCE_NAME,
        source_name=SOURCE_NAME,
        resolved_name=RESOLVED_NAME,
        provider=ArtistNameProvider.USER,
        provider_artist_id=None,
        selected_name_kind=None,
        selected_locale=None,
        accepted_at=datetime(2026, 7, 15, 11, tzinfo=UTC),
    )

    assert mapping.provider is ArtistNameProvider.USER


def test_user_artist_name_mapping_rejects_provider_provenance() -> None:
    """Manual mappings cannot pretend to carry MusicBrainz evidence."""
    with pytest.raises(ValueError, match=INVALID_PROVIDER_PROVENANCE_MESSAGE):
        _ = replace(_accepted_name(), provider=ArtistNameProvider.USER)


@pytest.mark.parametrize(
    ("selected_name_kind", "selected_locale"),
    [(SelectedArtistNameKind.SORT_NAME, "en"), (SelectedArtistNameKind.ALIAS, " ")],
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


def test_alias_sort_name_accepts_alias_locale_provenance() -> None:
    """Alias sort-name provenance retains the locale that selected the alias."""
    accepted_name = replace(
        _accepted_name(),
        selected_name_kind=SelectedArtistNameKind.ALIAS_SORT_NAME,
        selected_locale="ja-Latn",
    )

    assert accepted_name.selected_locale == "ja-Latn"


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
