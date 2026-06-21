"""
Summary: Defines organize feature request data.
Why: Gives organize usecases stable contracts before adapter implementation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CreateOrganizePlanRequest:
    """Request to organize or register a Library root."""

    library_root: str | None = None
