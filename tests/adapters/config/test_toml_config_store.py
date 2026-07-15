"""
Summary: Tests TOML-backed config persistence.
Why: Verifies settings storage without touching the user home.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import cast

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
    ArtistNameConfig,
    MetadataConfig,
    PathPolicyConfig,
    PathsConfig,
)
from omym2.features.common_ports import (
    ConfigRevisionMismatchError,
    ConfigSnapshotState,
    ConfigStoreIoError,
    ConfigStoreValidationError,
)

CONFIG_FILE_NAME = "config.toml"
INCOMING_PATH = "/music/incoming"
INVALID_MAX_FILENAME_LENGTH = 0
LIBRARY_PATH = "/music/library"
ARTIST_NAME = "Jane Doe"
ARTIST_ID = "JAND"
PREFERRED_ARTIST_NAME = "Jane D."
INJECTED_ARTIST_NAME = "Injected"
INJECTED_ARTIST_ID = "INJECTED"
FIRST_SAME_SIZE_LIBRARY_PATH = "/music/a"
SECOND_SAME_SIZE_LIBRARY_PATH = "/music/b"
DISC_NUMBER_STYLE_D_PREFIXED = "d_prefixed"
DISC_NUMBER_CONDITION_MULTIPLE_DISCS = "multiple_discs"
REPLACE_FAILURE_MESSAGE = "injected Config replace failure"


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
        artist_names=ArtistNameConfig(preferences={ARTIST_NAME: PREFERRED_ARTIST_NAME}),
        metadata=MetadataConfig(album_year_resolution=ALBUM_YEAR_RESOLUTION_OLDEST),
    )

    _save_current(store, config)

    assert config_path.is_file()
    assert store.load() == config
    assert f'album_year_resolution = "{ALBUM_YEAR_RESOLUTION_OLDEST}"' in config_path.read_text(
        encoding=CONFIG_FILE_ENCODING
    )
    assert f'"{ARTIST_NAME}" = "{ARTIST_ID}"' in config_path.read_text(encoding=CONFIG_FILE_ENCODING)
    assert f'"{ARTIST_NAME}" = "{PREFERRED_ARTIST_NAME}"' in config_path.read_text(encoding=CONFIG_FILE_ENCODING)


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

    _save_current(store, config)

    config_text = config_path.read_text(encoding=CONFIG_FILE_ENCODING)
    assert f'disc_number_style = "{DISC_NUMBER_STYLE_D_PREFIXED}"' in config_text
    assert f'disc_number_condition = "{DISC_NUMBER_CONDITION_MULTIPLE_DISCS}"' in config_text
    assert store.load() == config


def test_toml_config_store_load_caches_parsed_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A second load of an unchanged file reuses the parsed AppConfig."""
    config_path = tmp_path / CONFIG_FILE_NAME
    store = TomlConfigStore(config_path)
    _save_current(store, AppConfig(paths=PathsConfig(library=LIBRARY_PATH)))
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
    _save_current(store, AppConfig(artist_ids=ArtistIdConfig(entries={ARTIST_NAME: ARTIST_ID})))

    first_config = store.load()
    assert first_config.artist_ids.entries is not None
    with pytest.raises(TypeError):
        cast("dict[str, str]", first_config.artist_ids.entries)[INJECTED_ARTIST_NAME] = INJECTED_ARTIST_ID

    second_config = store.load()

    assert second_config is first_config
    assert second_config.artist_ids.entries == {ARTIST_NAME: ARTIST_ID}


def test_toml_config_store_cached_artist_name_preferences_are_immutable(tmp_path: Path) -> None:
    """Cached loads cannot be poisoned by unsaved artist display-name mutations."""
    config_path = tmp_path / CONFIG_FILE_NAME
    store = TomlConfigStore(config_path)
    _save_current(
        store,
        AppConfig(artist_names=ArtistNameConfig(preferences={ARTIST_NAME: PREFERRED_ARTIST_NAME})),
    )

    first_config = store.load()
    assert first_config.artist_names.preferences is not None
    with pytest.raises(TypeError):
        cast("dict[str, str]", first_config.artist_names.preferences)[INJECTED_ARTIST_NAME] = ARTIST_NAME

    second_config = store.load()

    assert second_config is first_config
    assert second_config.artist_names.preferences == {ARTIST_NAME: PREFERRED_ARTIST_NAME}


