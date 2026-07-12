"""
Summary: Defines the shared content-hashed Web asset naming predicate.
Why: Keeps package auditing and production serving in exact agreement.
"""

from __future__ import annotations

import re

from omym2.config import WEB_ASSET_HASH_MIN_LENGTH


def is_hashed_asset_name(file_name: str) -> bool:
    """Return whether a Vite asset name carries the required final hash segment."""
    return (
        re.fullmatch(
            rf".+-[A-Za-z0-9_-]{{{WEB_ASSET_HASH_MIN_LENGTH},}}\.[A-Za-z0-9]+",
            file_name,
        )
        is not None
    )
