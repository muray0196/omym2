"""
Summary: Defines read-only Library inspection request and result data.
Why: Gives Web Library routes a backend-authoritative readiness projection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.library import Library, LibraryStatus
    from omym2.shared.ids import LibraryId


@dataclass(frozen=True, slots=True)
class InspectLibrariesRequest:
    """Request every Library or one Library selected by stable identity."""

    library_id: LibraryId | None = None


@dataclass(frozen=True, slots=True)
class LibraryInspection:
    """One Library with its effective current-Config readiness."""

    library: Library
    effective_status: LibraryStatus
    is_registered: bool
    is_path_policy_current: bool