def test_toml_config_store_load_reparses_after_external_rewrite(tmp_path: Path) -> None:
    """Rewriting the config file with new content invalidates the cache."""
    config_path = tmp_path / CONFIG_FILE_NAME
    store = TomlConfigStore(config_path)
    _save_current(store, AppConfig())

    assert store.load() == AppConfig()

    updated_config = AppConfig(paths=PathsConfig(library=LIBRARY_PATH))
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
    _save_current(store, AppConfig())

    assert store.load() == AppConfig()

    updated_config = AppConfig(paths=PathsConfig(library=LIBRARY_PATH))
    _save_current(store, updated_config)

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


@pytest.mark.parametrize("invalid_value", ['""', '"   "', "42"])
def test_toml_config_store_validation_fails_invalid_artist_name_preference(
    tmp_path: Path,
    invalid_value: str,
) -> None:
    """Artist display-name preferences require nonblank string values."""
    config_path = tmp_path / CONFIG_FILE_NAME
    _ = config_path.write_text(
        f'version = 1\n\n[artist_names.preferences]\n"{ARTIST_NAME}" = {invalid_value}\n',
        encoding=CONFIG_FILE_ENCODING,
    )

    with pytest.raises(ConfigStoreValidationError, match=r"artist_names\.preferences"):
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


def test_toml_config_store_validation_fails_removed_ui_section(tmp_path: Path) -> None:
    """A config file still containing the removed UI section is rejected."""
    config_path = tmp_path / CONFIG_FILE_NAME
    _ = config_path.write_text(
        'version = 1\n\n[ui]\ntheme = "dark"\nshow_advanced_settings = true\n',
        encoding=CONFIG_FILE_ENCODING,
    )

    with pytest.raises(ConfigStoreValidationError, match="Unknown config key: ui"):
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


def test_toml_config_text_loads_missing_artist_name_defaults() -> None:
    """Missing artist_names config resolves to an empty preference mapping."""
    config = load_config_text("version = 1\n")

    assert config.artist_names == ArtistNameConfig()


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


def test_config_snapshot_wraps_raw_storage_io_failure(tmp_path: Path) -> None:
    """Unusable raw Config storage surfaces through the typed I/O boundary."""
    config_path = tmp_path / CONFIG_FILE_NAME
    config_path.mkdir()

    with pytest.raises(ConfigStoreIoError) as exc_info:
        _ = TomlConfigStore(config_path).read_snapshot()

    assert isinstance(exc_info.value.cause, IsADirectoryError)


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
    _save_current(store, AppConfig(paths=PathsConfig(library=FIRST_SAME_SIZE_LIBRARY_PATH)))
    before = store.read_snapshot()

    _save_current(store, AppConfig(paths=PathsConfig(library=SECOND_SAME_SIZE_LIBRARY_PATH)))
    after = store.read_snapshot()

    assert after.config_revision != before.config_revision


def test_config_snapshot_uses_open_handle_identity_for_path_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Config reads remain stable when pathname stat metadata differs from handle metadata."""
    config_path = tmp_path / CONFIG_FILE_NAME
    _ = config_path.write_text(dump_config_toml(AppConfig()), encoding=CONFIG_FILE_ENCODING)
    real_path_stat = Path.stat

    def _mismatched_path_stat(path: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        result = real_path_stat(path, follow_symlinks=follow_symlinks)
        values = list(result)
        values[1] += 1
        return os.stat_result(values)

    monkeypatch.setattr(Path, "stat", _mismatched_path_stat)

    snapshot = TomlConfigStore(config_path).read_snapshot()

    assert snapshot.state is ConfigSnapshotState.VALID
    assert snapshot.config == AppConfig()


def test_config_save_creates_missing_file_with_new_valid_revision_and_synced_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A matching missing revision installs deterministic TOML and syncs file and directory."""
    config_path = tmp_path / "nested" / CONFIG_FILE_NAME
    store = TomlConfigStore(config_path)
    missing_snapshot = store.read_snapshot()
    fsync_calls = 0
    real_fsync = os.fsync

    def _counting_fsync(file_descriptor: int) -> None:
        nonlocal fsync_calls
        fsync_calls += 1
        real_fsync(file_descriptor)

    monkeypatch.setattr(os, "fsync", _counting_fsync)

    installed = store.save(AppConfig(), expected_config_revision=missing_snapshot.config_revision)

    assert installed.state is ConfigSnapshotState.VALID
    assert installed.config == AppConfig()
    assert installed.config_revision != missing_snapshot.config_revision
    assert config_path.read_text(encoding=CONFIG_FILE_ENCODING) == dump_config_toml(AppConfig())
    assert fsync_calls == (1 if os.name == "nt" else 2)
    assert tuple(config_path.parent.glob(f".{CONFIG_FILE_NAME}.*.tmp")) == ()


