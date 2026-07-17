"""
Summary: Tests feature ports builders against today's CLI/Web wiring recipes.
Why: Guards platform composition from silently drifting away from adapters/cli/commands/*.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

import pytest

from omym2.adapters.artist_ids.musicbrainz_artist_lookup import MusicBrainzArtistLookup
from omym2.adapters.config.application_paths import ApplicationPaths
from omym2.adapters.config.default_config import default_app_config
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.adapters.fs.file_content_snapshot_reader import FilesystemFileContentSnapshotReader
from omym2.adapters.fs.file_mover import FilesystemFileMover
from omym2.adapters.fs.file_presence import FilesystemFilePresence
from omym2.adapters.fs.file_scanner import FilesystemFileScanner
from omym2.adapters.fs.file_snapshot_reader import FilesystemFileSnapshotReader
from omym2.adapters.fs.hash_calculator import FileContentHasher
from omym2.adapters.fs.path_resolver import FilesystemPathResolver
from omym2.adapters.fs.source_inventory_reader import FilesystemSourceInventoryReader
from omym2.features.add.ports import CreateAddPlanPorts
from omym2.features.apply.ports import ApplyPlanPorts
from omym2.features.artist_names.usecases.resolve_artist_names import ResolveArtistNamesUseCase
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

    from omym2.adapters.fs.configured_hash_calculator import ConfiguredFileContentHasher
    from omym2.domain.models.app_config import AppConfig
    from omym2.platform.runtime_context import RuntimeContext

CONFIGURED_RETRY_LIMIT = 3
EXTREME_LOG_RETENTION_FILES = 10**100
EXPECTED_ADD_INTERNAL_EXCLUDED_PATH_COUNT = 8


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
    assert isinstance(ports.file_content_snapshot_reader, FilesystemFileContentSnapshotReader)
    assert ports.file_content_snapshot_reader.clock is ports.clock
    assert isinstance(ports.file_content_snapshot_reader, FilesystemFileContentSnapshotReader)
    assert ports.file_content_snapshot_reader.clock is ports.clock
    assert isinstance(ports.source_inventory_reader, FilesystemSourceInventoryReader)
    assert isinstance(ports.file_presence, FilesystemFilePresence)
    assert ports.config_store is runtime.config_store
    assert isinstance(ports.artist_name_resolver, ResolveArtistNamesUseCase)
    assert ports.artist_name_resolver.ports.automatic_lookup_enabled is True
    assert isinstance(ports.path_resolver, FilesystemPathResolver)
    assert isinstance(ports.clock, SystemClock)
    assert isinstance(ports.id_generator, Uuid7IdGenerator)
    application_paths = ApplicationPaths(runtime.application_root)
    log_file = application_paths.desktop_log_file
    assert set(ports.internal_excluded_paths) == {
        application_paths.config_dir,
        application_paths.data_dir,
        runtime.config_file,
        runtime.database_file,
        runtime.database_file.with_name(f"{runtime.database_file.name}-wal"),
        runtime.database_file.with_name(f"{runtime.database_file.name}-shm"),
        runtime.database_file.with_name(f"{runtime.database_file.name}-journal"),
        log_file,
    }
    assert ports.rotating_log_files == (log_file,)


def test_build_create_add_plan_ports_does_not_expand_extreme_log_retention(
    runtime: RuntimeContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Composition passes one rotation base regardless of the configured retention integer."""
    config = default_app_config()
    configured = replace(
        config,
        logging=replace(config.logging, retention_files=EXTREME_LOG_RETENTION_FILES),
    )

    def load_config(_store: object) -> AppConfig:
        return configured

    monkeypatch.setattr(type(runtime.config_store), "load", load_config)

    ports = build_create_add_plan_ports(runtime)

    assert len(ports.internal_excluded_paths) == EXPECTED_ADD_INTERNAL_EXCLUDED_PATH_COUNT
    assert ports.rotating_log_files == (ApplicationPaths(runtime.application_root).desktop_log_file,)


def test_build_apply_plan_ports_matches_shared_apply_recipe(runtime: RuntimeContext) -> None:
    """build_apply_plan_ports mirrors the byte-identical ApplyPlanPorts block in apply/add/organize/refresh/undo."""
    ports = build_apply_plan_ports(runtime)

    assert isinstance(ports, ApplyPlanPorts)
    assert isinstance(ports.uow, SQLiteUnitOfWork)
    assert ports.uow.database_path == runtime.database_file
    assert isinstance(ports.file_mover, FilesystemFileMover)
    assert isinstance(ports.file_snapshot_reader, FilesystemFileSnapshotReader)
    assert ports.file_snapshot_reader.metadata_reader is runtime.metadata_reader
    assert isinstance(ports.file_content_snapshot_reader, FilesystemFileContentSnapshotReader)
    assert ports.file_content_snapshot_reader.clock is ports.clock
    assert isinstance(ports.path_resolver, FilesystemPathResolver)
    assert isinstance(ports.clock, SystemClock)
    assert isinstance(ports.id_generator, Uuid7IdGenerator)
    assert not hasattr(ports, "artist_name_resolver")


