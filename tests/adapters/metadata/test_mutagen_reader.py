"""
Summary: Tests Mutagen metadata mapping.
Why: Verifies external tag data is converted to TrackMetadata.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from omym2.adapters.metadata.mutagen_reader import (
    MUTAGEN_UNSUPPORTED_FILE_MESSAGE,
    MetadataReadError,
    MutagenMetadataReader,
)

if TYPE_CHECKING:
    from omym2.features.common_ports import FileSystemPath

ALBUM = "Example Album"
ALBUM_ARTIST = "Example Album Artist"
ARTIST = "Example Artist"
DISC_NUMBER = 1
DISC_TOTAL = 2
FILE_PATH = "track.flac"
GENRE = "J-Pop"
TITLE = "Example Song"
TRACK_NUMBER = 3
TRACK_TOTAL = 12
YEAR = 2024


def test_mutagen_metadata_reader_maps_easy_tags() -> None:
    """Mutagen easy tags become the domain TrackMetadata shape."""

    def opener(filething: FileSystemPath, *, easy: bool = False) -> object | None:
        assert filething == FILE_PATH
        assert easy
        return {
            "album": [ALBUM],
            "albumartist": [ALBUM_ARTIST],
            "artist": [ARTIST],
            "date": [f"{YEAR}-05-01"],
            "discnumber": [f"{DISC_NUMBER}/{DISC_TOTAL}"],
            "genre": [GENRE],
            "title": [TITLE],
            "tracknumber": [f"0{TRACK_NUMBER}/{TRACK_TOTAL}"],
        }

    metadata = MutagenMetadataReader(opener=opener).read(FILE_PATH)

    assert metadata.title == TITLE
    assert metadata.artist == ARTIST
    assert metadata.album == ALBUM
    assert metadata.album_artist == ALBUM_ARTIST
    assert metadata.genre == GENRE
    assert metadata.year == YEAR
    assert metadata.track_number == TRACK_NUMBER
    assert metadata.track_total == TRACK_TOTAL
    assert metadata.disc_number == DISC_NUMBER
    assert metadata.disc_total == DISC_TOTAL


def test_mutagen_metadata_reader_rejects_unknown_file_type() -> None:
    """A Mutagen None result is surfaced as a metadata read error."""

    def opener(filething: FileSystemPath, *, easy: bool = False) -> object | None:
        del filething, easy
        return None

    with pytest.raises(MetadataReadError, match=MUTAGEN_UNSUPPORTED_FILE_MESSAGE):
        _ = MutagenMetadataReader(opener=opener).read(FILE_PATH)
