"""
Summary: Calculates deterministic content fingerprints for test fixtures.
Why: Keeps byte-fixture support out of the production domain API.
"""

from __future__ import annotations

from hashlib import new

from omym2.config import CONTENT_FINGERPRINT_ALGORITHM


def calculate_content_fingerprint(content: bytes) -> str:
    """Return the production-algorithm digest for supplied fixture bytes."""
    digest = new(CONTENT_FINGERPRINT_ALGORITHM)
    digest.update(content)
    return digest.hexdigest()
