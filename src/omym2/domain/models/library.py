"""
Summary: Defines managed Library identity and registration state.
Why: Keeps Library identity stable independent of root path changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from omym2.shared.time import as_utc

if TYPE_CHECKING:
    from datetime import datetime

    from omym2.shared.ids import LibraryId


class LibraryStatus(StrEnum):
    """Known Library registration states."""

    REGISTERED = "registered"
    UNREGISTERED = "unregistered"
    STALE = "stale"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class Library:
    """A music Library managed by OMYM2."""

    library_id: LibraryId
    root_path: str
    path_policy_hash: str
    registered_at: datetime | None
    status: LibraryStatus
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        """Normalize timestamps while preserving the supplied Library ID."""
        if self.registered_at is not None:
            object.__setattr__(self, "registered_at", as_utc(self.registered_at))
        object.__setattr__(self, "created_at", as_utc(self.created_at))
        object.__setattr__(self, "updated_at", as_utc(self.updated_at))
