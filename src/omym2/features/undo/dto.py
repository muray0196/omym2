"""
Summary: Defines undo feature request data.
Why: Gives undo usecases stable contracts before history-based planning exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.shared.ids import RunId


@dataclass(frozen=True, slots=True)
class CreateUndoPlanRequest:
    """Request to create an undo Plan from a prior Run."""

    run_id: RunId
