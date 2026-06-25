"""
Summary: Defines track inspection request data.
Why: Gives Web adapters a read-only Track query contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.shared.ids import LibraryId


@dataclass(frozen=True, slots=True)
class ListTracksRequest:
    """Request to list Tracks for a Library or every known Library."""

    library_id: LibraryId | None = None
