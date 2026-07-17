"""
Summary: Tests editable original-to-English artist-name mapping snapshots.
Why: Proves MusicBrainz results and user corrections share one revisioned store.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from omym2.domain.models.accepted_artist_name import (
    AcceptedArtistName,
    ArtistNameProvider,
    SelectedArtistNameKind,
)
from omym2.features.artist_names.dto import SaveArtistNameMappingsRequest
from omym2.features.artist_names.usecases.get_artist_name_mappings import GetArtistNameMappingsUseCase
from omym2.features.artist_names.usecases.save_artist_name_mappings import (
    DUPLICATE_ARTIST_NAME_MAPPING_MESSAGE,
    INVALID_ENGLISH_ARTIST_NAME_MESSAGE,
    ArtistNameMappingsRevisionMismatchError,
    SaveArtistNameMappingsUseCase,
)
from tests.fakes.in_memory_repositories import InMemoryUnitOfWork
from tests.fakes.runtime import FixedClock

SOURCE_NAME = "宇多田ヒカル"
SECOND_SOURCE_NAME = "椎名林檎"
BASE_TIME = datetime(2026, 7, 17, 12, tzinfo=UTC)
MUSICBRAINZ_ARTIST_ID = "db2f4f3a-f0c2-4c96-bea3-636f4b44f57b"


def test_save_artist_name_mappings_edits_adds_and_deletes_in_one_snapshot() -> None:
    """The user can correct an automatic row, add one, and remove another atomically."""
    uow = InMemoryUnitOfWork()
    original = _musicbrainz_mapping(SOURCE_NAME, "Wrong Name")
    removed = _musicbrainz_mapping("削除", "Removed Name")
    uow.accepted_artist_names.records = {
        original.source_key: original,
        removed.source_key: removed,
    }
    current = GetArtistNameMappingsUseCase(uow).execute()

    result = SaveArtistNameMappingsUseCase(uow, FixedClock(BASE_TIME)).execute(
        SaveArtistNameMappingsRequest(
            entries={SOURCE_NAME: "Hikaru Utada", SECOND_SOURCE_NAME: "Ringo Sheena"},
            expected_revision=current.revision,
        )
    )

    assert tuple(mapping.source_name for mapping in result.mappings) == (SOURCE_NAME, SECOND_SOURCE_NAME)
    assert all(mapping.provider is ArtistNameProvider.USER for mapping in result.mappings)
    assert uow.accepted_artist_names.find_by_source_key("削除") is None
    assert uow.commit_count == 1


def test_save_artist_name_mappings_preserves_unchanged_musicbrainz_provenance() -> None:
    """Saving an unchanged row does not erase its automatic provenance."""
    uow = InMemoryUnitOfWork()
    mapping = _musicbrainz_mapping(SOURCE_NAME, "Hikaru Utada")
    uow.accepted_artist_names.records[mapping.source_key] = mapping
    current = GetArtistNameMappingsUseCase(uow).execute()

    result = SaveArtistNameMappingsUseCase(uow, FixedClock(BASE_TIME)).execute(
        SaveArtistNameMappingsRequest(
            entries={SOURCE_NAME: "Hikaru Utada"},
            expected_revision=current.revision,
        )
    )

    assert result.mappings == (mapping,)


def test_save_artist_name_mappings_preserves_raw_source_name_behind_normalized_key() -> None:
    """A manual edit retains the exact source metadata string used to create its mapping."""
    raw_source_name = "\t宇多田  ヒカル\n"
    uow = InMemoryUnitOfWork()
    revision = GetArtistNameMappingsUseCase(uow).execute().revision

    result = SaveArtistNameMappingsUseCase(uow, FixedClock(BASE_TIME)).execute(
        SaveArtistNameMappingsRequest(
            entries={raw_source_name: "Hikaru Utada"},
            expected_revision=revision,
        )
    )

    assert result.mappings[0].source_key == "宇多田 ヒカル"
    assert result.mappings[0].source_name == raw_source_name


def test_save_artist_name_mappings_rejects_stale_revision() -> None:
    """A stale browser snapshot cannot delete a mapping added concurrently."""
    uow = InMemoryUnitOfWork()
    stale = GetArtistNameMappingsUseCase(uow).execute()
    mapping = _musicbrainz_mapping(SOURCE_NAME, "Hikaru Utada")
    uow.accepted_artist_names.records[mapping.source_key] = mapping

    with pytest.raises(ArtistNameMappingsRevisionMismatchError):
        _ = SaveArtistNameMappingsUseCase(uow, FixedClock(BASE_TIME)).execute(
            SaveArtistNameMappingsRequest(entries={}, expected_revision=stale.revision)
        )


@pytest.mark.parametrize(
    ("entries", "message"),
    [
        ({SOURCE_NAME: "宇多田ヒカル"}, INVALID_ENGLISH_ARTIST_NAME_MESSAGE),
        ({"宇多田 ヒカル": "Hikaru Utada", "宇多田  ヒカル": "Utada Hikaru"}, DUPLICATE_ARTIST_NAME_MAPPING_MESSAGE),
    ],
)
def test_save_artist_name_mappings_validates_english_names_and_normalized_keys(
    entries: dict[str, str],
    message: str,
) -> None:
    """Manual rows follow the same English-name and source-key contract as automatic rows."""
    uow = InMemoryUnitOfWork()
    revision = GetArtistNameMappingsUseCase(uow).execute().revision

    with pytest.raises(ValueError, match=message):
        _ = SaveArtistNameMappingsUseCase(uow, FixedClock(BASE_TIME)).execute(
            SaveArtistNameMappingsRequest(entries=entries, expected_revision=revision)
        )


def _musicbrainz_mapping(source_name: str, english_name: str) -> AcceptedArtistName:
    return AcceptedArtistName(
        source_key=source_name,
        source_name=source_name,
        resolved_name=english_name,
        provider=ArtistNameProvider.MUSICBRAINZ,
        provider_artist_id=MUSICBRAINZ_ARTIST_ID,
        selected_name_kind=SelectedArtistNameKind.ALIAS,
        selected_locale="en",
        accepted_at=BASE_TIME,
    )
