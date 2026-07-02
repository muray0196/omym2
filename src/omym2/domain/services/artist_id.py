"""
Summary: Generates deterministic user-facing artist IDs.
Why: Supports editable path/config artist IDs without I/O or transliteration.
"""

from __future__ import annotations

import re
import unicodedata
from collections import deque
from typing import TYPE_CHECKING

from omym2.config import (
    ARTIST_ID_ASCII_ALNUM_PATTERN,
    ARTIST_ID_NON_TOKEN_PATTERN,
    ARTIST_ID_SEPARATOR_PATTERN,
    ARTIST_ID_VOWELS,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from omym2.domain.models.app_config import ArtistIdConfig

_ASCII_ALNUM_PATTERN = re.compile(ARTIST_ID_ASCII_ALNUM_PATTERN)
_NON_TOKEN_PATTERN = re.compile(ARTIST_ID_NON_TOKEN_PATTERN)
_SEPARATOR_PATTERN = re.compile(ARTIST_ID_SEPARATOR_PATTERN)


def generate_artist_id(source_artist: str | None, config: ArtistIdConfig) -> str:
    """Generate a deterministic artist ID from resolved artist text."""
    words = tuple(_reduced_words(source_artist))
    if len(words) == 0:
        return config.fallback

    generated = _round_robin_characters(words, config.max_length)
    if generated == "":
        return config.fallback
    return generated[: config.max_length]


def _reduced_words(source_artist: str | None) -> Iterable[str]:
    if source_artist is None:
        return ()

    artist_words: list[str] = []
    for artist_name in source_artist.split(","):
        normalized_artist = _normalize_artist_text(artist_name)
        if normalized_artist == "":
            continue
        artist_words.extend(_without_inner_vowels(word) for word in normalized_artist.split("-") if word != "")
    return tuple(word for word in artist_words if word != "")


def _normalize_artist_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    ascii_words = _ASCII_ALNUM_PATTERN.findall(normalized)
    # Non-ASCII text intentionally does not transliterate. If MusicBrainz did
    # not supply a Latin name, users can edit the saved fallback value.
    if len(ascii_words) == 0:
        return ""
    tokenized = _NON_TOKEN_PATTERN.sub("-", normalized)
    collapsed = _SEPARATOR_PATTERN.sub("-", tokenized)
    return collapsed.strip("-")


def _without_inner_vowels(word: str) -> str:
    if len(word) <= 1:
        return word.upper()
    first, rest = word[0], word[1:]
    return f"{first}{''.join(character for character in rest if character not in ARTIST_ID_VOWELS)}".upper()


def _round_robin_characters(words: Iterable[str], max_length: int) -> str:
    queues = deque(deque(word) for word in words if word != "")
    characters: list[str] = []
    while queues and len(characters) < max_length:
        queue = queues.popleft()
        characters.append(queue.popleft())
        if queue:
            queues.append(queue)
    return "".join(characters)
