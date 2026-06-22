"""
Summary: Defines pure config fingerprint calculation.
Why: Lets Plans preserve the settings identity used during creation.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from hashlib import new
from typing import TYPE_CHECKING

from omym2.config import (
    CONFIG_FINGERPRINT_ALGORITHM,
    CONFIG_FINGERPRINT_ENCODING,
    CONFIG_FINGERPRINT_JSON_ITEM_SEPARATOR,
    CONFIG_FINGERPRINT_JSON_KEY_SEPARATOR,
)

if TYPE_CHECKING:
    from omym2.domain.models.app_config import AppConfig

JSON_SEPARATORS = (CONFIG_FINGERPRINT_JSON_ITEM_SEPARATOR, CONFIG_FINGERPRINT_JSON_KEY_SEPARATOR)


def calculate_config_fingerprint(config: AppConfig, algorithm: str = CONFIG_FINGERPRINT_ALGORITHM) -> str:
    """Return a stable fingerprint for the complete AppConfig value."""
    # Canonical JSON keeps the hash independent from TOML formatting, comments,
    # and table ordering while still reflecting every AppConfig field.
    payload = json.dumps(asdict(config), sort_keys=True, separators=JSON_SEPARATORS)
    digest = new(algorithm)
    digest.update(payload.encode(CONFIG_FINGERPRINT_ENCODING))
    return digest.hexdigest()
