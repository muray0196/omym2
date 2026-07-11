"""
Summary: Defines refresh feature request data.
Why: Gives refresh usecases stable contracts before refresh logic exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.shared.ids import LibraryId, TrackId


@dataclass(frozen=True, slots=True)
class CreateRefreshPlanRequest:
    """Request to refresh all Tracks or a narrower target."""

    trust_stat: bool
    library_id: LibraryId | None = None
    track_id: TrackId | None = None
    target_path: str | None = None
    include_all: bool = False
