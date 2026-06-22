"""
Summary: Defines check feature request data.
Why: Gives check usecases stable contracts before consistency logic exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.shared.ids import LibraryId


@dataclass(frozen=True, slots=True)
class CheckLibraryRequest:
    """Request to inspect one Library or the selected default Library."""

    library_id: LibraryId | None = None
