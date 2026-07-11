"""
Summary: Builds the CLI CommandDependencies bundle from concrete adapters.
Why: Wires all 12 CLI commands' ports and factories through one shared RuntimeContext.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from omym2.adapters.cli.commands.add import AddCommandDependencies
from omym2.adapters.cli.commands.apply import ApplyCommandDependencies
from omym2.adapters.cli.commands.organize import OrganizeCommandDependencies
from omym2.adapters.cli.commands.refresh import RefreshCommandDependencies
from omym2.adapters.cli.commands.settings import SettingsCommandPorts
from omym2.adapters.cli.commands.undo import UndoCommandDependencies
from omym2.adapters.cli.main import CommandDependencies
from omym2.platform.artist_ids_composition import artist_ids_command_ports_for
from omym2.platform.cli_path_normalization import normalize_cli_path
from omym2.platform.feature_composition import (
    build_apply_plan_ports,
    build_check_library_ports,
    build_create_add_plan_ports,
    build_create_organize_plan_ports,
    build_create_refresh_plan_ports,
    build_create_undo_plan_ports,
    build_history_ports,
    build_inspect_file_ports,
    build_plan_query_ports,
    build_settings_ports,
    build_uow,
)
from omym2.platform.runtime_context import runtime_context_for

if TYPE_CHECKING:
    from pathlib import Path

    from fastapi import FastAPI


def _build_web_app(config_path: Path, database_path: Path) -> FastAPI:
    """Build the settings Web app without importing its stack for other commands."""
    from omym2.platform.web_composition import build_web_app  # noqa: PLC0415  # Intentional settings-only import.

    return build_web_app(config_path, database_path)


def build_command_dependencies(
    config_path: Path | None = None,
    database_path: Path | None = None,
) -> CommandDependencies:
    """Build the full per-command dependency bundle for one CLI invocation.

    Every eagerly built field runs on each invocation before command dispatch,
    so it must stay side-effect-free at construction (no I/O, no optional
    imports); anything heavier belongs behind one of the factory fields.
    """
    runtime = runtime_context_for(config_path, database_path)
    return CommandDependencies(
        add=AddCommandDependencies(
            create_add_plan_ports_factory=lambda: build_create_add_plan_ports(runtime),
            apply_plan_ports_factory=lambda: build_apply_plan_ports(runtime),
            normalize_source_path=normalize_cli_path,
        ),
        apply=ApplyCommandDependencies(
            uow_factory=lambda: build_uow(runtime),
            apply_plan_ports_factory=lambda: build_apply_plan_ports(runtime),
        ),
        artist_ids=artist_ids_command_ports_for(runtime),
        check=build_check_library_ports(runtime),
        config=build_settings_ports(runtime),
        history=build_history_ports(runtime),
        inspect=build_inspect_file_ports(runtime),
        organize=OrganizeCommandDependencies(
            create_organize_plan_ports_factory=lambda: build_create_organize_plan_ports(runtime),
            apply_plan_ports_factory=lambda: build_apply_plan_ports(runtime),
            normalize_library_root=normalize_cli_path,
        ),
        plans=build_plan_query_ports(runtime),
        refresh=RefreshCommandDependencies(
            create_refresh_plan_ports_factory=lambda: build_create_refresh_plan_ports(runtime),
            apply_plan_ports_factory=lambda: build_apply_plan_ports(runtime),
            normalize_target_path=normalize_cli_path,
        ),
        settings=SettingsCommandPorts(
            web_app_factory=lambda: _build_web_app(runtime.config_file, runtime.database_file)
        ),
        undo=UndoCommandDependencies(
            create_undo_plan_ports_factory=lambda: build_create_undo_plan_ports(runtime),
            apply_plan_ports_factory=lambda: build_apply_plan_ports(runtime),
        ),
    )
