"""
Summary: Defines add feature request and response data.
Why: Gives add usecases stable contracts before adapter implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.shared.ids import LibraryId, OperationId


@dataclass(frozen=True, slots=True)
class CreateAddPlanRequest:
    """Request to create an add Plan from Incoming or a supplied source."""

    source_path: str | None = None
    library_id: LibraryId | None = None
    operation_id: OperationId | None = None
