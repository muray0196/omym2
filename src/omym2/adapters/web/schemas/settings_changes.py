"""
Summary: Describes displayable settings differences.
Why: Lets the Web API report settings changes without frontend policy logic.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from omym2.domain.models.app_config import AppConfig


@dataclass(frozen=True, slots=True)
class SettingsChange:
    """One displayable settings difference."""

    label: str
    before: str
    after: str


def describe_config_changes(before: AppConfig, after: AppConfig) -> tuple[SettingsChange, ...]:
    """Return field-level changes between two AppConfig values."""
    field_values = (
        ("Library path", before.paths.library, after.paths.library),
        ("Incoming path", before.paths.incoming, after.paths.incoming),
        ("Add mode", before.add.default_mode, after.add.default_mode),
        ("Add auto apply", before.add.auto_apply, after.add.auto_apply),
        ("Organize mode", before.organize.default_mode, after.organize.default_mode),
        ("Organize auto apply", before.organize.auto_apply, after.organize.auto_apply),
        ("Organize only misplaced", before.organize.only_misplaced, after.organize.only_misplaced),
        ("Refresh mode", before.refresh.default_mode, after.refresh.default_mode),
        ("Refresh auto apply", before.refresh.auto_apply, after.refresh.auto_apply),
        ("Path template", before.path_policy.template, after.path_policy.template),
        ("Unknown artist", before.path_policy.unknown_artist, after.path_policy.unknown_artist),
        ("Unknown album", before.path_policy.unknown_album, after.path_policy.unknown_album),
        ("Sanitize path text", before.path_policy.sanitize, after.path_policy.sanitize),
        ("Max filename length", before.path_policy.max_filename_length, after.path_policy.max_filename_length),
        ("Artist ID max length", before.artist_ids.max_length, after.artist_ids.max_length),
        ("Artist ID fallback", before.artist_ids.fallback_id, after.artist_ids.fallback_id),
        ("Artist ID entries", before.artist_ids.entries, after.artist_ids.entries),
        ("Prefer album artist", before.metadata.prefer_album_artist, after.metadata.prefer_album_artist),
        ("Require title", before.metadata.require_title, after.metadata.require_title),
        ("Require artist", before.metadata.require_artist, after.metadata.require_artist),
        ("Require album", before.metadata.require_album, after.metadata.require_album),
        ("Target exists policy", before.collision.on_target_exists, after.collision.on_target_exists),
        ("Duplicate hash policy", before.collision.on_duplicate_hash, after.collision.on_duplicate_hash),
        ("Missing metadata policy", before.collision.on_missing_metadata, after.collision.on_missing_metadata),
        ("UI theme", before.ui.theme, after.ui.theme),
        ("Show advanced settings", before.ui.show_advanced_settings, after.ui.show_advanced_settings),
    )
    return tuple(
        SettingsChange(label=label, before=_display_value(before_value), after=_display_value(after_value))
        for label, before_value, after_value in field_values
        if before_value != after_value
    )


def _display_value(value: object) -> str:
    if value is None:
        return "Not set"
    if isinstance(value, bool):
        return "On" if value else "Off"
    if isinstance(value, Mapping):
        mapping_value = cast("Mapping[object, object]", value)
        return str(dict(mapping_value))
    return str(value)
