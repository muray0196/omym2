"""
Summary: Defines the persisted record of one Library's latest check run.
Why: Lets check findings be browsed as a cheap DB read instead of recomputed per request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from omym2.shared.ids import CheckRunId, LibraryId


@dataclass(frozen=True, slots=True)
class CheckRun:
    """One completed check run for one Library, replaced wholesale on the next check."""

    check_run_id: CheckRunId
    library_id: LibraryId
    checked_at: datetime
    total_count: int
