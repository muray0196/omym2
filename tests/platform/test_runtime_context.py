"""
Summary: Tests RuntimeContext path and shared adapter construction.
Why: Verifies storage overrides and optional naming activation stay process-scoped.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from omym2.adapters.artist_ids.fasttext_language_detector import OptionalFastTextLanguageDetector
from omym2.adapters.artist_ids.musicbrainz_artist_lookup import MusicBrainzArtistLookup
from omym2.adapters.artist_ids.no_op_language_detector import NoOpLanguageDetector
from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.config.toml_config_store import TomlConfigStore
from omym2.adapters.fs.exclusive_operation_lock import FilesystemExclusiveOperationLock
from omym2.adapters.metadata.mutagen_reader import MutagenMetadataReader
from omym2.config import ARTIST_NAME_FASTTEXT_MODEL_PATH_ENVIRONMENT_VARIABLE
from omym2.platform.runtime_context import runtime_context_for

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_runtime_context_for_uses_explicit_path_overrides(tmp_path: Path) -> None:
    """Explicit config and database paths are used as-is, not resolved from application paths."""
    config_path = tmp_path / "config.toml"
    database_path = tmp_path / "omym2.sqlite3"

    runtime = runtime_context_for(config_path, database_path)

    assert runtime.config_file == config_path
    assert runtime.database_file == database_path
    assert isinstance(runtime.exclusive_operation_lock, FilesystemExclusiveOperationLock)


def test_runtime_context_for_falls_back_to_default_application_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Omitted paths fall back to default_application_paths() values."""
    monkeypatch.chdir(tmp_path)
    expected_paths = default_application_paths()

    runtime = runtime_context_for()

    assert runtime.config_file == expected_paths.config_file
    assert runtime.database_file == expected_paths.database_file
    assert runtime.application_root == expected_paths.app_root
    assert runtime.exclusive_operation_lock.lock_file == expected_paths.exclusive_operation_lock_file


def test_runtime_context_for_infers_standard_overridden_application_root(tmp_path: Path) -> None:
    """Web tests and embedded callers share the lock rooted beside standard Config and DB paths."""
    expected_paths = default_application_paths(tmp_path)

    runtime = runtime_context_for(expected_paths.config_file, expected_paths.database_file)

    assert runtime.application_root == tmp_path
    assert runtime.exclusive_operation_lock.lock_file == expected_paths.exclusive_operation_lock_file


def test_runtime_context_for_anchors_lock_to_effective_database_when_only_config_is_overridden(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Config override cannot move the lock away from another process sharing the default DB."""
    default_root = tmp_path / "default-root"
    custom_root = tmp_path / "custom-root"
    default_root.mkdir()
    monkeypatch.chdir(default_root)
    default_paths = default_application_paths()

    default_runtime = runtime_context_for()
    overridden_runtime = runtime_context_for(custom_root / ".config" / "config.toml")

    assert overridden_runtime.database_file == default_paths.database_file
    assert overridden_runtime.exclusive_operation_lock.lock_file == default_runtime.exclusive_operation_lock.lock_file


def test_runtime_context_for_calls_default_application_paths_exactly_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """default_application_paths is resolved a single time per runtime_context_for call."""
    call_count = 0
    real_default_application_paths = default_application_paths

    def counting_default_application_paths(app_root: Path | None = None) -> object:
        nonlocal call_count
        call_count += 1
        return real_default_application_paths(app_root)

    monkeypatch.setattr(
        "omym2.platform.runtime_context.default_application_paths",
        counting_default_application_paths,
    )
    monkeypatch.chdir(tmp_path)

    _ = runtime_context_for()

    assert call_count == 1


def test_runtime_context_for_constructs_one_shared_config_store_and_metadata_reader(tmp_path: Path) -> None:
    """The config store and metadata reader are constructed once and exposed on the context."""
    config_path = tmp_path / "config.toml"
    database_path = tmp_path / "omym2.sqlite3"

    runtime = runtime_context_for(config_path, database_path)

    assert isinstance(runtime.config_store, TomlConfigStore)
    assert runtime.config_store.config_path == config_path
    assert isinstance(runtime.metadata_reader, MutagenMetadataReader)


def test_runtime_context_for_disables_new_artist_name_lookups_without_process_opt_in(tmp_path: Path) -> None:
    """An absent model-path environment value keeps normal Plan composition local-only."""
    runtime = runtime_context_for(
        tmp_path / "config.toml",
        tmp_path / "omym2.sqlite3",
        environment={},
    )

    assert isinstance(runtime.artist_name_language_predictor, NoOpLanguageDetector)
    assert isinstance(runtime.artist_name_provider, MusicBrainzArtistLookup)


def test_runtime_context_for_builds_one_lazy_predictor_from_process_opt_in(tmp_path: Path) -> None:
    """A non-empty model path activates lazy automatic lookup for the shared process runtime."""
    model_path = tmp_path / "lid.176.ftz"
    runtime = runtime_context_for(
        tmp_path / "config.toml",
        tmp_path / "omym2.sqlite3",
        environment={ARTIST_NAME_FASTTEXT_MODEL_PATH_ENVIRONMENT_VARIABLE: f"  {model_path}  "},
    )

    predictor = runtime.artist_name_language_predictor
    assert isinstance(predictor, OptionalFastTextLanguageDetector)
    assert predictor.model_path == model_path


def test_runtime_context_for_treats_blank_artist_name_model_path_as_disabled(tmp_path: Path) -> None:
    """Whitespace-only runtime configuration cannot accidentally enable model work."""
    runtime = runtime_context_for(
        tmp_path / "config.toml",
        tmp_path / "omym2.sqlite3",
        environment={ARTIST_NAME_FASTTEXT_MODEL_PATH_ENVIRONMENT_VARIABLE: "   "},
    )

    assert isinstance(runtime.artist_name_language_predictor, NoOpLanguageDetector)
