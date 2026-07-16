"""
Summary: Tests artist ID CLI command behavior.
Why: Verifies generation is exposed without requiring live network/model I/O.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from io import StringIO
from typing import TYPE_CHECKING

from omym2.adapters.cli.commands.artist_ids import ArtistIdsCommandDependencies, run_artist_ids_command
from omym2.adapters.config.toml_config_store import TomlConfigStore
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.config import CONFIG_FILE_ENCODING
from omym2.domain.models.app_config import AppConfig, ArtistIdConfig
from omym2.domain.services.artist_name import derive_artist_name_source_key
from omym2.features.artist_names.dto import (
    ArtistLanguagePrediction,
    ArtistNameAliasCandidate,
    ArtistNameProviderCandidate,
    ArtistNameSearchResult,
)
from omym2.platform.artist_ids_composition import artist_ids_command_ports_for
from omym2.platform.operation_composition import OperationRuntime
from omym2.platform.runtime_context import runtime_context_for

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

JAPANESE_ARTIST = "米津玄師"
RESOLVED_ARTIST = "Kenshi Yonezu"
ENGLISH_ARTIST = "John Smith"
MODEL_LOAD_ERROR = "model cannot be loaded"
MUSICBRAINZ_ARTIST_ID = "db2f4f3a-f0c2-4c96-bea3-636f4b44f57b"


def _artist_ids_command_ports(config_path: Path, database_path: Path):
    """Build real command ports for one isolated CLI test root."""
    runtime = runtime_context_for(config_path, database_path)
    return artist_ids_command_ports_for(runtime, OperationRuntime(runtime))


@dataclass(frozen=True, slots=True)
class _JapanesePredictor:
    def predict_language(self, text: str) -> ArtistLanguagePrediction:
        return ArtistLanguagePrediction(
            label="__label__ja" if text == JAPANESE_ARTIST else "__label__en",
            confidence=0.99,
            available=True,
        )


@dataclass(frozen=True, slots=True)
class _Provider:
    def search_artists(self, source_name: str) -> ArtistNameSearchResult:
        if source_name != JAPANESE_ARTIST:
            return ArtistNameSearchResult(available=True)
        return ArtistNameSearchResult(
            available=True,
            candidates=(
                ArtistNameProviderCandidate(
                    provider_artist_id=MUSICBRAINZ_ARTIST_ID,
                    score=100,
                    name=source_name,
                    aliases=(ArtistNameAliasCandidate(name=RESOLVED_ARTIST, locale="en"),),
                ),
            ),
        )


def test_artist_ids_generate_command_saves_generated_entry(tmp_path: Path) -> None:
    """The CLI generates an editable TOML artist ID entry."""
    config_path = tmp_path / "config.toml"
    stdout = StringIO()
    stderr = StringIO()

    exit_code = run_artist_ids_command(
        ["generate", ENGLISH_ARTIST],
        stdout,
        stderr,
        _artist_ids_command_ports(config_path, tmp_path / "omym2.db"),
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert f"{ENGLISH_ARTIST}: JOHNSMTH (saved, from {ENGLISH_ARTIST})" in stdout.getvalue()
    assert TomlConfigStore(config_path).load().artist_ids.entries == {ENGLISH_ARTIST: "JOHNSMTH"}


def test_artist_ids_generate_command_uses_injected_japanese_dependencies(tmp_path: Path) -> None:
    """Injected fastText/MusicBrainz ports can resolve Japanese names before generation."""
    config_path = tmp_path / "config.toml"
    database_path = tmp_path / "omym2.db"
    stdout = StringIO()
    stderr = StringIO()

    exit_code = run_artist_ids_command(
        ["generate", JAPANESE_ARTIST],
        stdout,
        stderr,
        _artist_ids_command_ports(config_path, database_path),
        ArtistIdsCommandDependencies(
            language_predictor=_JapanesePredictor(),
            artist_name_provider=_Provider(),
        ),
    )

    assert exit_code == 0
    assert RESOLVED_ARTIST in stdout.getvalue()
    assert TomlConfigStore(config_path).load().artist_ids.entries == {JAPANESE_ARTIST: "KENSHYNZ"}
    source_key = derive_artist_name_source_key(JAPANESE_ARTIST)
    assert source_key is not None
    with SQLiteUnitOfWork(database_path) as uow:
        accepted = uow.accepted_artist_names.find_by_source_key(source_key)
        uow.commit()
    assert accepted is not None
    assert accepted.resolved_name == RESOLVED_ARTIST


def test_artist_ids_generate_command_preserves_existing_without_overwrite(tmp_path: Path) -> None:
    """Normal CLI generation keeps manual edits unless overwrite is requested."""
    config_path = tmp_path / "config.toml"
    store = TomlConfigStore(config_path)
    _ = store.save(
        AppConfig(artist_ids=ArtistIdConfig(entries={ENGLISH_ARTIST: "MANUAL"})),
        expected_config_revision=store.read_snapshot().config_revision,
    )
    stdout = StringIO()
    stderr = StringIO()

    exit_code = run_artist_ids_command(
        ["generate", ENGLISH_ARTIST],
        stdout,
        stderr,
        _artist_ids_command_ports(config_path, tmp_path / "omym2.db"),
    )

    assert exit_code == 0
    assert "preserved" in stdout.getvalue()
    assert TomlConfigStore(config_path).load().artist_ids.entries == {ENGLISH_ARTIST: "MANUAL"}


def test_artist_ids_generate_command_reports_invalid_persisted_config(tmp_path: Path) -> None:
    """The CLI reports invalid persisted TOML config as a controlled error, not a traceback."""
    config_path = tmp_path / "config.toml"
    _ = config_path.write_text(
        'version = 2\n[artist_ids]\nmax_length = 0\nfallback_id = "NOART"\n',
        encoding=CONFIG_FILE_ENCODING,
    )
    stdout = StringIO()
    stderr = StringIO()

    exit_code = run_artist_ids_command(
        ["generate", ENGLISH_ARTIST],
        stdout,
        stderr,
        _artist_ids_command_ports(config_path, tmp_path / "omym2.db"),
    )

    assert exit_code == 1
    assert stdout.getvalue() == ""
    assert "ArtistIdConfig max_length must be positive." in stderr.getvalue()


def test_artist_ids_generate_command_reports_missing_fasttext_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The optional fastText path returns a controlled CLI error when absent."""
    config_path = tmp_path / "config.toml"
    stdout = StringIO()
    stderr = StringIO()

    def missing_fasttext_module(_name: str) -> object:
        raise ModuleNotFoundError

    monkeypatch.setattr(importlib, "import_module", missing_fasttext_module)

    exit_code = run_artist_ids_command(
        ["generate", "--fasttext-model", str(tmp_path / "lid.bin"), ENGLISH_ARTIST],
        stdout,
        stderr,
        _artist_ids_command_ports(config_path, tmp_path / "omym2.db"),
    )

    assert exit_code == 1
    assert stdout.getvalue() == ""
    assert "fastText support requires the optional fasttext package." in stderr.getvalue()


def test_artist_ids_generate_command_reports_fasttext_model_load_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CLI reports unreadable model files without surfacing a traceback."""
    config_path = tmp_path / "config.toml"
    stdout = StringIO()
    stderr = StringIO()

    @dataclass(frozen=True, slots=True)
    class BrokenFastTextModule:
        def load_model(self, _path: str) -> object:
            raise ValueError(MODEL_LOAD_ERROR)

    def broken_fasttext_module(_name: str) -> object:
        return BrokenFastTextModule()

    monkeypatch.setattr(importlib, "import_module", broken_fasttext_module)

    exit_code = run_artist_ids_command(
        ["generate", "--fasttext-model", str(tmp_path / "missing.bin"), ENGLISH_ARTIST],
        stdout,
        stderr,
        _artist_ids_command_ports(config_path, tmp_path / "omym2.db"),
    )

    assert exit_code == 1
    assert stdout.getvalue() == ""
    assert "fastText model load failed." in stderr.getvalue()
    assert MODEL_LOAD_ERROR in stderr.getvalue()
