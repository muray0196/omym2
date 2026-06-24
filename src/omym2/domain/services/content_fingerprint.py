"""
Summary: Defines pure content fingerprint calculation.
Why: Lets adapters read bytes while domain owns hash policy.
"""

from __future__ import annotations

from hashlib import new

from omym2.config import CONTENT_FINGERPRINT_ALGORITHM


def calculate_content_fingerprint(content: bytes, algorithm: str = CONTENT_FINGERPRINT_ALGORITHM) -> str:
    """Return the content fingerprint for supplied bytes."""
    digest = new(algorithm)
    digest.update(content)
    return digest.hexdigest()
