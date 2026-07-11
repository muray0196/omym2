"""
Summary: Tests feature ports builders against today's CLI/Web wiring recipes.
Why: Guards platform composition from silently drifting away from adapters/cli/commands/*.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.adapters.fs.file_mover import FilesystemFileMover
from omym2.adapters.fs.file_presence import FilesystemFilePresence
from omym2.adapters.fs.file_scanner import FilesystemFileScanner
from omym2.adapters.fs.file_snapshot_reader import FilesystemFileSnapshotReader
from omym2.adapters.fs.hash_calculator import FileContentHasher
from omym2.adapters.fs.path_resolver import FilesystemPathResolver
from omym2.features.add.ports import CreateAddPlanPorts
from omym2.features.apply.ports import ApplyPlanPorts
from omym2.features.check.ports import CheckLibraryPorts, CheckQueryPorts
from omym2.features.common_ports import SystemClock, Uuid7IdGenerator
from omym2.features.history.ports import HistoryPorts
from omym2.features.inspect.ports import InspectFilePorts
from omym2.features.organize.ports import CreateOrganizePlanPorts
from omym2.features.plans.ports import PlanQueryPorts
from omym2.features.refresh.ports import CreateRefreshPlanPorts
from omym2.features.settings.ports import SettingsPorts
from omym2.features.tracks.ports import TracksPorts
from omym2.features.undo.ports import CreateUndoPlanPorts
from omym2.platform.feature_composition import (
    build_apply_plan_ports,
    build_check_library_ports,
    build_check_query_ports,
    build_create_add_plan_ports,
    build_create_organize_plan_ports,
    build_create_refresh_plan_ports,
    build_create_undo_plan_ports,
    build_history_ports,
    build_inspect_file_ports,
    build_plan_query_ports,
    build_settings_ports,
    build_tracks_ports,
    build_uow,
)
from omym2.platform.runtime_context import runtime_context_for

if TYPE_CHECKING:
    from pathlib import Path

    from omym2.platform.runtime_context import RuntimeContext


@pytest.fixture
def runtime(tmp_path: Path) -> RuntimeContext:
    """Build a RuntimeContext over isolated tmp_path config/database locations."""
    return runtime_context_for(tmp_path / "config.toml", tmp_path / "omym2.sqlite3")


def test_build_uow_returns_bare_sqlite_unit_of_work(runtime: RuntimeContext) -> None:
    """build_uow mirrors apply.py's bare SQLiteUnitOfWork(database_path) construction."""
    uow = build_uow(runtime)

    assert isinstance(uow, SQLiteUnitOfWork)
    assert uow.database_path == runtime.database_file


def test_build_create_add_plan_ports_matches_add_command_recipe(runtime: RuntimeContext) -> None:
    """build_create_add_plan_ports mirrors add.py's CreateAddPlanPorts construction."""
    ports = build_create_add_plan_ports(runtime)

    assert isinstance(ports, CreateAddPlanPorts)
    assert isinstance(ports.uow, SQLiteUnitOfWork)
    assert ports.uow.database_path == runtime.database_file
    assert isinstance(ports.file_scanner, FilesystemFileScanner)
    assert isinstance(ports.file_snapshot_reader, FilesystemFileSnapshotReader)
    assert ports.file_snapshot_reader.metadata_reader is runtime.metadata_reader
    assert isinstance(ports.file_presence, FilesystemFilePresence)
    assert ports.config_store is runtime.config_store
    assert isinstance(ports.path_resolver, FilesystemPathResolver)
    assert isinstance(ports.clock, SystemClock)
    assert isinstance(ports.id_generator, Uuid7IdGenerator)


def test_build_apply_plan_ports_matches_shared_apply_recipe(runtime: RuntimeContext) -> None:
    """build_apply_plan_ports mirrors the byte-identical ApplyPlanPorts block in apply/add/organize/refresh/undo."""
    ports = build_apply_plan_ports(runtime)

    assert isinstance(ports, ApplyPlanPorts)
    assert isinstance(ports.uow, SQLiteUnitOfWork)
    assert ports.uow.database_path == runtime.database_file
    assert isinstance(ports.file_mover, FilesystemFileMover)
    assert isinstance(ports.file_snapshot_reader, FilesystemFileSnapshotReader)
    assert ports.file_snapshot_reader.metadata_reader is runtime.metadata_reader
    assert isinstance(ports.path_resolver, FilesystemPathResolver)
    assert isinstance(ports.clock, SystemClock)
    assert isinstance(ports.id_generator, Uuid7IdGenerator)


def test_build_check_library_ports_matches_check_command_recipe(runtime: RuntimeContext) -> None:
    """build_check_library_ports mirrors check.py's CheckLibraryPorts construction."""
    ports = build_check_library_ports(runtime)

    assert isinstance(ports, CheckLibraryPorts)
    assert isinstance(ports.uow, SQLiteUnitOfWork)
    assert ports.uow.database_path == runtime.database_file
    assert isinstance(ports.file_scanner, FilesystemFileScanner)
    assert isinstance(ports.file_snapshot_reader, FilesystemFileSnapshotReader)
    assert ports.file_snapshot_reader.metadata_reader is runtime.metadata_reader
    assert isinstance(ports.file_content_hasher, FileContentHasher)
    assert ports.config_store is runtime.config_store
    assert isinstance(ports.path_resolver, FilesystemPathResolver)
    assert isinstance(ports.clock, SystemClock)
    assert isinstance(ports.id_generator, Uuid7IdGenerator)


