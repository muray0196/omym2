"""
Summary: Defines inspect feature request data.
Why: Gives inspect usecases stable contracts before read adapters exist.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InspectFileRequest:
    """Request to inspect one file."""

    path: str
