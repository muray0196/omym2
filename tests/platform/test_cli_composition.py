"""
Summary: Tests CLI dependency bundle construction.
Why: Verifies command entry point wiring preserves path overrides.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI

from omym2.platform.cli_composition import build_command_dependencies

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_settings_web_app_factory_uses_config_and_database_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The settings command must serve the same config and database selected for the CLI invocation."""
    config_path = tmp_path / "config.toml"
    database_path = tmp_path / "omym2.sqlite3"
    captured_args: list[tuple[Path | None, Path | None, Path | None]] = []

    def build_web_app(
        config_path: Path | None = None,
        database_path: Path | None = None,
        static_dist_path: Path | None = None,
    ) -> FastAPI:
        captured_args.append((config_path, database_path, static_dist_path))
        return FastAPI()

    monkeypatch.setattr("omym2.platform.cli_composition.build_web_app", build_web_app)

    dependencies = build_command_dependencies(config_path, database_path)
    app = dependencies.settings.web_app_factory()

    assert isinstance(app, FastAPI)
    assert captured_args == [(config_path, database_path, None)]


def test_path_normalizer_is_injected_to_path_consuming_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI composition should inject shared CLI path normalization into add/organize/refresh."""

    def fake_normalize(path: object) -> str:
        return f"normalized:{path}"

    monkeypatch.setattr("omym2.platform.cli_composition.normalize_cli_path", fake_normalize)

    dependencies = build_command_dependencies()

    assert dependencies.add.normalize_source_path is fake_normalize
    assert dependencies.organize.normalize_library_root is fake_normalize
    assert dependencies.refresh.normalize_target_path is fake_normalize
