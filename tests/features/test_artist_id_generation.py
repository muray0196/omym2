"""
Summary: Tests artist ID generation usecase behavior.
Why: Verifies ports, persistence, and manual-entry preservation.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from omym2.domain.models.app_config import AppConfig, ArtistIdConfig
from omym2.features.artist_ids.dto import GenerateArtistIdsRequest
from omym2.features.artist_ids.usecases.generate_artist_ids import GenerateArtistIdsUseCase
from omym2.features.common_ports import ConfigStoreValidationError

JAPANESE_ARTIST = "米津玄師"
RESOLVED_ARTIST = "Kenshi Yonezu"
ENGLISH_ARTIST = "John Smith"
SAVED_ARTIST_ID = "MANUAL"
NO_USABLE_CHARS_ARTIST = "!!!"
# Sanitizer-stable on its own (passes ArtistIdConfig.__post_init__), but its
# max_length-3 truncation "AB-CD"[:3] == "AB-" ends with a hyphen, which is
# not a valid saved entry value. This keeps the truncation edge reachable
# through the usecase's own ArtistIdConfig(...) construction after fallback_id
# gained the same entries-value pattern check at construction time.
TRUNCATION_UNSAFE_FALLBACK_ID = "AB-CD"
TRUNCATION_MAX_LENGTH = 3


@dataclass(slots=True)
class _MemoryConfigStore:
    config: AppConfig
    saves: int = 0

    def load(self) -> AppConfig:
        return self.config

    def save(self, config: AppConfig) -> None:
        self.config = config
        self.saves += 1


@dataclass(frozen=True, slots=True)
class _FakeLanguageDetector:
    japanese_artists: frozenset[str]

    def is_japanese(self, text: str) -> bool:
        return text in self.japanese_artists


@dataclass(frozen=True, slots=True)
class _FakeArtistResolver:
    names: dict[str, str | None]

    def english_or_latin_name(self, source_artist: str) -> str | None:
        return self.names.get(source_artist)


def test_generate_artist_ids_resolves_japanese_artist_before_generation() -> None:
    """Japanese source names use the resolved MusicBrainz name when available."""
    store = _MemoryConfigStore(AppConfig())

    result = _usecase(store, {JAPANESE_ARTIST}, {JAPANESE_ARTIST: RESOLVED_ARTIST}).execute(
        GenerateArtistIdsRequest((JAPANESE_ARTIST,))
    )

    assert result.entries[0].generation_artist == RESOLVED_ARTIST
    assert result.entries[0].artist_id == "KENSHYNZ"
    assert store.config.artist_ids.entries == {JAPANESE_ARTIST: "KENSHYNZ"}


def test_generate_artist_ids_generates_non_japanese_artist_directly() -> None:
    """Non-Japanese names generate from the source text without resolver calls."""
    store = _MemoryConfigStore(AppConfig())

    result = _usecase(store, frozenset(), {}).execute(GenerateArtistIdsRequest((ENGLISH_ARTIST,)))

    assert result.entries[0].generation_artist == ENGLISH_ARTIST
    assert result.entries[0].artist_id == "JOHNSMTH"
    assert store.config.artist_ids.entries == {ENGLISH_ARTIST: "JOHNSMTH"}


def test_generate_artist_ids_falls_back_when_lookup_fails() -> None:
    """Japanese lookup failure falls back to deterministic source-name generation."""
    store = _MemoryConfigStore(AppConfig())

    result = _usecase(store, {JAPANESE_ARTIST}, {JAPANESE_ARTIST: None}).execute(
        GenerateArtistIdsRequest((JAPANESE_ARTIST,))
    )

    assert result.entries[0].generation_artist == JAPANESE_ARTIST
    assert result.entries[0].artist_id == "NOART"


def test_generate_artist_ids_preserves_existing_saved_entry() -> None:
    """Normal generation does not overwrite user-edited entries."""
    store = _MemoryConfigStore(AppConfig(artist_ids=ArtistIdConfig(entries={ENGLISH_ARTIST: SAVED_ARTIST_ID})))

    result = _usecase(store, frozenset(), {}).execute(GenerateArtistIdsRequest((ENGLISH_ARTIST,)))

    assert result.entries[0].artist_id == SAVED_ARTIST_ID
    assert result.entries[0].saved is False
    assert store.saves == 0
    assert store.config.artist_ids.entries == {ENGLISH_ARTIST: SAVED_ARTIST_ID}


def test_generate_artist_ids_overwrites_when_requested() -> None:
    """Explicit regeneration can replace an existing editable entry."""
    store = _MemoryConfigStore(AppConfig(artist_ids=ArtistIdConfig(entries={ENGLISH_ARTIST: SAVED_ARTIST_ID})))

    result = _usecase(store, frozenset(), {}).execute(GenerateArtistIdsRequest((ENGLISH_ARTIST,), overwrite=True))

    assert result.entries[0].artist_id == "JOHNSMTH"
    assert result.entries[0].overwritten is True
    assert store.config.artist_ids.entries == {ENGLISH_ARTIST: "JOHNSMTH"}


def test_generate_artist_ids_reports_unsafe_fallback_id_truncation_as_config_error() -> None:
    """A fallback_id that is only unsafe once truncated still surfaces as a config error, not a traceback."""
    store = _MemoryConfigStore(
        AppConfig(
            artist_ids=ArtistIdConfig(
                max_length=TRUNCATION_MAX_LENGTH,
                fallback_id=TRUNCATION_UNSAFE_FALLBACK_ID,
            )
        )
    )

    with pytest.raises(ConfigStoreValidationError):
        _ = _usecase(store, frozenset(), {}).execute(GenerateArtistIdsRequest((NO_USABLE_CHARS_ARTIST,)))

    assert store.saves == 0


def _usecase(
    store: _MemoryConfigStore,
    japanese_artists: set[str] | frozenset[str],
    resolved_names: dict[str, str | None],
) -> GenerateArtistIdsUseCase:
    return GenerateArtistIdsUseCase(
        config_store=store,
        language_detector=_FakeLanguageDetector(frozenset(japanese_artists)),
        artist_resolver=_FakeArtistResolver(resolved_names),
    )
