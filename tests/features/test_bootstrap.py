"""
Summary: Tests read-only Bootstrap readiness selection.
Why: Keeps Config and Library degradation rules backend-authoritative.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from omym2.adapters.config.default_config import default_app_config
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.services.config_fingerprint import calculate_path_policy_fingerprint
from omym2.features.bootstrap.dto import BootstrapReason
from omym2.features.bootstrap.ports import BootstrapPorts, LibrarySnapshotUnavailableError
from omym2.features.bootstrap.usecases.get_bootstrap import GetBootstrapUseCase
from omym2.features.common_ports import ConfigSnapshot, ConfigSnapshotState
from omym2.shared.ids import LibraryId, OperationId

if TYPE_CHECKING:
    from collections.abc import Sequence

    from omym2.domain.models.app_config import AppConfig

NOW = datetime(2026, 7, 13, tzinfo=UTC)
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345670"))
SECOND_LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345671"))


@dataclass(frozen=True, slots=True)
class StaticConfigSnapshotReader:
    """Return one deterministic Config snapshot."""

    snapshot: ConfigSnapshot

    def read_snapshot(self) -> ConfigSnapshot:
        return self.snapshot


@dataclass(frozen=True, slots=True)
class StaticLibrarySnapshotReader:
    """Return deterministic persisted Libraries or a storage failure."""

    libraries: Sequence[Library] = ()
    unavailable: bool = False
    operation_id: OperationId | None = None

    def list_libraries(self) -> Sequence[Library]:
        if self.unavailable:
            raise LibrarySnapshotUnavailableError
        return self.libraries

    def active_operation_id(self) -> OperationId | None:
        if self.unavailable:
            raise LibrarySnapshotUnavailableError
        return self.operation_id


def test_bootstrap_selects_one_current_registered_library() -> None:
    """One registered Library with the effective PathPolicy is ready."""
    config = default_app_config()
    path_policy_hash = calculate_path_policy_fingerprint(
        config.path_policy,
        config.artist_ids,
        config.metadata.album_year_resolution,
    )
    result = _execute(_snapshot(config), (_library(LIBRARY_ID, path_policy_hash),))

    assert result.active_library is not None
    assert result.active_library.library_id == LIBRARY_ID
    assert result.is_path_policy_current is True
    assert result.effective_library_status is LibraryStatus.REGISTERED
    assert result.is_library_registered is True
    assert result.library_reasons == ()
    assert result.config_reason is None
    assert result.config_valid is True
    assert result.runtime_capabilities.can_start_operations is True
    assert result.runtime_capabilities.start_operations_disabled_reasons == ()


def test_bootstrap_reports_missing_library_without_invalidating_default_config() -> None:
    """A missing Config uses valid defaults while missing Library remains explicit."""
    result = _execute(_snapshot(default_app_config(), state=ConfigSnapshotState.MISSING), ())

    assert result.config_reason is None
    assert result.config_valid is True
    assert result.active_library is None
    assert result.library_reasons == (BootstrapReason.LIBRARY_UNREGISTERED,)
    assert result.runtime_capabilities.can_start_operations is False
    assert result.runtime_capabilities.start_operations_disabled_reasons == (BootstrapReason.LIBRARY_UNREGISTERED,)


def test_bootstrap_reports_invalid_config_and_stale_library() -> None:
    """Invalid raw Config remains recoverable and cannot make a Library current."""
    result = _execute(
        _snapshot(default_app_config(), state=ConfigSnapshotState.INVALID, errors=("Invalid TOML",)),
        (_library(LIBRARY_ID, "old-fingerprint"),),
    )

    assert result.config_reason is BootstrapReason.CONFIG_INVALID
    assert result.active_library is not None
    assert result.is_path_policy_current is False
    assert result.effective_library_status is LibraryStatus.STALE
    assert result.library_reasons == (BootstrapReason.LIBRARY_STALE,)
    assert result.config_valid is False
    assert result.runtime_capabilities.start_operations_disabled_reasons == (
        BootstrapReason.CONFIG_INVALID,
        BootstrapReason.LIBRARY_STALE,
    )


def test_bootstrap_does_not_guess_between_multiple_libraries() -> None:
    """Multiple persisted Libraries leave active selection empty."""
    config = default_app_config()
    result = _execute(
        _snapshot(config),
        (_library(LIBRARY_ID, "hash"), _library(SECOND_LIBRARY_ID, "hash")),
    )

    assert result.active_library is None
    assert result.library_reasons == (BootstrapReason.LIBRARY_SELECTION_AMBIGUOUS,)


def test_bootstrap_preserves_config_recovery_when_state_storage_is_unavailable() -> None:
    """SQLite failure does not discard the independently read Config snapshot."""
    snapshot = _snapshot(default_app_config())
    ports = BootstrapPorts(
        snapshot_reader := StaticConfigSnapshotReader(snapshot),
        state_reader := StaticLibrarySnapshotReader(unavailable=True),
        state_reader,
    )

    result = GetBootstrapUseCase(ports).execute()

    assert snapshot_reader.read_snapshot() is snapshot
    assert result.config_snapshot is snapshot
    assert result.state_storage_available is False
    assert result.library_reasons == (BootstrapReason.STORAGE_UNAVAILABLE,)
    assert result.runtime_capabilities.can_read_state is False
    assert result.runtime_capabilities.read_state_disabled_reasons == (BootstrapReason.STORAGE_UNAVAILABLE,)


def _execute(snapshot: ConfigSnapshot, libraries: Sequence[Library]):
    state_reader = StaticLibrarySnapshotReader(libraries)
    return GetBootstrapUseCase(
        BootstrapPorts(StaticConfigSnapshotReader(snapshot), state_reader, state_reader)
    ).execute()


def _snapshot(
    config: AppConfig,
    *,
    state: ConfigSnapshotState = ConfigSnapshotState.VALID,
    errors: tuple[str, ...] = (),
) -> ConfigSnapshot:
    return ConfigSnapshot(state=state, config=config, config_revision="v1:test", errors=errors)


def _library(library_id: LibraryId, path_policy_hash: str) -> Library:
    return Library(
        library_id=library_id,
        root_path="/music",
        path_policy_hash=path_policy_hash,
        registered_at=NOW,
        status=LibraryStatus.REGISTERED,
        created_at=NOW,
        updated_at=NOW,
    )
