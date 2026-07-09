"""
Summary: Builds feature ports dataclasses from a shared RuntimeContext.
Why: Centralizes concrete adapter wiring so CLI and Web command modules stop duplicating it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.adapters.fs.file_mover import FilesystemFileMover
from omym2.adapters.fs.file_presence import FilesystemFilePresence
from omym2.adapters.fs.file_scanner import FilesystemFileScanner
from omym2.adapters.fs.file_snapshot_reader import FilesystemFileSnapshotReader
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

if TYPE_CHECKING:
    from omym2.platform.runtime_context import RuntimeContext


def build_uow(runtime: RuntimeContext) -> SQLiteUnitOfWork:
    """Build a bare UnitOfWork over the shared database file."""
    return SQLiteUnitOfWork(runtime.database_file)


def build_create_add_plan_ports(runtime: RuntimeContext) -> CreateAddPlanPorts:
    """Build ports for add plan creation."""
    return CreateAddPlanPorts(
        uow=SQLiteUnitOfWork(runtime.database_file),
        file_scanner=FilesystemFileScanner(),
        file_snapshot_reader=FilesystemFileSnapshotReader(metadata_reader=runtime.metadata_reader),
        file_presence=FilesystemFilePresence(),
        config_store=runtime.config_store,
        path_resolver=FilesystemPathResolver(),
        clock=SystemClock(),
        id_generator=Uuid7IdGenerator(),
    )


def build_apply_plan_ports(runtime: RuntimeContext) -> ApplyPlanPorts:
    """Build ports for apply execution."""
    return ApplyPlanPorts(
        uow=SQLiteUnitOfWork(runtime.database_file),
        file_mover=FilesystemFileMover(),
        file_snapshot_reader=FilesystemFileSnapshotReader(metadata_reader=runtime.metadata_reader),
        path_resolver=FilesystemPathResolver(),
        clock=SystemClock(),
        id_generator=Uuid7IdGenerator(),
    )


def build_check_library_ports(runtime: RuntimeContext) -> CheckLibraryPorts:
    """Build ports for check inspection and persistence."""
    return CheckLibraryPorts(
        uow=SQLiteUnitOfWork(runtime.database_file),
        file_scanner=FilesystemFileScanner(),
        file_snapshot_reader=FilesystemFileSnapshotReader(metadata_reader=runtime.metadata_reader),
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


def build_inspect_file_ports(runtime: RuntimeContext) -> InspectFilePorts:
    """Build ports for single-file inspection."""
    return InspectFilePorts(
        file_snapshot_reader=FilesystemFileSnapshotReader(metadata_reader=runtime.metadata_reader),
        config_store=runtime.config_store,
    )


def build_create_organize_plan_ports(runtime: RuntimeContext) -> CreateOrganizePlanPorts:
    """Build ports for organize planning."""
    return CreateOrganizePlanPorts(
        uow=SQLiteUnitOfWork(runtime.database_file),
        file_scanner=FilesystemFileScanner(),
        file_snapshot_reader=FilesystemFileSnapshotReader(metadata_reader=runtime.metadata_reader),
        config_store=runtime.config_store,
        path_resolver=FilesystemPathResolver(),
        clock=SystemClock(),
        id_generator=Uuid7IdGenerator(),
    )


def build_plan_query_ports(runtime: RuntimeContext) -> PlanQueryPorts:
    """Build ports for querying reviewed Plans."""
    return PlanQueryPorts(uow=SQLiteUnitOfWork(runtime.database_file))


def build_create_refresh_plan_ports(runtime: RuntimeContext) -> CreateRefreshPlanPorts:
    """Build ports for refresh planning."""
    return CreateRefreshPlanPorts(
        uow=SQLiteUnitOfWork(runtime.database_file),
        file_snapshot_reader=FilesystemFileSnapshotReader(metadata_reader=runtime.metadata_reader),
        file_presence=FilesystemFilePresence(),
        config_store=runtime.config_store,
        path_resolver=FilesystemPathResolver(),
        clock=SystemClock(),
        id_generator=Uuid7IdGenerator(),
    )


def build_settings_ports(runtime: RuntimeContext) -> SettingsPorts:
    """Build ports for settings usecases."""
    return SettingsPorts(config_store=runtime.config_store)


def build_tracks_ports(runtime: RuntimeContext) -> TracksPorts:
    """Build ports for read-only Track inspection, matching adapters/web/app.py."""
    return TracksPorts(uow=SQLiteUnitOfWork(runtime.database_file))


def build_create_undo_plan_ports(runtime: RuntimeContext) -> CreateUndoPlanPorts:
    """Build ports for undo planning (no config_store)."""
    return CreateUndoPlanPorts(
        uow=SQLiteUnitOfWork(runtime.database_file),
        file_snapshot_reader=FilesystemFileSnapshotReader(metadata_reader=runtime.metadata_reader),
        file_presence=FilesystemFilePresence(),
        path_resolver=FilesystemPathResolver(),
        clock=SystemClock(),
        id_generator=Uuid7IdGenerator(),
    )
