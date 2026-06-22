"""
Summary: Provides the default OMYM2 application config.
Why: Lets missing config files resolve without treating bootstrap as an error.
"""

from __future__ import annotations

from omym2.domain.models.app_config import AppConfig


def default_app_config() -> AppConfig:
    """Return the documented default in-memory settings."""
    return AppConfig()
