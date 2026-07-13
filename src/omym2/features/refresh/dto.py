"""
Summary: Defines refresh feature request data.
Why: Gives refresh usecases stable contracts before refresh logic exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.shared.ids import LibraryId, OperationId, TrackId


class RefreshTargetKind(StrEnum):
    """Explicit Web target interpretation for a path-based Refresh request."""

    FILE = "file"
    DIRECTORY = "directory"


@dataclass(frozen=True, slots=True)
class CreateRefreshPlanRequest:
    """Request to refresh all Tracks or a narrower target."""

    trust_stat: bool
    library_id: LibraryId | None = None
    track_id: TrackId | None = None
    target_path: str | None = None
    target_kind: RefreshTargetKind | None = None
    include_all: bool = False
    operation_id: OperationId | None = None
