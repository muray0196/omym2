"""
Summary: Tests artist ID generation usecase behavior.
Why: Verifies ports, persistence, and manual-entry preservation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from omym2.domain.models.app_config import AppConfig, ArtistIdConfig, ArtistNameConfig
from omym2.domain.models.artist_name_resolution import ArtistNameResolution, ArtistNameResolutionProvenance
from omym2.domain.services.artist_name import derive_artist_name_source_key
from omym2.features.artist_ids.dto import GenerateArtistIdsRequest
from omym2.features.artist_ids.usecases.generate_artist_ids import GenerateArtistIdsUseCase
from omym2.features.common_ports import (
    ConfigRevisionMismatchError,
    ConfigSnapshot,
    ConfigSnapshotState,
    ConfigStoreValidationError,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

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
CONFIG_REVISION = "v1:artist-ids"
SAVED_CONFIG_REVISION = "v1:artist-ids-saved"


@dataclass(slots=True)
class _MemoryConfigStore:
    config: AppConfig
    saves: int = 0
    config_revision: str = CONFIG_REVISION

    def read_snapshot(self) -> ConfigSnapshot:
        return ConfigSnapshot(
            state=ConfigSnapshotState.VALID,
            config=self.config,
            config_revision=self.config_revision,
        )

    def load(self) -> AppConfig:
        return self.config

    def save(self, config: AppConfig, *, expected_config_revision: str) -> ConfigSnapshot:
        if expected_config_revision != self.config_revision:
            raise ConfigRevisionMismatchError(expected_config_revision, self.config_revision)
        self.config = config
        self.saves += 1
        self.config_revision = SAVED_CONFIG_REVISION
        return self.read_snapshot()


@dataclass(slots=True)
class _FakeArtistNameResolutionReader:
    names: dict[str, str | None]
    calls: list[tuple[str | None, ...]]

    def resolve_many(
        self,
        source_names: Sequence[str | None],
        *,
        preferences: Mapping[str, str] | None = None,
    ) -> tuple[ArtistNameResolution, ...]:
        exact_preferences = preferences or {}
        self.calls.append(tuple(source_names))
        return tuple(
            ArtistNameResolution(
                source_name=source_name,
                source_key=derive_artist_name_source_key(source_name),
                resolved_name=(
                    None
                    if source_name is None
                    else exact_preferences.get(source_name, self.names.get(source_name, source_name))
                ),
                provenance=(
                    ArtistNameResolutionProvenance.USER_PREFERENCE
                    if source_name is not None and source_name in exact_preferences
                    else ArtistNameResolutionProvenance.ORIGINAL
                ),
            )
            for source_name in source_names
        )


def test_generate_artist_ids_resolves_japanese_artist_before_generation() -> None:
    """Japanese source names use the resolved MusicBrainz name when available."""
    store = _MemoryConfigStore(AppConfig())

    result = _usecase(store, {JAPANESE_ARTIST: RESOLVED_ARTIST}).execute(GenerateArtistIdsRequest((JAPANESE_ARTIST,)))

    assert result.entries[0].generation_artist == RESOLVED_ARTIST
    assert result.entries[0].artist_id == "KENSHYNZ"
    assert store.config.artist_ids.entries == {JAPANESE_ARTIST: "KENSHYNZ"}


def test_generate_artist_ids_uses_display_preference_for_a_missing_compact_id() -> None:
    """An exact display preference can seed a new ID without coupling later edits to the saved value."""
    store = _MemoryConfigStore(AppConfig(artist_names=ArtistNameConfig(preferences={JAPANESE_ARTIST: RESOLVED_ARTIST})))

    result = _usecase(store, {}).execute(GenerateArtistIdsRequest((JAPANESE_ARTIST,)))

    assert result.entries[0].generation_artist == RESOLVED_ARTIST
    assert store.config.artist_ids.entries == {JAPANESE_ARTIST: "KENSHYNZ"}


def test_generate_artist_ids_generates_non_japanese_artist_directly() -> None:
    """The shared resolver can preserve a non-Japanese source for direct generation."""
    store = _MemoryConfigStore(AppConfig())

    result = _usecase(store, {}).execute(GenerateArtistIdsRequest((ENGLISH_ARTIST,)))

    assert result.entries[0].generation_artist == ENGLISH_ARTIST
    assert result.entries[0].artist_id == "JOHNSMTH"
    assert store.config.artist_ids.entries == {ENGLISH_ARTIST: "JOHNSMTH"}


def test_generate_artist_ids_falls_back_when_lookup_fails() -> None:
    """Japanese lookup failure falls back to deterministic source-name generation."""
    store = _MemoryConfigStore(AppConfig())

    result = _usecase(store, {JAPANESE_ARTIST: None}).execute(GenerateArtistIdsRequest((JAPANESE_ARTIST,)))

    assert result.entries[0].generation_artist == JAPANESE_ARTIST
    assert result.entries[0].artist_id == "NOART"


def test_generate_artist_ids_preserves_existing_saved_entry() -> None:
    """Normal generation does not overwrite user-edited entries."""
    store = _MemoryConfigStore(AppConfig(artist_ids=ArtistIdConfig(entries={ENGLISH_ARTIST: SAVED_ARTIST_ID})))

    result = _usecase(store, {}).execute(GenerateArtistIdsRequest((ENGLISH_ARTIST,)))

    assert result.entries[0].artist_id == SAVED_ARTIST_ID
    assert result.entries[0].saved is False
    assert store.saves == 0
    assert store.config.artist_ids.entries == {ENGLISH_ARTIST: SAVED_ARTIST_ID}


def test_generate_artist_ids_overwrites_when_requested() -> None:
    """Explicit regeneration can replace an existing editable entry."""
    store = _MemoryConfigStore(AppConfig(artist_ids=ArtistIdConfig(entries={ENGLISH_ARTIST: SAVED_ARTIST_ID})))

    result = _usecase(store, {}).execute(GenerateArtistIdsRequest((ENGLISH_ARTIST,), overwrite=True))

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
        _ = _usecase(store, {}).execute(GenerateArtistIdsRequest((NO_USABLE_CHARS_ARTIST,)))

    assert store.saves == 0


def _usecase(
    store: _MemoryConfigStore,
    resolved_names: dict[str, str | None],
) -> GenerateArtistIdsUseCase:
    return GenerateArtistIdsUseCase(
        config_store=store,
        artist_name_resolver=_FakeArtistNameResolutionReader(resolved_names, []),
    )
