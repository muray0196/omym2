"""
Summary: Reads music tags through Mutagen.
Why: Converts external tag formats into OMYM2 TrackMetadata.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast

import mutagen

from omym2.domain.models.track_metadata import TrackMetadata

if TYPE_CHECKING:
    from omym2.features.common_ports import FileSystemPath

ALBUM_ARTIST_KEYS = ("albumartist", "album_artist", "album artist")
ALBUM_KEYS = ("album",)
ARTIST_KEYS = ("artist",)
DATE_KEYS = ("date", "originaldate", "year")
DISC_NUMBER_KEYS = ("discnumber", "disc")
DISC_TOTAL_KEYS = ("disctotal",)
GENRE_KEYS = ("genre",)
TITLE_KEYS = ("title",)
TRACK_NUMBER_KEYS = ("tracknumber", "track")
TRACK_TOTAL_KEYS = ("tracktotal",)
MUTAGEN_READ_ERROR_PREFIX = "Mutagen could not read metadata"
MUTAGEN_UNSUPPORTED_FILE_MESSAGE = "Mutagen could not determine an audio metadata type."
MUTAGEN_ERROR_ATTRIBUTE = "MutagenError"
MUTAGEN_FILE_ATTRIBUTE = "File"
UNSUPPORTED_TAG_CONTAINER_MESSAGE = "Mutagen returned an unsupported tag container."
YEAR_PATTERN = re.compile(r"(?P<year>\d{4})")


class MetadataReadError(ValueError):
    """Raised when a metadata adapter cannot read a supported tag mapping."""


class MutagenFileOpener(Protocol):
    """Callable shape used by MutagenMetadataReader."""

    def __call__(self, filething: FileSystemPath, *, easy: bool = False) -> object | None:
        """Open one file with optional Mutagen easy tags."""
        ...


DEFAULT_MUTAGEN_FILE_OPENER = cast("MutagenFileOpener", vars(mutagen)[MUTAGEN_FILE_ATTRIBUTE])
MUTAGEN_ERROR_TYPE = cast("type[Exception]", vars(mutagen)[MUTAGEN_ERROR_ATTRIBUTE])


@dataclass(frozen=True, slots=True)
class MutagenMetadataReader:
    """Read music metadata using Mutagen's easy tag names."""

    opener: MutagenFileOpener = DEFAULT_MUTAGEN_FILE_OPENER

    def read(self, path: FileSystemPath) -> TrackMetadata:
        """Return normalized OMYM2 metadata for one music file."""
        try:
            audio = self.opener(path, easy=True)
        except MUTAGEN_ERROR_TYPE as exc:
            raise MetadataReadError(MUTAGEN_READ_ERROR_PREFIX) from exc

        if audio is None:
            raise MetadataReadError(MUTAGEN_UNSUPPORTED_FILE_MESSAGE)

        tags = _tags_from_audio(audio)
        track_number, track_total = _number_pair_from_tags(tags, TRACK_NUMBER_KEYS, TRACK_TOTAL_KEYS)
        disc_number, disc_total = _number_pair_from_tags(tags, DISC_NUMBER_KEYS, DISC_TOTAL_KEYS)
        return TrackMetadata(
            title=_first_text(tags, TITLE_KEYS),
            artist=_first_text(tags, ARTIST_KEYS),
            album=_first_text(tags, ALBUM_KEYS),
            album_artist=_first_text(tags, ALBUM_ARTIST_KEYS),
            genre=_first_text(tags, GENRE_KEYS),
            year=_year_from_text(_first_text(tags, DATE_KEYS)),
            track_number=track_number,
            track_total=track_total,
            disc_number=disc_number,
            disc_total=disc_total,
        )


def _tags_from_audio(audio: object) -> Mapping[str, object]:
    if isinstance(audio, Mapping):
        return cast("Mapping[str, object]", audio)

    tags = getattr(audio, "tags", None)
    if tags is None:
        return {}
    if isinstance(tags, Mapping):
        return cast("Mapping[str, object]", tags)
    raise MetadataReadError(UNSUPPORTED_TAG_CONTAINER_MESSAGE)


def _number_pair_from_tags(
    tags: Mapping[str, object],
    pair_keys: tuple[str, ...],
    total_keys: tuple[str, ...],
) -> tuple[int | None, int | None]:
    pair_value, paired_total = _number_pair_from_text(_first_text(tags, pair_keys))
    explicit_total = _number_from_text(_first_text(tags, total_keys))
    return pair_value, explicit_total if explicit_total is not None else paired_total


def _first_text(tags: Mapping[str, object], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = _tag_value(tags, key)
        text = _coerce_first_text(value)
        if text is not None:
            return text
    return None


def _tag_value(tags: Mapping[str, object], key: str) -> object | None:
    if key in tags:
        return tags[key]

    expected_key = key.casefold()
    for candidate_key, value in tags.items():
        if candidate_key.casefold() == expected_key:
            return value
    return None


def _coerce_first_text(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return _non_empty_text(value)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        for item in value:
            text = _non_empty_text(str(item))
            if text is not None:
                return text
        return None
    return _non_empty_text(str(value))


def _non_empty_text(value: str) -> str | None:
    stripped_value = value.strip()
    if stripped_value == "":
        return None
    return stripped_value


def _number_pair_from_text(value: str | None) -> tuple[int | None, int | None]:
    if value is None:
        return None, None
    number_text, separator, total_text = value.partition("/")
    number = _number_from_text(number_text)
    total = _number_from_text(total_text) if separator != "" else None
    return number, total


def _number_from_text(value: str | None) -> int | None:
    if value is None:
        return None
    stripped_value = value.strip()
    if stripped_value == "":
        return None
    try:
        return int(stripped_value)
    except ValueError:
        return None


def _year_from_text(value: str | None) -> int | None:
    if value is None:
        return None
    match = YEAR_PATTERN.search(value)
    if match is None:
        return None
    return int(match.group("year"))
