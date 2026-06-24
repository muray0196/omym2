"""
Summary: Provides CLI confirmation helpers.
Why: Keeps interactive prompts in adapters instead of feature usecases.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import TextIO

APPLY_CANCELLED_MESSAGE = "Apply cancelled; plan remains ready."
APPLY_CONFIRMATION_PROMPT = "Apply plan? [y/N] "
CONFIRMED_RESPONSES = frozenset({"y", "yes"})


@dataclass(frozen=True, slots=True)
class ConfirmationOptions:
    """Confirmation options parsed by command adapters."""

    yes: bool = False


def confirm_apply(stdout: TextIO, options: ConfirmationOptions) -> bool:
    """Return whether the user confirmed a Plan apply attempt."""
    if options.yes:
        return True

    _ = stdout.write(APPLY_CONFIRMATION_PROMPT)
    return sys.stdin.readline().strip().casefold() in CONFIRMED_RESPONSES
