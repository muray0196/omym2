"""
Summary: Tests shared artist-name runtime and artist-ID command composition.
Why: Keeps persisted provider controls and local-only selection consistent.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from typing import TYPE_CHECKING

import pytest

from omym2 import __version__
from omym2.adapters.artist_ids.fasttext_language_detector import OptionalFastTextLanguageDetector
from omym2.adapters.artist_ids.musicbrainz_artist_lookup import MusicBrainzArtistLookup
from omym2.adapters.artist_ids.no_op_language_detector import NoOpLanguageDetector
from omym2.adapters.cli.commands.artist_ids import ArtistIdsCommandDependencies, run_artist_ids_command
from omym2.adapters.config.toml_config_store import TomlConfigStore
from omym2.adapters.db.sqlite.provider_request_cadence import SQLiteProviderRequestCadence
from omym2.domain.models.app_config import AppConfig, FastTextConfig, MusicBrainzConfig
from omym2.features.artist_names.dto import ArtistLanguagePrediction, ArtistNameSearchResult
from omym2.platform.artist_ids_composition import artist_ids_command_ports_for
from omym2.platform.artist_name_composition import (
    ArtistNameRuntime,
    automatic_language_predictor_for_model,
    language_predictor_for_model,
)
from omym2.platform.operation_composition import OperationRuntime
from omym2.platform.runtime_context import runtime_context_for

if TYPE_CHECKING:
    from pathlib import Path

JAPANESE_ARTIST = "米津玄師"
CONFIGURED_TIMEOUT_SECONDS = 2.25
CONFIGURED_RETRY_LIMIT = 4
CONFIGURED_RATE_LIMIT_SECONDS = 3.5


@dataclass(frozen=True, slots=True)
class _JapanesePredictor:
    """Return one deterministic eligible language observation."""

    def predict_language(self, text: str) -> ArtistLanguagePrediction:
        del text
        return ArtistLanguagePrediction(label="__label__ja", confidence=0.99, available=True)


def test_language_predictor_for_model_returns_no_op_when_model_path_is_none() -> None:
    """A missing --fasttext-model option selects the no-op predictor."""
    detector = language_predictor_for_model(None)

    assert isinstance(detector, NoOpLanguageDetector)


def test_automatic_language_predictor_for_model_is_lazy_when_model_path_is_present(tmp_path: Path) -> None:
    """Normal Plan selection records the model without importing fastText eagerly."""
    model_path = tmp_path / "lid.176.ftz"

    detector = automatic_language_predictor_for_model(model_path)

    assert isinstance(detector, OptionalFastTextLanguageDetector)
    assert detector.model_path == model_path


def test_automatic_language_predictor_for_model_returns_no_op_without_model_path() -> None:
    """Normal Plan selection stays local-only without a persisted model path."""
    detector = automatic_language_predictor_for_model(None)

    assert isinstance(detector, NoOpLanguageDetector)


def test_language_predictor_for_model_does_not_check_existence_for_nonexistent_path(tmp_path: Path) -> None:
    """language_predictor_for_model leaves model-file validation to fastText.

    fastText is an optional, uninstalled dependency in this environment, so building
    FastTextLanguageDetector(model_path=...) fails at model-load time with ModuleNotFoundError,
    exactly as artist_ids.py's command error handling expects before converting it into a CLI message.
    """
    nonexistent_model_path = tmp_path / "does-not-exist.bin"
    assert not nonexistent_model_path.exists()

    with pytest.raises(ModuleNotFoundError):
        _ = language_predictor_for_model(nonexistent_model_path)


def test_artist_name_runtime_anchors_relative_model_path_to_application_storage(tmp_path: Path) -> None:
    """Packaged launches never resolve persisted model paths from a transient working directory."""
    runtime = ArtistNameRuntime(tmp_path / ".data" / "omym2.sqlite3", tmp_path)

    detector = runtime.language_predictor_for(FastTextConfig(model_path="models/lid.176.ftz"))

    assert isinstance(detector, OptionalFastTextLanguageDetector)
    assert detector.model_path == tmp_path / "models" / "lid.176.ftz"


def test_artist_ids_generate_uses_persisted_shared_musicbrainz_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The explicit naming consumer reuses configured provider bounds and durable cadence."""
    config_path = tmp_path / "config.toml"
    database_path = tmp_path / "omym2.sqlite3"
    musicbrainz = MusicBrainzConfig(
        enabled=True,
        application_name="Configured App",
        contact="configured@example.invalid",
        timeout_seconds=CONFIGURED_TIMEOUT_SECONDS,
        retry_limit=CONFIGURED_RETRY_LIMIT,
        rate_limit_seconds=CONFIGURED_RATE_LIMIT_SECONDS,
    )
    store = TomlConfigStore(config_path)
    snapshot = store.read_snapshot()
    _ = store.save(
        AppConfig(musicbrainz=musicbrainz),
        expected_config_revision=snapshot.config_revision,
    )
    observed_providers: list[MusicBrainzArtistLookup] = []

    def record_provider(provider: MusicBrainzArtistLookup, _source_name: str) -> ArtistNameSearchResult:
        observed_providers.append(provider)
        return ArtistNameSearchResult(available=True)

    monkeypatch.setattr(MusicBrainzArtistLookup, "search_artists", record_provider)
    runtime = runtime_context_for(config_path, database_path)
    operations = OperationRuntime(runtime)
    expected_provider = runtime.artist_name_runtime.provider_for(musicbrainz)
    assert isinstance(expected_provider, MusicBrainzArtistLookup)
    try:
        exit_code = run_artist_ids_command(
            ["generate", JAPANESE_ARTIST],
            StringIO(),
            StringIO(),
            artist_ids_command_ports_for(runtime, operations),
            ArtistIdsCommandDependencies(language_predictor=_JapanesePredictor()),
        )
    finally:
        operations.close()

    assert exit_code == 0
    assert observed_providers == [expected_provider]
    assert expected_provider.user_agent == f"Configured App/{__version__} (configured@example.invalid)"
    assert expected_provider.timeout_seconds == CONFIGURED_TIMEOUT_SECONDS
    assert expected_provider.retry_limit == CONFIGURED_RETRY_LIMIT
    assert expected_provider.rate_limit_seconds == CONFIGURED_RATE_LIMIT_SECONDS
    cadence = expected_provider.request_cadence
    assert isinstance(cadence, SQLiteProviderRequestCadence)
    assert cadence.database_path == database_path
    assert cadence.provider == "musicbrainz"


def test_artist_ids_generate_without_fasttext_option_stays_local_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persisted provider enablement alone does not make the explicit command contact it."""
    config_path = tmp_path / "config.toml"
    store = TomlConfigStore(config_path)
    snapshot = store.read_snapshot()
    _ = store.save(
        AppConfig(musicbrainz=MusicBrainzConfig(enabled=True)),
        expected_config_revision=snapshot.config_revision,
    )

    def unexpected_provider_call(_provider: MusicBrainzArtistLookup, _source_name: str) -> ArtistNameSearchResult:
        pytest.fail("Local-only artist-ID generation must not contact MusicBrainz.")

    monkeypatch.setattr(MusicBrainzArtistLookup, "search_artists", unexpected_provider_call)
    runtime = runtime_context_for(config_path, tmp_path / "omym2.sqlite3")
    operations = OperationRuntime(runtime)
    try:
        exit_code = run_artist_ids_command(
            ["generate", JAPANESE_ARTIST],
            StringIO(),
            StringIO(),
            artist_ids_command_ports_for(runtime, operations),
        )
    finally:
        operations.close()

    assert exit_code == 0