def test_build_check_query_ports_matches_web_app_check_factory(runtime: RuntimeContext) -> None:
    """build_check_query_ports mirrors the lean, filesystem-free read-side check ports factory."""
    ports = build_check_query_ports(runtime)

    assert isinstance(ports, CheckQueryPorts)
    assert isinstance(ports.uow, SQLiteUnitOfWork)
    assert ports.uow.database_path == runtime.database_file


def test_build_history_ports_matches_history_command_recipe(runtime: RuntimeContext) -> None:
    """build_history_ports mirrors history.py's bare HistoryPorts(uow=...) construction."""
    ports = build_history_ports(runtime)

    assert isinstance(ports, HistoryPorts)
    assert isinstance(ports.uow, SQLiteUnitOfWork)
    assert ports.uow.database_path == runtime.database_file


def test_build_inspect_file_ports_matches_inspect_command_recipe(runtime: RuntimeContext) -> None:
    """build_inspect_file_ports mirrors inspect.py's InspectFilePorts construction."""
    ports = build_inspect_file_ports(runtime)

    assert isinstance(ports, InspectFilePorts)
    assert isinstance(ports.file_snapshot_reader, FilesystemFileSnapshotReader)
    assert ports.file_snapshot_reader.metadata_reader is runtime.metadata_reader
    assert ports.config_store is runtime.config_store


def test_build_create_organize_plan_ports_matches_organize_command_recipe(runtime: RuntimeContext) -> None:
    """build_create_organize_plan_ports mirrors organize.py's CreateOrganizePlanPorts construction."""
    ports = build_create_organize_plan_ports(runtime)

    assert isinstance(ports, CreateOrganizePlanPorts)
    assert isinstance(ports.uow, SQLiteUnitOfWork)
    assert ports.uow.database_path == runtime.database_file
    assert isinstance(ports.file_scanner, FilesystemFileScanner)
    assert isinstance(ports.file_snapshot_reader, FilesystemFileSnapshotReader)
    assert ports.file_snapshot_reader.metadata_reader is runtime.metadata_reader
    assert ports.config_store is runtime.config_store
    assert isinstance(ports.path_resolver, FilesystemPathResolver)
    assert isinstance(ports.clock, SystemClock)
    assert isinstance(ports.id_generator, Uuid7IdGenerator)


def test_build_plan_query_ports_matches_plans_command_recipe(runtime: RuntimeContext) -> None:
    """build_plan_query_ports mirrors plans.py's bare PlanQueryPorts(uow=...) construction."""
    ports = build_plan_query_ports(runtime)

    assert isinstance(ports, PlanQueryPorts)
    assert isinstance(ports.uow, SQLiteUnitOfWork)
    assert ports.uow.database_path == runtime.database_file


def test_build_create_refresh_plan_ports_matches_refresh_command_recipe(runtime: RuntimeContext) -> None:
    """build_create_refresh_plan_ports mirrors refresh.py's CreateRefreshPlanPorts construction."""
    ports = build_create_refresh_plan_ports(runtime)

    assert isinstance(ports, CreateRefreshPlanPorts)
    assert isinstance(ports.uow, SQLiteUnitOfWork)
    assert ports.uow.database_path == runtime.database_file
    assert isinstance(ports.file_snapshot_reader, FilesystemFileSnapshotReader)
    assert ports.file_snapshot_reader.metadata_reader is runtime.metadata_reader
    assert isinstance(ports.file_stat_reader, FilesystemFileScanner)
    assert isinstance(ports.file_presence, FilesystemFilePresence)
    assert ports.config_store is runtime.config_store
    assert isinstance(ports.path_resolver, FilesystemPathResolver)
    assert isinstance(ports.clock, SystemClock)
    assert isinstance(ports.id_generator, Uuid7IdGenerator)


def test_build_settings_ports_matches_config_command_recipe(runtime: RuntimeContext) -> None:
    """build_settings_ports mirrors config.py's SettingsPorts(config_store=store) construction."""
    ports = build_settings_ports(runtime)

    assert isinstance(ports, SettingsPorts)
    assert ports.config_store is runtime.config_store


def test_build_tracks_ports_matches_web_app_tracks_factory(runtime: RuntimeContext) -> None:
    """build_tracks_ports mirrors adapters/web/app.py's TracksPorts(uow=...) factory."""
    ports = build_tracks_ports(runtime)

    assert isinstance(ports, TracksPorts)
    assert isinstance(ports.uow, SQLiteUnitOfWork)
    assert ports.uow.database_path == runtime.database_file


def test_build_create_undo_plan_ports_matches_undo_command_recipe(runtime: RuntimeContext) -> None:
    """build_create_undo_plan_ports mirrors undo.py's CreateUndoPlanPorts construction, with no config_store."""
    ports = build_create_undo_plan_ports(runtime)

    assert isinstance(ports, CreateUndoPlanPorts)
    assert isinstance(ports.uow, SQLiteUnitOfWork)
    assert ports.uow.database_path == runtime.database_file
    assert isinstance(ports.file_snapshot_reader, FilesystemFileSnapshotReader)
    assert ports.file_snapshot_reader.metadata_reader is runtime.metadata_reader
    assert isinstance(ports.file_presence, FilesystemFilePresence)
    assert isinstance(ports.path_resolver, FilesystemPathResolver)
    assert isinstance(ports.clock, SystemClock)
    assert isinstance(ports.id_generator, Uuid7IdGenerator)
    assert not hasattr(ports, "config_store")
