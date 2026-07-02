"""
Summary: Tests artist ID generation usecase behavior.
Why: Verifies language and MusicBrainz ports stay outside path rendering.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from omym2.domain.models.app_config import AppConfig, ArtistIdConfig, ArtistIdEntry
from omym2.features.artist_ids.dto import ArtistIdGenerationRequest
from omym2.features.artist_ids.ports import ArtistIdPorts
from omym2.features.artist_ids.usecases.generate_artist_ids import GenerateArtistIdsUseCase

ENGLISH_ARTIST = "Aimer"
EXISTING_ARTIST_ID = "CUSTOM"
JAPANESE_ARTIST = "宇多田ヒカル"
LOOKUP_ARTIST = "Hikaru Utada"
LOOKUP_ARTIST_ID = "HUKTRD"


def test_generate_artist_ids_generates_non_japanese_artist_directly() -> None:
    """Non-Japanese artist names do not call MusicBrainz before generation."""
    store = FakeConfigStore()
    resolver = FakeMusicBrainzLookup()

    result = GenerateArtistIdsUseCase(
        ArtistIdPorts(config_store=store, language_detector=FakeLanguageDetector(), musicbrainz_lookup=resolver)
    ).execute(ArtistIdGenerationRequest(artist_names=(ENGLISH_ARTIST,)))

    assert result.entries[0].artist_id == "AMR"
    assert result.entries[0].generated_from == ENGLISH_ARTIST
    assert resolver.lookups == []
    assert _saved_entries(store)[ENGLISH_ARTIST] == "AMR"


def test_generate_artist_ids_resolves_japanese_artist_before_generation() -> None:
    """Japanese artist names use the MusicBrainz port for a Latin source name."""
    store = FakeConfigStore()

    result = GenerateArtistIdsUseCase(
        ArtistIdPorts(
            config_store=store,
            language_detector=FakeLanguageDetector(languages={JAPANESE_ARTIST: "ja"}),
            musicbrainz_lookup=FakeMusicBrainzLookup(results={JAPANESE_ARTIST: LOOKUP_ARTIST}),
        )
    ).execute(ArtistIdGenerationRequest(artist_names=(JAPANESE_ARTIST,)))

    assert result.entries[0].generated_from == LOOKUP_ARTIST
    assert result.entries[0].artist_id == LOOKUP_ARTIST_ID
    assert _saved_entries(store)[JAPANESE_ARTIST] == LOOKUP_ARTIST_ID


def test_generate_artist_ids_falls_back_when_japanese_lookup_fails() -> None:
    """Lookup failure leaves a deterministic editable fallback entry."""
    store = FakeConfigStore()

    result = GenerateArtistIdsUseCase(
        ArtistIdPorts(
            config_store=store,
            language_detector=FakeLanguageDetector(languages={JAPANESE_ARTIST: "ja"}),
            musicbrainz_lookup=FakeMusicBrainzLookup(),
        )
    ).execute(ArtistIdGenerationRequest(artist_names=(JAPANESE_ARTIST,)))

    assert result.entries[0].artist_id == "NOART"
    assert _saved_entries(store)[JAPANESE_ARTIST] == "NOART"


def test_generate_artist_ids_preserves_existing_entry_without_overwrite() -> None:
    """Normal generation does not overwrite manually edited saved entries."""
    store = FakeConfigStore(
        config=AppConfig(
            artist_ids=ArtistIdConfig(
                entries=(ArtistIdEntry(source_artist=ENGLISH_ARTIST, artist_id=EXISTING_ARTIST_ID),)
            )
        )
    )

    result = GenerateArtistIdsUseCase(
        ArtistIdPorts(
            config_store=store, language_detector=FakeLanguageDetector(), musicbrainz_lookup=FakeMusicBrainzLookup()
        )
    ).execute(ArtistIdGenerationRequest(artist_names=(ENGLISH_ARTIST,)))

    assert result.entries[0].preserved_existing
    assert result.entries[0].artist_id == EXISTING_ARTIST_ID
    assert store.saved_config is None


@dataclass(slots=True)
class FakeConfigStore:
    """Config store fake for artist ID tests."""

    config: AppConfig = field(default_factory=AppConfig)
    saved_config: AppConfig | None = None

    def load(self) -> AppConfig:
        """Return the configured test AppConfig."""
        return self.config

    def save(self, config: AppConfig) -> None:
        """Record the saved AppConfig."""
        self.saved_config = config


@dataclass(frozen=True, slots=True)
class FakeLanguageDetector:
    """Language detector fake keyed by artist name."""

    languages: dict[str, str] = field(default_factory=dict)

    def detect_language(self, text: str) -> str | None:
        """Return a configured language or English by default."""
        return self.languages.get(text, "en")


@dataclass(slots=True)
class FakeMusicBrainzLookup:
    """MusicBrainz lookup fake keyed by source artist."""

    results: dict[str, str] = field(default_factory=dict)
    lookups: list[str] = field(default_factory=list)

    def find_latin_artist_name(self, artist_name: str) -> str | None:
        """Return a configured Latin name and record the lookup."""
        self.lookups.append(artist_name)
        return self.results.get(artist_name)


def _saved_entries(store: FakeConfigStore) -> dict[str, str]:
    assert store.saved_config is not None
    return {entry.source_artist: entry.artist_id for entry in store.saved_config.artist_ids.entries}
