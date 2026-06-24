"""
Summary: Defines inspect feature request data.
Why: Gives inspect usecases stable contracts before read adapters exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.file_snapshot import FileSnapshot


@dataclass(frozen=True, slots=True)
class InspectFileRequest:
    """Request to inspect one file."""

    path: str


@dataclass(frozen=True, slots=True)
class InspectFileResult:
    """Result of read-only inspection for one file."""

    snapshot: FileSnapshot
    canonical_path: str | None
    canonical_path_error: str | None = None
