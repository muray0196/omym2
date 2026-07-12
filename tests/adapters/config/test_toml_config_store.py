"""
Summary: Tests TOML-backed config persistence.
Why: Verifies settings storage without touching the user home.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, cast

import pytest

from omym2.adapters.config import toml_config_store
from omym2.adapters.config.toml_config_store import TomlConfigStore, dump_config_toml, load_config_text
from omym2.config import ALBUM_YEAR_RESOLUTION_OLDEST, CONFIG_FILE_ENCODING
from omym2.domain.models.app_config import (
    INVALID_ARTIST_ID_ENTRY_VALUE_MESSAGE,
    INVALID_ARTIST_ID_FALLBACK_MESSAGE,
    INVALID_ARTIST_ID_MAX_LENGTH_MESSAGE,
    INVALID_MAX_FILENAME_LENGTH_MESSAGE,
    AppConfig,
    ArtistIdConfig,
    MetadataConfig,
    PathPolicyConfig,
    PathsConfig,
    UiConfig,
)
from omym2.features.common_ports import ConfigSnapshotState, ConfigStoreValidationError

if TYPE_CHECKING:
    from pathlib import Path

CONFIG_FILE_NAME = "config.toml"
INCOMING_PATH = "/music/incoming"
INVALID_MAX_FILENAME_LENGTH = 0
LIBRARY_PATH = "/music/library"
UI_THEME_DARK = "dark"
ARTIST_NAME = "Jane Doe"
ARTIST_ID = "JAND"
INJECTED_ARTIST_NAME = "Injected"
INJECTED_ARTIST_ID = "INJECTED"
FIRST_SAME_SIZE_LIBRARY_PATH = "/music/a"
SECOND_SAME_SIZE_LIBRARY_PATH = "/music/b"
DISC_NUMBER_STYLE_D_PREFIXED = "d_prefixed"
DISC_NUMBER_CONDITION_MULTIPLE_DISCS = "multiple_discs"


def test_toml_config_store_loads_default_when_config_missing(tmp_path: Path) -> None:
    """Missing config resolves to AppConfig defaults without creating a file."""
    config_path = tmp_path / CONFIG_FILE_NAME

    config = TomlConfigStore(config_path).load()

    assert config == AppConfig()
    assert not config_path.exists()


def test_toml_config_store_saves_and_loads_config(tmp_path: Path) -> None:
    """Saved TOML round-trips through the config adapter."""
    config_path = tmp_path / "nested" / CONFIG_FILE_NAME
    store = TomlConfigStore(config_path)
    config = AppConfig(
        paths=PathsConfig(library=LIBRARY_PATH, incoming=INCOMING_PATH),
        artist_ids=ArtistIdConfig(entries={ARTIST_NAME: ARTIST_ID}),
        metadata=MetadataConfig(album_year_resolution=ALBUM_YEAR_RESOLUTION_OLDEST),
        ui=UiConfig(theme=UI_THEME_DARK),
    )

    store.save(config)

    assert config_path.is_file()
    assert store.load() == config
    assert f'album_year_resolution = "{ALBUM_YEAR_RESOLUTION_OLDEST}"' in config_path.read_text(
        encoding=CONFIG_FILE_ENCODING
    )
    assert f'"{ARTIST_NAME}" = "{ARTIST_ID}"' in config_path.read_text(encoding=CONFIG_FILE_ENCODING)


def test_toml_config_store_saves_and_loads_disc_number_settings(tmp_path: Path) -> None:
    """Path policy disc settings round-trip through TOML."""
    config_path = tmp_path / CONFIG_FILE_NAME
    store = TomlConfigStore(config_path)
    config = AppConfig(
        path_policy=PathPolicyConfig(
            disc_number_style=DISC_NUMBER_STYLE_D_PREFIXED,
            disc_number_condition=DISC_NUMBER_CONDITION_MULTIPLE_DISCS,
        )
    )

    store.save(config)

    config_text = config_path.read_text(encoding=CONFIG_FILE_ENCODING)
    assert f'disc_number_style = "{DISC_NUMBER_STYLE_D_PREFIXED}"' in config_text
    assert f'disc_number_condition = "{DISC_NUMBER_CONDITION_MULTIPLE_DISCS}"' in config_text
    assert store.load() == config


def test_toml_config_store_load_caches_parsed_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A second load of an unchanged file reuses the parsed AppConfig."""
    config_path = tmp_path / CONFIG_FILE_NAME
    store = TomlConfigStore(config_path)
    store.save(AppConfig(ui=UiConfig(theme=UI_THEME_DARK)))
    parse_calls = 0
    real_load_config_text = toml_config_store.load_config_text

    def _counting_load(config_text: str) -> AppConfig:
        nonlocal parse_calls
        parse_calls += 1
        return real_load_config_text(config_text)

    monkeypatch.setattr(toml_config_store, "load_config_text", _counting_load)

    first_config = store.load()
    second_config = store.load()

    assert parse_calls == 1
    assert second_config is first_config


