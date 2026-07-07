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
from omym2.config import CONFIG_FILE_ENCODING
from omym2.domain.models.app_config import AppConfig, ArtistIdConfig
from omym2.platform.artist_ids_composition import build_artist_ids_command_ports

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

JAPANESE_ARTIST = "米津玄師"
RESOLVED_ARTIST = "Kenshi Yonezu"
ENGLISH_ARTIST = "John Smith"
MODEL_LOAD_ERROR = "model cannot be loaded"


@dataclass(frozen=True, slots=True)
class _JapaneseDetector:
    def is_japanese(self, text: str) -> bool:
        return text == JAPANESE_ARTIST


@dataclass(frozen=True, slots=True)
class _Resolver:
    def english_or_latin_name(self, source_artist: str) -> str | None:
        if source_artist == JAPANESE_ARTIST:
            return RESOLVED_ARTIST
        return None


def test_artist_ids_generate_command_saves_generated_entry(tmp_path: Path) -> None:
    """The CLI generates an editable TOML artist ID entry."""
    config_path = tmp_path / "config.toml"
    stdout = StringIO()
    stderr = StringIO()

    exit_code = run_artist_ids_command(
        ["generate", ENGLISH_ARTIST], stdout, stderr, build_artist_ids_command_ports(config_path)
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert f"{ENGLISH_ARTIST}: JOHNSMTH (saved, from {ENGLISH_ARTIST})" in stdout.getvalue()
    assert TomlConfigStore(config_path).load().artist_ids.entries == {ENGLISH_ARTIST: "JOHNSMTH"}


def test_artist_ids_generate_command_uses_injected_japanese_dependencies(tmp_path: Path) -> None:
    """Injected fastText/MusicBrainz ports can resolve Japanese names before generation."""
    config_path = tmp_path / "config.toml"
    stdout = StringIO()
    stderr = StringIO()

    exit_code = run_artist_ids_command(
        ["generate", JAPANESE_ARTIST],
        stdout,
        stderr,
        build_artist_ids_command_ports(config_path),
        ArtistIdsCommandDependencies(language_detector=_JapaneseDetector(), artist_resolver=_Resolver()),
    )

    assert exit_code == 0
    assert RESOLVED_ARTIST in stdout.getvalue()
    assert TomlConfigStore(config_path).load().artist_ids.entries == {JAPANESE_ARTIST: "KENSHYNZ"}


def test_artist_ids_generate_command_preserves_existing_without_overwrite(tmp_path: Path) -> None:
    """Normal CLI generation keeps manual edits unless overwrite is requested."""
    config_path = tmp_path / "config.toml"
    TomlConfigStore(config_path).save(AppConfig(artist_ids=ArtistIdConfig(entries={ENGLISH_ARTIST: "MANUAL"})))
    stdout = StringIO()
    stderr = StringIO()

    exit_code = run_artist_ids_command(
        ["generate", ENGLISH_ARTIST], stdout, stderr, build_artist_ids_command_ports(config_path)
    )

    assert exit_code == 0
    assert "preserved" in stdout.getvalue()
    assert TomlConfigStore(config_path).load().artist_ids.entries == {ENGLISH_ARTIST: "MANUAL"}


def test_artist_ids_generate_command_reports_invalid_persisted_config(tmp_path: Path) -> None:
    """The CLI reports invalid persisted TOML config as a controlled error, not a traceback."""
    config_path = tmp_path / "config.toml"
    _ = config_path.write_text(
        'version = 1\n[artist_ids]\nmax_length = 0\nfallback_id = "NOART"\n',
        encoding=CONFIG_FILE_ENCODING,
    )
    stdout = StringIO()
    stderr = StringIO()

    exit_code = run_artist_ids_command(
        ["generate", ENGLISH_ARTIST], stdout, stderr, build_artist_ids_command_ports(config_path)
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
        build_artist_ids_command_ports(config_path),
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
        build_artist_ids_command_ports(config_path),
    )

    assert exit_code == 1
    assert stdout.getvalue() == ""
    assert "fastText model load failed." in stderr.getvalue()
    assert MODEL_LOAD_ERROR in stderr.getvalue()