def test_config_save_can_replace_invalid_raw_state_with_its_observed_revision(tmp_path: Path) -> None:
    """Invalid Config recovery succeeds only through the raw revision that identified it."""
    config_path = tmp_path / CONFIG_FILE_NAME
    _ = config_path.write_text("version = ", encoding=CONFIG_FILE_ENCODING)
    store = TomlConfigStore(config_path)
    invalid_snapshot = store.read_snapshot()
    replacement = AppConfig(paths=PathsConfig(library=LIBRARY_PATH))

    installed = store.save(replacement, expected_config_revision=invalid_snapshot.config_revision)

    assert invalid_snapshot.state is ConfigSnapshotState.INVALID
    assert installed.state is ConfigSnapshotState.VALID
    assert installed.config == replacement
    assert installed.errors == ()


def test_config_save_rejects_stale_revision_without_writing(tmp_path: Path) -> None:
    """An initial revision mismatch is a typed conflict and leaves current bytes unchanged."""
    config_path = tmp_path / CONFIG_FILE_NAME
    store = TomlConfigStore(config_path)
    stale_revision = store.read_snapshot().config_revision
    current = AppConfig(paths=PathsConfig(library=FIRST_SAME_SIZE_LIBRARY_PATH))
    _save_current(store, current)
    current_bytes = config_path.read_bytes()

    with pytest.raises(ConfigRevisionMismatchError) as exc_info:
        _ = store.save(AppConfig(), expected_config_revision=stale_revision)

    assert exc_info.value.expected_config_revision == stale_revision
    assert exc_info.value.actual_config_revision == store.read_snapshot().config_revision
    assert config_path.read_bytes() == current_bytes
    assert tuple(tmp_path.glob(f".{CONFIG_FILE_NAME}.*.tmp")) == ()


def test_config_save_detects_external_replacement_before_atomic_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The second revision check preserves an identical external replacement after temp sync."""
    config_path = tmp_path / CONFIG_FILE_NAME
    replacement_path = tmp_path / "external.toml"
    store = TomlConfigStore(config_path)
    _save_current(store, AppConfig())
    expected_revision = store.read_snapshot().config_revision
    external_config = AppConfig()
    real_fsync = os.fsync
    fsync_calls = 0

    def _replace_after_temp_sync(file_descriptor: int) -> None:
        nonlocal fsync_calls
        real_fsync(file_descriptor)
        fsync_calls += 1
        if fsync_calls == 1:
            _ = replacement_path.write_text(dump_config_toml(external_config), encoding=CONFIG_FILE_ENCODING)
            _ = replacement_path.replace(config_path)

    monkeypatch.setattr(os, "fsync", _replace_after_temp_sync)

    with pytest.raises(ConfigRevisionMismatchError):
        _ = store.save(
            AppConfig(paths=PathsConfig(library=LIBRARY_PATH)),
            expected_config_revision=expected_revision,
        )

    assert store.load() == external_config
    assert tuple(tmp_path.glob(f".{CONFIG_FILE_NAME}.*.tmp")) == ()


def test_config_save_propagates_replace_io_failure_and_removes_temp_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A destination I/O failure is observable, preserves Config, and leaves no temp file."""
    config_path = tmp_path / CONFIG_FILE_NAME
    store = TomlConfigStore(config_path)
    current = AppConfig(paths=PathsConfig(library=FIRST_SAME_SIZE_LIBRARY_PATH))
    _save_current(store, current)
    expected_revision = store.read_snapshot().config_revision
    current_bytes = config_path.read_bytes()

    def _fail_replace(_source: object, _target: object) -> None:
        raise OSError(REPLACE_FAILURE_MESSAGE)

    monkeypatch.setattr(os, "replace", _fail_replace)

    with pytest.raises(ConfigStoreIoError, match=REPLACE_FAILURE_MESSAGE) as exc_info:
        _ = store.save(
            AppConfig(paths=PathsConfig(library=LIBRARY_PATH)),
            expected_config_revision=expected_revision,
        )

    assert isinstance(exc_info.value.cause, OSError)
    assert config_path.read_bytes() == current_bytes
    assert tuple(tmp_path.glob(f".{CONFIG_FILE_NAME}.*.tmp")) == ()


def _save_current(store: TomlConfigStore, config: AppConfig) -> None:
    """Save one test Config against the raw revision observed immediately beforehand."""
    _ = store.save(config, expected_config_revision=store.read_snapshot().config_revision)