def test_toml_config_store_cached_artist_id_entries_are_immutable(tmp_path: Path) -> None:
    """Cached loads cannot be poisoned by unsaved artist ID entry mutations."""
    config_path = tmp_path / CONFIG_FILE_NAME
    store = TomlConfigStore(config_path)
    store.save(AppConfig(artist_ids=ArtistIdConfig(entries={ARTIST_NAME: ARTIST_ID})))

    first_config = store.load()
    assert first_config.artist_ids.entries is not None
    with pytest.raises(TypeError):
        cast("dict[str, str]", first_config.artist_ids.entries)[INJECTED_ARTIST_NAME] = INJECTED_ARTIST_ID

    second_config = store.load()

    assert second_config is first_config
    assert second_config.artist_ids.entries == {ARTIST_NAME: ARTIST_ID}


def test_toml_config_store_load_reparses_after_external_rewrite(tmp_path: Path) -> None:
    """Rewriting the config file with new content invalidates the cache."""
    config_path = tmp_path / CONFIG_FILE_NAME
    store = TomlConfigStore(config_path)
    store.save(AppConfig())

    assert store.load() == AppConfig()

    updated_config = AppConfig(ui=UiConfig(theme=UI_THEME_DARK))
    _ = config_path.write_text(dump_config_toml(updated_config), encoding=CONFIG_FILE_ENCODING)

    assert store.load() == updated_config


