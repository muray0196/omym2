"""
Summary: Tests RuntimeContext construction.
Why: Verifies path overrides, cwd fallback, and shared adapter construction stay correct.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.config.toml_config_store import TomlConfigStore
from omym2.adapters.metadata.mutagen_reader import MutagenMetadataReader
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
