"""
Summary: Tests CLI dependency bundle construction.
Why: Verifies command entry point wiring preserves path overrides.
"""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING

from fastapi import FastAPI

from omym2.platform.cli_composition import command_dependencies_for_runtime
from omym2.platform.runtime_context import runtime_context_for

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

    def build_web_app(config_path: Path, database_path: Path) -> FastAPI:
        captured_args.append((config_path, database_path, None))
        return FastAPI()

    monkeypatch.setattr("omym2.platform.cli_composition._build_web_app", build_web_app)

    dependencies = command_dependencies_for_runtime(runtime_context_for(config_path, database_path))
    app = dependencies.settings.web_app_factory()

    assert isinstance(app, FastAPI)
    assert captured_args == [(config_path, database_path, None)]


def test_building_cli_dependencies_does_not_import_web_stack() -> None:
    """Non-settings CLI startup leaves Web and optional native desktop stacks unloaded."""
    script = """
import sys
from omym2.platform.cli_composition import command_dependencies_for_runtime
from omym2.platform.runtime_context import runtime_context_for

_ = command_dependencies_for_runtime(runtime_context_for())
for module_name in (
    "fastapi",
    "omym2.platform.web_composition",
    "uvicorn",
    "webview",
    "omym2.adapters.desktop.window",
    "omym2.platform.desktop_entry_point",
):
    assert module_name not in sys.modules, module_name
"""

    _ = subprocess.run(  # noqa: S603  # The current interpreter runs a fixed regression script.
        [sys.executable, "-c", script],
        check=True,
    )


def test_path_normalizer_is_injected_to_path_consuming_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI composition should inject shared CLI path normalization into add/organize/refresh."""

    def fake_normalize(path: object) -> str:
        return f"normalized:{path}"

    monkeypatch.setattr("omym2.platform.cli_composition.normalize_cli_path", fake_normalize)

    dependencies = command_dependencies_for_runtime(runtime_context_for())

    assert dependencies.add.normalize_source_path is fake_normalize
    assert dependencies.organize.normalize_library_root is fake_normalize
    assert dependencies.refresh.normalize_target_path is fake_normalize
