"""
Summary: Defines pure metadata fingerprint calculation.
Why: Detects tag changes without treating metadata as Track identity.
"""

from __future__ import annotations

import json
from hashlib import new
from typing import TYPE_CHECKING

from omym2.config import (
    METADATA_FINGERPRINT_ALGORITHM,
    METADATA_FINGERPRINT_ENCODING,
    METADATA_FINGERPRINT_JSON_ITEM_SEPARATOR,
    METADATA_FINGERPRINT_JSON_KEY_SEPARATOR,
)

if TYPE_CHECKING:
    from omym2.domain.models.track_metadata import TrackMetadata

JSON_SEPARATORS = (METADATA_FINGERPRINT_JSON_ITEM_SEPARATOR, METADATA_FINGERPRINT_JSON_KEY_SEPARATOR)


def calculate_metadata_fingerprint(
    metadata: TrackMetadata,
    algorithm: str = METADATA_FINGERPRINT_ALGORITHM,
) -> str:
    """Return a stable fingerprint for metadata values."""
    # Canonical JSON avoids dataclass field ordering or whitespace changing the hash.
    payload = json.dumps(metadata.fingerprint_payload(), sort_keys=True, separators=JSON_SEPARATORS)
    digest = new(algorithm)
    digest.update(payload.encode(METADATA_FINGERPRINT_ENCODING))
    return digest.hexdigest()
