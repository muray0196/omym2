"""
Summary: Computes application Bootstrap readiness.
Why: Gives the Web shell backend-authoritative Config and Library state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.domain.models.library import LibraryStatus
from omym2.domain.services.config_fingerprint import calculate_path_policy_fingerprint
from omym2.features.bootstrap.dto import BootstrapCapabilities, BootstrapReason, BootstrapResult
from omym2.features.bootstrap.ports import BootstrapPorts, LibrarySnapshotUnavailableError
from omym2.features.common_ports import ConfigSnapshotState

if TYPE_CHECKING:
    from omym2.domain.models.library import Library
    from omym2.features.common_ports import ConfigSnapshot


@dataclass(frozen=True, slots=True)
class GetBootstrapUseCase:
    """Read Config and Library state without mutating either store."""

    ports: BootstrapPorts

    def execute(self) -> BootstrapResult:
        """Return one degraded-capable readiness snapshot."""
        try:
            config_snapshot = self.ports.config_snapshot_reader.read_snapshot()
        except OSError:
            config_snapshot = None

        try:
            libraries = tuple(self.ports.library_snapshot_reader.list_libraries())
        except LibrarySnapshotUnavailableError:
            return _result(
                config_snapshot,
                None,
                path_policy_current=False,
                library_reasons=(BootstrapReason.STORAGE_UNAVAILABLE,),
                state_storage_available=False,
            )

        active_library, selection_reason = _select_library(libraries)
        path_policy_current = _is_path_policy_current(config_snapshot, active_library)
        library_reasons = _library_reasons(
            active_library,
            selection_reason,
            path_policy_current=path_policy_current,
        )
        return _result(
            config_snapshot,
            active_library,
            path_policy_current=path_policy_current,
            library_reasons=library_reasons,
            state_storage_available=True,
        )


def _result(
    config_snapshot: ConfigSnapshot | None,
    active_library: Library | None,
    *,
    path_policy_current: bool,
    library_reasons: tuple[BootstrapReason, ...],
    state_storage_available: bool,
) -> BootstrapResult:
    config_reason = _config_reason(config_snapshot)
    config_valid = config_snapshot is not None and config_snapshot.state is not ConfigSnapshotState.INVALID
    return BootstrapResult(
        config_snapshot=config_snapshot,
        config_valid=config_valid,
        active_library=active_library,
        effective_library_status=_effective_library_status(active_library, path_policy_current=path_policy_current),
        is_library_registered=active_library is not None and active_library.registered_at is not None,
        is_path_policy_current=path_policy_current,
        config_reason=config_reason,
        library_reasons=library_reasons,
        state_storage_available=state_storage_available,
        runtime_capabilities=_runtime_capabilities(
            config_snapshot,
            config_reason=config_reason,
            library_reasons=library_reasons,
            state_storage_available=state_storage_available,
        ),
    )


def _effective_library_status(
    library: Library | None,
    *,
    path_policy_current: bool,
) -> LibraryStatus | None:
    if library is None:
        return None
    if library.status is LibraryStatus.REGISTERED and not path_policy_current:
        return LibraryStatus.STALE
    return library.status


def _runtime_capabilities(
    config_snapshot: ConfigSnapshot | None,
    *,
    config_reason: BootstrapReason | None,
    library_reasons: tuple[BootstrapReason, ...],
    state_storage_available: bool,
) -> BootstrapCapabilities:
    read_reasons = () if state_storage_available else (BootstrapReason.STORAGE_UNAVAILABLE,)
    change_reasons = () if config_snapshot is not None else (BootstrapReason.CONFIG_IO_FAILED,)
    start_reasons = (() if config_reason is None else (config_reason,)) + library_reasons
    return BootstrapCapabilities(
        can_read_state=not read_reasons,
        can_change_settings=not change_reasons,
        can_start_operations=not start_reasons,
        read_state_disabled_reasons=read_reasons,
        change_settings_disabled_reasons=change_reasons,
        start_operations_disabled_reasons=start_reasons,
    )


def _config_reason(config_snapshot: ConfigSnapshot | None) -> BootstrapReason | None:
    if config_snapshot is None:
        return BootstrapReason.CONFIG_IO_FAILED
    if config_snapshot.state is ConfigSnapshotState.INVALID:
        return BootstrapReason.CONFIG_INVALID
    return None


def _select_library(
    libraries: tuple[Library, ...],
) -> tuple[Library | None, BootstrapReason | None]:
    if not libraries:
        return None, BootstrapReason.LIBRARY_UNREGISTERED
    if len(libraries) > 1:
        return None, BootstrapReason.LIBRARY_SELECTION_AMBIGUOUS
    return next(iter(libraries)), None


def _is_path_policy_current(config_snapshot: ConfigSnapshot | None, library: Library | None) -> bool:
    if config_snapshot is None or library is None or config_snapshot.state is ConfigSnapshotState.INVALID:
        return False
    config = config_snapshot.config
    return library.path_policy_hash == calculate_path_policy_fingerprint(
        config.path_policy,
        config.artist_ids,
        config.metadata.album_year_resolution,
    )


def _library_reasons(
    library: Library | None,
    selection_reason: BootstrapReason | None,
    *,
    path_policy_current: bool,
) -> tuple[BootstrapReason, ...]:
    if selection_reason is not None:
        return (selection_reason,)
    if library is None:
        return ()
    if library.status is LibraryStatus.BLOCKED:
        return (BootstrapReason.LIBRARY_BLOCKED,)
    if library.status is LibraryStatus.UNREGISTERED:
        return (BootstrapReason.LIBRARY_UNREGISTERED,)
    if library.status is LibraryStatus.STALE or not path_policy_current:
        return (BootstrapReason.LIBRARY_STALE,)
    return ()
