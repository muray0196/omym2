"""
Summary: Tests deterministic artist ID generation.
Why: Protects editable path artist IDs from heuristic drift.
"""

from __future__ import annotations

from omym2.domain.models.app_config import ArtistIdConfig
from omym2.domain.services.artist_id import generate_artist_id

COMMA_SEPARATED_ARTISTS = "First, Second"
FALLBACK_ID = "NOART"
JAPANESE_ARTIST = "宇多田ヒカル"
MULTI_WORD_ARTIST = "Kenshi Yonezu"
SHORT_MAX_LENGTH = 4
VOWEL_HEAVY_ARTIST = "Aeiou Beat"


def test_artist_id_uses_fallback_for_blank_input() -> None:
    """Blank artist text produces the documented fallback ID."""
    assert generate_artist_id("", ArtistIdConfig()) == FALLBACK_ID


def test_artist_id_uses_fallback_for_non_latin_text_without_transliteration() -> None:
    """Japanese text is not transliterated by the pure generator."""
    assert generate_artist_id(JAPANESE_ARTIST, ArtistIdConfig()) == FALLBACK_ID


def test_artist_id_removes_vowels_after_first_character_per_word() -> None:
    """Each normalized word keeps its leading character and drops later vowels."""
    assert generate_artist_id(VOWEL_HEAVY_ARTIST, ArtistIdConfig()) == "ABT"


def test_artist_id_balances_multi_word_characters_round_robin() -> None:
    """Multi-word artist IDs draw characters evenly across normalized words."""
    assert generate_artist_id(MULTI_WORD_ARTIST, ArtistIdConfig()) == "KYNNSZH"


def test_artist_id_splits_comma_separated_artists() -> None:
    """Multiple source artists are balanced after comma splitting."""
    assert generate_artist_id(COMMA_SEPARATED_ARTISTS, ArtistIdConfig()) == "FSRCSNTD"


def test_artist_id_respects_configured_max_length() -> None:
    """Generation stops at the configured maximum length."""
    assert generate_artist_id(MULTI_WORD_ARTIST, ArtistIdConfig(max_length=SHORT_MAX_LENGTH)) == "KYNN"