def test_toml_config_store_load_reparses_same_size_rewrite_with_preserved_mtime(tmp_path: Path) -> None:
    """A metadata-preserving external rewrite still invalidates the cache."""
    config_path = tmp_path / CONFIG_FILE_NAME
    first_text = f'version = 1\n\n[paths]\nlibrary = "{FIRST_SAME_SIZE_LIBRARY_PATH}"\n'
    second_text = f'version = 1\n\n[paths]\nlibrary = "{SECOND_SAME_SIZE_LIBRARY_PATH}"\n'
    assert len(first_text.encode(CONFIG_FILE_ENCODING)) == len(second_text.encode(CONFIG_FILE_ENCODING))
    _ = config_path.write_text(first_text, encoding=CONFIG_FILE_ENCODING)
    store = TomlConfigStore(config_path)

    assert store.load().paths.library == FIRST_SAME_SIZE_LIBRARY_PATH
    original_stat = config_path.stat()
    _ = config_path.write_text(second_text, encoding=CONFIG_FILE_ENCODING)
    os.utime(config_path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

    assert store.load().paths.library == SECOND_SAME_SIZE_LIBRARY_PATH


def test_toml_config_store_save_invalidates_cached_load(tmp_path: Path) -> None:
    """Saving after a cached load returns the newly saved config."""
    config_path = tmp_path / CONFIG_FILE_NAME
    store = TomlConfigStore(config_path)
    store.save(AppConfig())

    assert store.load() == AppConfig()

    updated_config = AppConfig(ui=UiConfig(theme=UI_THEME_DARK))
    store.save(updated_config)

    assert store.load() == updated_config


def test_toml_config_text_round_trips_default_config() -> None:
    """The deterministic TOML serializer produces loadable config text."""
    config = AppConfig()

    assert load_config_text(dump_config_toml(config)) == config


def test_toml_config_store_validation_fails_invalid_path_policy(tmp_path: Path) -> None:
    """Adapter validation reports domain path policy errors through ConfigStore."""
    config_path = tmp_path / CONFIG_FILE_NAME
    _ = config_path.write_text(
        "\n".join(
            (
                "version = 1",
                "",
                "[path_policy]",
                f"max_filename_length = {INVALID_MAX_FILENAME_LENGTH}",
            )
        ),
        encoding=CONFIG_FILE_ENCODING,
    )

    with pytest.raises(ConfigStoreValidationError, match=INVALID_MAX_FILENAME_LENGTH_MESSAGE):
        _ = TomlConfigStore(config_path).load()


def test_toml_config_store_validation_fails_invalid_disc_number_settings(tmp_path: Path) -> None:
    """Adapter validation rejects unsupported path policy disc setting values."""
    config_path = tmp_path / CONFIG_FILE_NAME
    _ = config_path.write_text(
        'version = 1\n\n[path_policy]\ndisc_number_style = "prefix"\ndisc_number_condition = "sometimes"',
        encoding=CONFIG_FILE_ENCODING,
    )

    with pytest.raises(ConfigStoreValidationError) as exc_info:
        _ = TomlConfigStore(config_path).load()

    assert "path_policy.disc_number_style" in str(exc_info.value)
    assert "path_policy.disc_number_condition" in str(exc_info.value)


def test_toml_config_store_validation_fails_invalid_artist_id_max_length(tmp_path: Path) -> None:
    """Adapter validation reports domain artist ID max_length errors through ConfigStore."""
    config_path = tmp_path / CONFIG_FILE_NAME
    _ = config_path.write_text(
        "version = 1\n\n[artist_ids]\nmax_length = 0\n",
        encoding=CONFIG_FILE_ENCODING,
    )

    with pytest.raises(ConfigStoreValidationError, match=INVALID_ARTIST_ID_MAX_LENGTH_MESSAGE):
        _ = TomlConfigStore(config_path).load()


def test_toml_config_store_validation_fails_invalid_artist_id_fallback_id(tmp_path: Path) -> None:
    """Adapter validation reports a non-sanitizer-stable configured fallback_id."""
    config_path = tmp_path / CONFIG_FILE_NAME
    _ = config_path.write_text(
        'version = 1\n\n[artist_ids]\nfallback_id = "N/A"\n',
        encoding=CONFIG_FILE_ENCODING,
    )

    with pytest.raises(ConfigStoreValidationError, match=INVALID_ARTIST_ID_FALLBACK_MESSAGE):
        _ = TomlConfigStore(config_path).load()


def test_toml_config_store_validation_fails_invalid_artist_id_entry_value(tmp_path: Path) -> None:
    """Adapter validation reports non-sanitizer-stable artist ID entry values."""
    config_path = tmp_path / CONFIG_FILE_NAME
    _ = config_path.write_text(
        "\n".join(
            (
                "version = 1",
                "",
                "[artist_ids.entries]",
                f'"{ARTIST_NAME}" = "../escape"',
            )
        ),
        encoding=CONFIG_FILE_ENCODING,
    )

    with pytest.raises(ConfigStoreValidationError, match=INVALID_ARTIST_ID_ENTRY_VALUE_MESSAGE):
        _ = TomlConfigStore(config_path).load()


def test_toml_config_store_validation_fails_invalid_album_year_resolution(tmp_path: Path) -> None:
    """Adapter validation rejects unknown album-year resolution methods."""
    config_path = tmp_path / CONFIG_FILE_NAME
    _ = config_path.write_text(
        'version = 1\n\n[metadata]\nalbum_year_resolution = "median"\n',
        encoding=CONFIG_FILE_ENCODING,
    )

    with pytest.raises(ConfigStoreValidationError, match=r"metadata\.album_year_resolution must be one of"):
        _ = TomlConfigStore(config_path).load()


def test_toml_config_store_validation_fails_removed_organize_only_misplaced_key(tmp_path: Path) -> None:
    """A config file still containing the removed organize.only_misplaced key is rejected."""
    config_path = tmp_path / CONFIG_FILE_NAME
    _ = config_path.write_text(
        "version = 1\n\n[organize]\nonly_misplaced = true\n",
        encoding=CONFIG_FILE_ENCODING,
    )

    with pytest.raises(ConfigStoreValidationError, match=r"Unknown config key: organize\.only_misplaced\."):
        _ = TomlConfigStore(config_path).load()


def test_toml_config_store_validation_fails_invalid_toml(tmp_path: Path) -> None:
    """Malformed TOML is reported as a config validation error."""
    config_path = tmp_path / CONFIG_FILE_NAME
    _ = config_path.write_text("version = ", encoding=CONFIG_FILE_ENCODING)

    with pytest.raises(ConfigStoreValidationError, match="Invalid TOML"):
        _ = TomlConfigStore(config_path).load()


def test_toml_config_text_loads_missing_artist_id_defaults() -> None:
    """Missing artist_ids config resolves to documented defaults."""
    config = load_config_text("version = 1\n")

    assert config.artist_ids == ArtistIdConfig()


def test_config_snapshot_gives_missing_storage_a_stable_revision_without_creating_file(tmp_path: Path) -> None:
    """Missing Config is a valid default snapshot with real opaque identity."""
    config_path = tmp_path / CONFIG_FILE_NAME
    store = TomlConfigStore(config_path)

    first = store.read_snapshot()
    second = store.read_snapshot()

    assert first.state is ConfigSnapshotState.MISSING
    assert first.config == AppConfig()
    assert first.errors == ()
    assert first.config_revision == second.config_revision
    assert first.config_revision.startswith("v1:")
    assert not config_path.exists()


def test_config_snapshot_preserves_revision_and_recovery_defaults_for_invalid_toml(tmp_path: Path) -> None:
    """Invalid raw Config remains identifiable without returning its source text."""
    config_path = tmp_path / CONFIG_FILE_NAME
    _ = config_path.write_text("version = ", encoding=CONFIG_FILE_ENCODING)

    snapshot = TomlConfigStore(config_path).read_snapshot()

    assert snapshot.state is ConfigSnapshotState.INVALID
    assert snapshot.config == AppConfig()
    assert snapshot.config_revision.startswith("v1:")
    assert snapshot.errors
    assert "Invalid TOML" in snapshot.errors[0]


def test_config_snapshot_revision_changes_after_identical_file_replacement(tmp_path: Path) -> None:
    """Replacing Config with identical bytes still changes raw storage identity."""
    config_path = tmp_path / CONFIG_FILE_NAME
    replacement_path = tmp_path / "replacement.toml"
    config_text = dump_config_toml(AppConfig())
    _ = config_path.write_text(config_text, encoding=CONFIG_FILE_ENCODING)
    store = TomlConfigStore(config_path)
    before = store.read_snapshot()

    _ = replacement_path.write_text(config_text, encoding=CONFIG_FILE_ENCODING)
    _ = replacement_path.replace(config_path)
    after = store.read_snapshot()

    assert before.state is ConfigSnapshotState.VALID
    assert after.state is ConfigSnapshotState.VALID
    assert after.config == before.config
    assert after.config_revision != before.config_revision


def test_config_snapshot_revision_changes_with_raw_content(tmp_path: Path) -> None:
    """A raw Config edit produces a new opaque revision."""
    config_path = tmp_path / CONFIG_FILE_NAME
    store = TomlConfigStore(config_path)
    store.save(AppConfig(paths=PathsConfig(library=FIRST_SAME_SIZE_LIBRARY_PATH)))
    before = store.read_snapshot()

    store.save(AppConfig(paths=PathsConfig(library=SECOND_SAME_SIZE_LIBRARY_PATH)))
    after = store.read_snapshot()

    assert after.config_revision != before.config_revision
