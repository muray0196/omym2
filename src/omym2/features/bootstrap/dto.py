"""
Summary: Defines read-only Bootstrap readiness data.
Why: Keeps startup state selection independent of HTTP response models.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.library import Library, LibraryStatus
    from omym2.features.common_ports import ConfigSnapshot
    from omym2.shared.ids import OperationId


class BootstrapReason(StrEnum):
    """Stable readiness conditions translated by inbound adapters."""

    CONFIG_INVALID = "config_invalid"
    CONFIG_IO_FAILED = "config_io_failed"
    LIBRARY_SELECTION_AMBIGUOUS = "library_selection_ambiguous"
    LIBRARY_UNREGISTERED = "library_unregistered"
    LIBRARY_STALE = "library_stale"
    LIBRARY_BLOCKED = "library_blocked"
    STORAGE_UNAVAILABLE = "storage_unavailable"


@dataclass(frozen=True, slots=True)
class BootstrapCapabilities:
    """Backend-authoritative runtime availability and its stable reasons."""

    can_read_state: bool
    can_change_settings: bool
    can_start_operations: bool
    read_state_disabled_reasons: tuple[BootstrapReason, ...]
    change_settings_disabled_reasons: tuple[BootstrapReason, ...]
    start_operations_disabled_reasons: tuple[BootstrapReason, ...]


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    """Backend readiness snapshot used to build the HTTP Bootstrap resource."""

    config_snapshot: ConfigSnapshot | None
    config_valid: bool
    active_library: Library | None
    effective_library_status: LibraryStatus | None
    is_library_registered: bool
    is_path_policy_current: bool
    config_reason: BootstrapReason | None
    library_reasons: tuple[BootstrapReason, ...]
    state_storage_available: bool
    runtime_capabilities: BootstrapCapabilities
    active_operation_id: OperationId | None