def test_build_check_library_ports_matches_check_command_recipe(runtime: RuntimeContext) -> None:
    """build_check_library_ports mirrors check.py's CheckLibraryPorts construction."""
    ports = build_check_library_ports(runtime)

    assert isinstance(ports, CheckLibraryPorts)
    assert isinstance(ports.uow, SQLiteUnitOfWork)
    assert ports.uow.database_path == runtime.database_file
    assert isinstance(ports.file_scanner, FilesystemFileScanner)
    assert isinstance(ports.file_snapshot_reader, FilesystemFileSnapshotReader)
    assert ports.file_snapshot_reader.metadata_reader is runtime.metadata_reader
    assert isinstance(ports.file_content_snapshot_reader, FilesystemFileContentSnapshotReader)
    assert isinstance(ports.source_inventory_reader, FilesystemSourceInventoryReader)
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
    assert isinstance(ports.file_content_snapshot_reader, FilesystemFileContentSnapshotReader)
    assert ports.file_content_snapshot_reader.clock is ports.clock
    assert isinstance(ports.source_inventory_reader, FilesystemSourceInventoryReader)
    assert isinstance(ports.file_presence, FilesystemFilePresence)
    assert ports.config_store is runtime.config_store
    assert isinstance(ports.artist_name_resolver, ResolveArtistNamesUseCase)
    assert ports.artist_name_resolver.ports.automatic_lookup_enabled is True
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
    assert isinstance(ports.file_content_snapshot_reader, FilesystemFileContentSnapshotReader)
    assert ports.file_content_snapshot_reader.clock is ports.clock
    assert isinstance(ports.source_inventory_reader, FilesystemSourceInventoryReader)
    assert isinstance(ports.file_stat_reader, FilesystemFileScanner)
    assert isinstance(ports.file_presence, FilesystemFilePresence)
    assert ports.config_store is runtime.config_store
    assert isinstance(ports.artist_name_resolver, ResolveArtistNamesUseCase)
    assert ports.artist_name_resolver.ports.automatic_lookup_enabled is True
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


def test_plan_composition_reloads_and_reuses_persisted_naming_controls(runtime: RuntimeContext) -> None:
    """Saved settings affect the next Plan builder and reuse unchanged stateful adapters."""
    initial = runtime.config_store.read_snapshot()
    configured = replace(
        initial.config,
        musicbrainz=replace(
            initial.config.musicbrainz,
            enabled=True,
            application_name="Library Tool",
            contact="ops@example.test",
            timeout_seconds=2.5,
            retry_limit=CONFIGURED_RETRY_LIMIT,
            rate_limit_seconds=1.25,
        ),
    )
    _ = runtime.config_store.save(configured, expected_config_revision=initial.config_revision)

    first_resolver = cast(
        "ResolveArtistNamesUseCase",
        build_create_add_plan_ports(runtime).artist_name_resolver,
    )
    second_resolver = cast(
        "ResolveArtistNamesUseCase",
        build_create_organize_plan_ports(runtime).artist_name_resolver,
    )
    first = first_resolver.ports
    second = second_resolver.ports

    assert first.automatic_lookup_enabled is True
    assert isinstance(first.artist_name_provider, MusicBrainzArtistLookup)
    assert first.artist_name_provider is second.artist_name_provider
    assert first.artist_name_provider.user_agent == "Library Tool/0.1.0 (ops@example.test)"
    assert first.artist_name_provider.timeout_seconds == pytest.approx(2.5)
    assert first.artist_name_provider.retry_limit == CONFIGURED_RETRY_LIMIT
    assert first.artist_name_provider.rate_limit_seconds == pytest.approx(1.25)


def test_file_composition_uses_persisted_hash_chunk_size_for_every_snapshot_path(
    runtime: RuntimeContext,
) -> None:
    """Operational hash sizing applies consistently without changing the digest policy."""
    initial = runtime.config_store.read_snapshot()
    chunk_size = 17
    configured = replace(
        initial.config,
        hashing=replace(initial.config.hashing, read_chunk_size_bytes=chunk_size),
    )
    _ = runtime.config_store.save(configured, expected_config_revision=initial.config_revision)

    check_ports = build_check_library_ports(runtime)
    snapshot_readers = tuple(
        cast("FilesystemFileSnapshotReader", reader)
        for reader in (
            build_create_add_plan_ports(runtime).file_snapshot_reader,
            build_apply_plan_ports(runtime).file_snapshot_reader,
            check_ports.file_snapshot_reader,
            build_create_organize_plan_ports(runtime).file_snapshot_reader,
            build_create_refresh_plan_ports(runtime).file_snapshot_reader,
            build_create_undo_plan_ports(runtime).file_snapshot_reader,
        )
    )

    assert all(isinstance(reader.hasher, FileContentHasher) for reader in snapshot_readers)
    assert all(cast("FileContentHasher", reader.hasher).chunk_size_bytes == chunk_size for reader in snapshot_readers)
    content_snapshot_readers = (
        build_create_add_plan_ports(runtime).file_content_snapshot_reader,
        build_apply_plan_ports(runtime).file_content_snapshot_reader,
        check_ports.file_content_snapshot_reader,
        build_create_organize_plan_ports(runtime).file_content_snapshot_reader,
        build_create_refresh_plan_ports(runtime).file_content_snapshot_reader,
        build_create_undo_plan_ports(runtime).file_content_snapshot_reader,
    )
    assert all(isinstance(reader, FilesystemFileContentSnapshotReader) for reader in content_snapshot_readers)
    assert all(
        cast("FilesystemFileContentSnapshotReader", reader).hasher.chunk_size_bytes == chunk_size
        for reader in content_snapshot_readers
    )
    assert cast("FileContentHasher", check_ports.file_content_hasher).chunk_size_bytes == chunk_size
    apply_mover = cast("FilesystemFileMover", build_apply_plan_ports(runtime).file_mover)
    assert apply_mover.content_hasher.chunk_size_bytes == chunk_size
    inspect_reader = cast(
        "FilesystemFileSnapshotReader",
        build_inspect_file_ports(runtime).file_snapshot_reader,
    )
    inspect_hasher = cast("ConfiguredFileContentHasher", inspect_reader.hasher)
    assert inspect_hasher.chunk_size_bytes == chunk_size
