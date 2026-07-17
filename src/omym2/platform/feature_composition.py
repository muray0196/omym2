"""
Summary: Builds feature ports dataclasses from a shared RuntimeContext.
Why: Centralizes concrete adapter wiring so CLI and Web command modules stop duplicating it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from omym2.adapters.config.application_paths import ApplicationPaths
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.adapters.fs.configured_hash_calculator import ConfiguredFileContentHasher
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
from omym2.features.check.ports import CheckLibraryPorts, CheckQueryPorts
from omym2.features.common_ports import SystemClock, Uuid7IdGenerator
from omym2.features.history.ports import HistoryPorts
from omym2.features.inspect.ports import InspectFilePorts
from omym2.features.libraries.ports import LibraryInspectionPorts
from omym2.features.organize.ports import CreateOrganizePlanPorts
from omym2.features.plans.ports import PlanQueryPorts
from omym2.features.refresh.ports import CreateRefreshPlanPorts
from omym2.features.settings.ports import SettingsPorts
from omym2.features.tracks.ports import TracksPorts
from omym2.features.undo.ports import CreateUndoPlanPorts
from omym2.platform.artist_name_composition import artist_name_resolver_for
from omym2.platform.logging_composition import resolve_log_file

if TYPE_CHECKING:
    from omym2.domain.models.app_config import AppConfig
    from omym2.features.common_ports import ArtistNameResolutionReader, FileSystemPath
    from omym2.platform.runtime_context import RuntimeContext

SQLITE_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")


def _file_content_hasher(config: AppConfig) -> FileContentHasher:
    return FileContentHasher(chunk_size_bytes=config.hashing.read_chunk_size_bytes)


def _file_snapshot_reader(runtime: RuntimeContext, config: AppConfig) -> FilesystemFileSnapshotReader:
    return FilesystemFileSnapshotReader(
        metadata_reader=runtime.metadata_reader,
        hasher=_file_content_hasher(config),
    )


def _cached_artist_name_resolver(runtime: RuntimeContext) -> ArtistNameResolutionReader:
    """Build a mapping-only resolver that never starts automatic provider work."""
    config = runtime.config_store.read_snapshot().config
    return artist_name_resolver_for(
        runtime.database_file,
        runtime.artist_name_runtime.provider_for(config.musicbrainz),
        automatic_lookup_enabled=False,
    )


def _add_internal_excluded_paths(runtime: RuntimeContext, config: AppConfig) -> tuple[FileSystemPath, ...]:
    """Return only OMYM2-owned config, data, and log entries for Add inventory pruning."""
    application_paths = ApplicationPaths(runtime.application_root)
    log_file = resolve_log_file(
        runtime.application_root,
        application_paths.desktop_log_file,
        config.logging,
    )
    candidates = (
        application_paths.config_dir,
        application_paths.data_dir,
        runtime.config_file,
        runtime.database_file,
        *(
            runtime.database_file.with_name(f"{runtime.database_file.name}{suffix}")
            for suffix in SQLITE_SIDECAR_SUFFIXES
        ),
        log_file,
    )
    return tuple(dict.fromkeys(candidates))


def _add_rotating_log_files(runtime: RuntimeContext, config: AppConfig) -> tuple[FileSystemPath, ...]:
    """Return log bases whose numeric rotation siblings are also OMYM2-owned."""
    application_paths = ApplicationPaths(runtime.application_root)
    return (
        resolve_log_file(
            runtime.application_root,
            application_paths.desktop_log_file,
            config.logging,
        ),
    )


def build_uow(runtime: RuntimeContext) -> SQLiteUnitOfWork:
    """Build a bare UnitOfWork over the shared database file."""
    return SQLiteUnitOfWork(runtime.database_file)


def build_create_add_plan_ports(runtime: RuntimeContext) -> CreateAddPlanPorts:
    """Build ports for add plan creation."""
    config = runtime.config_store.load()
    clock = SystemClock()
    return CreateAddPlanPorts(
        uow=SQLiteUnitOfWork(runtime.database_file),
        file_scanner=FilesystemFileScanner(),
        file_snapshot_reader=_file_snapshot_reader(runtime, config),
        file_content_snapshot_reader=FilesystemFileContentSnapshotReader(
            clock=clock,
            hasher=_file_content_hasher(config),
        ),
        source_inventory_reader=FilesystemSourceInventoryReader(),
        file_presence=FilesystemFilePresence(),
        config_store=runtime.config_store,
        artist_name_resolver=artist_name_resolver_for(
            runtime.database_file,
            runtime.artist_name_runtime.provider_for(config.musicbrainz),
            automatic_lookup_enabled=config.musicbrainz.enabled,
        ),
        path_resolver=FilesystemPathResolver(),
        clock=clock,
        id_generator=Uuid7IdGenerator(),
        internal_excluded_paths=_add_internal_excluded_paths(runtime, config),
        rotating_log_files=_add_rotating_log_files(runtime, config),
    )


def build_apply_plan_ports(runtime: RuntimeContext) -> ApplyPlanPorts:
    """Build ports for apply execution."""
    config = runtime.config_store.load()
    clock = SystemClock()
    return ApplyPlanPorts(
        uow=SQLiteUnitOfWork(runtime.database_file),
        file_mover=FilesystemFileMover(content_hasher=_file_content_hasher(config)),
        file_snapshot_reader=_file_snapshot_reader(runtime, config),
        file_content_snapshot_reader=FilesystemFileContentSnapshotReader(
            clock=clock,
            hasher=_file_content_hasher(config),
        ),
        path_resolver=FilesystemPathResolver(),
        clock=clock,
        id_generator=Uuid7IdGenerator(),
    )


def build_check_library_ports(runtime: RuntimeContext) -> CheckLibraryPorts:
    """Build ports for check inspection and persistence."""
    config = runtime.config_store.load()
    content_hasher = _file_content_hasher(config)
    return CheckLibraryPorts(
        uow=SQLiteUnitOfWork(runtime.database_file),
        file_scanner=FilesystemFileScanner(),
        file_snapshot_reader=FilesystemFileSnapshotReader(
            metadata_reader=runtime.metadata_reader,
            hasher=content_hasher,
        ),
        file_content_snapshot_reader=FilesystemFileContentSnapshotReader(
            clock=SystemClock(),
            hasher=content_hasher,
        ),
        source_inventory_reader=FilesystemSourceInventoryReader(),
        file_content_hasher=content_hasher,
        config_store=runtime.config_store,
        path_resolver=FilesystemPathResolver(),
        clock=SystemClock(),
        id_generator=Uuid7IdGenerator(),
    )


def build_check_query_ports(runtime: RuntimeContext) -> CheckQueryPorts:
    """Build ports for read-only browsing of persisted check findings, without filesystem ports."""
    return CheckQueryPorts(uow=SQLiteUnitOfWork(runtime.database_file))


def build_history_ports(runtime: RuntimeContext) -> HistoryPorts:
    """Build ports for history queries."""
    return HistoryPorts(uow=SQLiteUnitOfWork(runtime.database_file))


def build_library_inspection_ports(runtime: RuntimeContext) -> LibraryInspectionPorts:
    """Build ports for read-only effective Library readiness inspection."""
    return LibraryInspectionPorts(
        uow=SQLiteUnitOfWork(runtime.database_file),
        config_snapshot_reader=runtime.config_store,
    )


def build_inspect_file_ports(runtime: RuntimeContext) -> InspectFilePorts:
    """Build ports for single-file inspection."""
    return InspectFilePorts(
        file_snapshot_reader=FilesystemFileSnapshotReader(
            metadata_reader=runtime.metadata_reader,
            hasher=ConfiguredFileContentHasher(runtime.config_store),
        ),
        config_store=runtime.config_store,
        artist_name_resolver=_cached_artist_name_resolver(runtime),
    )


def build_create_organize_plan_ports(runtime: RuntimeContext) -> CreateOrganizePlanPorts:
    """Build ports for organize planning."""
    config = runtime.config_store.load()
    clock = SystemClock()
    return CreateOrganizePlanPorts(
        uow=SQLiteUnitOfWork(runtime.database_file),
        file_scanner=FilesystemFileScanner(),
        file_snapshot_reader=_file_snapshot_reader(runtime, config),
        file_content_snapshot_reader=FilesystemFileContentSnapshotReader(
            clock=clock,
            hasher=_file_content_hasher(config),
        ),
        source_inventory_reader=FilesystemSourceInventoryReader(),
        file_presence=FilesystemFilePresence(),
        config_store=runtime.config_store,
        artist_name_resolver=artist_name_resolver_for(
            runtime.database_file,
            runtime.artist_name_runtime.provider_for(config.musicbrainz),
            automatic_lookup_enabled=config.musicbrainz.enabled,
        ),
        path_resolver=FilesystemPathResolver(),
        clock=clock,
        id_generator=Uuid7IdGenerator(),
    )


def build_plan_query_ports(runtime: RuntimeContext) -> PlanQueryPorts:
    """Build ports for querying reviewed Plans."""
    return PlanQueryPorts(uow=SQLiteUnitOfWork(runtime.database_file))


def build_create_refresh_plan_ports(runtime: RuntimeContext) -> CreateRefreshPlanPorts:
    """Build ports for refresh planning."""
    config = runtime.config_store.load()
    clock = SystemClock()
    return CreateRefreshPlanPorts(
        uow=SQLiteUnitOfWork(runtime.database_file),
        file_snapshot_reader=_file_snapshot_reader(runtime, config),
        file_content_snapshot_reader=FilesystemFileContentSnapshotReader(
            clock=clock,
            hasher=_file_content_hasher(config),
        ),
        source_inventory_reader=FilesystemSourceInventoryReader(),
        file_stat_reader=FilesystemFileScanner(),
        file_presence=FilesystemFilePresence(),
        config_store=runtime.config_store,
        artist_name_resolver=artist_name_resolver_for(
            runtime.database_file,
            runtime.artist_name_runtime.provider_for(config.musicbrainz),
            automatic_lookup_enabled=config.musicbrainz.enabled,
        ),
        path_resolver=FilesystemPathResolver(),
        clock=clock,
        id_generator=Uuid7IdGenerator(),
    )


def build_settings_ports(runtime: RuntimeContext) -> SettingsPorts:
    """Build ports for settings usecases."""
    return SettingsPorts(
        config_store=runtime.config_store,
        artist_name_resolver=_cached_artist_name_resolver(runtime),
    )


def build_tracks_ports(runtime: RuntimeContext) -> TracksPorts:
    """Build ports for read-only Track inspection, matching adapters/web/app.py."""
    return TracksPorts(uow=SQLiteUnitOfWork(runtime.database_file))


def build_create_undo_plan_ports(runtime: RuntimeContext) -> CreateUndoPlanPorts:
    """Build ports for undo planning (no config_store)."""
    config = runtime.config_store.load()
    clock = SystemClock()
    return CreateUndoPlanPorts(
        uow=SQLiteUnitOfWork(runtime.database_file),
        file_snapshot_reader=_file_snapshot_reader(runtime, config),
        file_content_snapshot_reader=FilesystemFileContentSnapshotReader(
            clock=clock,
            hasher=_file_content_hasher(config),
        ),
        file_presence=FilesystemFilePresence(),
        path_resolver=FilesystemPathResolver(),
        clock=clock,
        id_generator=Uuid7IdGenerator(),
    )
