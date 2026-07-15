"""
Summary: Builds deterministic Settings choices, validation, changes, and previews.
Why: Keeps complete Config edit behavior backend-owned and adapter-independent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from omym2.config import (
    ALLOWED_ALBUM_YEAR_RESOLUTION_METHODS,
    ALLOWED_COLLISION_DUPLICATE_HASH_POLICIES,
    ALLOWED_COLLISION_MISSING_METADATA_POLICIES,
    ALLOWED_COLLISION_TARGET_EXISTS_POLICIES,
    ALLOWED_COMMAND_MODES,
    ALLOWED_PATH_POLICY_DISC_NUMBER_CONDITIONS,
    ALLOWED_PATH_POLICY_DISC_NUMBER_STYLES,
    PATH_POLICY_ALLOWED_PLACEHOLDERS,
    PATH_POLICY_PREVIEW_ALBUM,
    PATH_POLICY_PREVIEW_ALBUM_ARTIST,
    PATH_POLICY_PREVIEW_ARTIST,
    PATH_POLICY_PREVIEW_DISC_NUMBER,
    PATH_POLICY_PREVIEW_DISC_TOTAL,
    PATH_POLICY_PREVIEW_FILE_EXTENSION,
    PATH_POLICY_PREVIEW_TITLE,
    PATH_POLICY_PREVIEW_TRACK_NUMBER,
    PATH_POLICY_PREVIEW_YEAR,
)
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.features.settings.dto import (
    PathPolicyPreviewRequest,
    PathPolicyPreviewResult,
    SettingsChoicesResult,
    SettingsFieldChange,
    SettingsValidationIssue,
)
from omym2.features.settings.usecases.preview_path_policy import PreviewPathPolicyUseCase

EMPTY_PATH_MESSAGE = "Configured paths must be non-empty when present."
EMPTY_PATH_POLICY_TEMPLATE_MESSAGE = "PathPolicy template must be non-empty."
EMPTY_ARTIST_NAME_MESSAGE = "Artist ID entry names must be non-empty."
EMPTY_ARTIST_DISPLAY_NAME_MESSAGE = "Artist display-name preference keys and values must be non-empty."
UNSUPPORTED_CHOICE_MESSAGE = "Value is not one of the backend-supported choices."


def settings_choices() -> SettingsChoicesResult:
    """Return deterministic backend-owned values for editable controls."""
    return SettingsChoicesResult(
        command_modes=tuple(sorted(ALLOWED_COMMAND_MODES)),
        disc_number_styles=tuple(sorted(ALLOWED_PATH_POLICY_DISC_NUMBER_STYLES)),
        disc_number_conditions=tuple(sorted(ALLOWED_PATH_POLICY_DISC_NUMBER_CONDITIONS)),
        album_year_resolutions=tuple(sorted(ALLOWED_ALBUM_YEAR_RESOLUTION_METHODS)),
        target_exists_policies=tuple(sorted(ALLOWED_COLLISION_TARGET_EXISTS_POLICIES)),
        duplicate_hash_policies=tuple(sorted(ALLOWED_COLLISION_DUPLICATE_HASH_POLICIES)),
        missing_metadata_policies=tuple(sorted(ALLOWED_COLLISION_MISSING_METADATA_POLICIES)),
        path_placeholders=PATH_POLICY_ALLOWED_PLACEHOLDERS,
    )


def validate_settings_config(config: AppConfig) -> tuple[SettingsValidationIssue, ...]:
    """Validate complete typed Config values not enforced by nested domain models."""
    issues: list[SettingsValidationIssue] = []
    _validate_optional_path(config.paths.library, "paths.library", issues)
    _validate_optional_path(config.paths.incoming, "paths.incoming", issues)
    _validate_choice(config.add.default_mode, ALLOWED_COMMAND_MODES, "add.default_mode", issues)
    _validate_choice(config.organize.default_mode, ALLOWED_COMMAND_MODES, "organize.default_mode", issues)
    _validate_choice(config.refresh.default_mode, ALLOWED_COMMAND_MODES, "refresh.default_mode", issues)
    if config.path_policy.template.strip() == "":
        issues.append(
            SettingsValidationIssue(
                field="path_policy.template",
                message=EMPTY_PATH_POLICY_TEMPLATE_MESSAGE,
            )
        )
    _validate_choice(
        config.path_policy.disc_number_style,
        ALLOWED_PATH_POLICY_DISC_NUMBER_STYLES,
        "path_policy.disc_number_style",
        issues,
    )
    _validate_choice(
        config.path_policy.disc_number_condition,
        ALLOWED_PATH_POLICY_DISC_NUMBER_CONDITIONS,
        "path_policy.disc_number_condition",
        issues,
    )
    _validate_choice(
        config.metadata.album_year_resolution,
        ALLOWED_ALBUM_YEAR_RESOLUTION_METHODS,
        "metadata.album_year_resolution",
        issues,
    )
    _validate_choice(
        config.collision.on_target_exists,
        ALLOWED_COLLISION_TARGET_EXISTS_POLICIES,
        "collision.on_target_exists",
        issues,
    )
    _validate_choice(
        config.collision.on_duplicate_hash,
        ALLOWED_COLLISION_DUPLICATE_HASH_POLICIES,
        "collision.on_duplicate_hash",
        issues,
    )
    _validate_choice(
        config.collision.on_missing_metadata,
        ALLOWED_COLLISION_MISSING_METADATA_POLICIES,
        "collision.on_missing_metadata",
        issues,
    )
    issues.extend(
        SettingsValidationIssue(field="artist_ids.entries", message=EMPTY_ARTIST_NAME_MESSAGE)
        for source_artist in sorted(config.artist_ids.entries or {})
        if source_artist.strip() == ""
    )
    issues.extend(
        SettingsValidationIssue(field="artist_names.preferences", message=EMPTY_ARTIST_DISPLAY_NAME_MESSAGE)
        for source_artist, display_name in sorted((config.artist_names.preferences or {}).items())
        if source_artist.strip() == "" or display_name.strip() == ""
    )
    return tuple(issues)


def settings_field_changes(before: AppConfig, after: AppConfig) -> tuple[SettingsFieldChange, ...]:
    """Return deterministic scalar differences for every persisted Config field."""
    fields: tuple[tuple[str, SettingsChangeValue, SettingsChangeValue], ...] = (
        ("version", before.version, after.version),
        ("paths.library", before.paths.library, after.paths.library),
        ("paths.incoming", before.paths.incoming, after.paths.incoming),
        ("add.default_mode", before.add.default_mode, after.add.default_mode),
        ("add.auto_apply", before.add.auto_apply, after.add.auto_apply),
        ("organize.default_mode", before.organize.default_mode, after.organize.default_mode),
        ("organize.auto_apply", before.organize.auto_apply, after.organize.auto_apply),
        ("refresh.default_mode", before.refresh.default_mode, after.refresh.default_mode),
        ("refresh.auto_apply", before.refresh.auto_apply, after.refresh.auto_apply),
        ("path_policy.template", before.path_policy.template, after.path_policy.template),
        ("path_policy.unknown_artist", before.path_policy.unknown_artist, after.path_policy.unknown_artist),
        ("path_policy.unknown_album", before.path_policy.unknown_album, after.path_policy.unknown_album),
        ("path_policy.sanitize", before.path_policy.sanitize, after.path_policy.sanitize),
        (
            "path_policy.max_filename_length",
            before.path_policy.max_filename_length,
            after.path_policy.max_filename_length,
        ),
        (
            "path_policy.disc_number_style",
            before.path_policy.disc_number_style,
            after.path_policy.disc_number_style,
        ),
        (
            "path_policy.disc_number_condition",
            before.path_policy.disc_number_condition,
            after.path_policy.disc_number_condition,
        ),
        ("artist_ids.max_length", before.artist_ids.max_length, after.artist_ids.max_length),
        ("artist_ids.fallback_id", before.artist_ids.fallback_id, after.artist_ids.fallback_id),
        (
            "metadata.prefer_album_artist",
            before.metadata.prefer_album_artist,
            after.metadata.prefer_album_artist,
        ),
        ("metadata.require_title", before.metadata.require_title, after.metadata.require_title),
        ("metadata.require_artist", before.metadata.require_artist, after.metadata.require_artist),
        ("metadata.require_album", before.metadata.require_album, after.metadata.require_album),
        (
            "metadata.album_year_resolution",
            before.metadata.album_year_resolution,
            after.metadata.album_year_resolution,
        ),
        (
            "collision.on_target_exists",
            before.collision.on_target_exists,
            after.collision.on_target_exists,
        ),
        (
            "collision.on_duplicate_hash",
            before.collision.on_duplicate_hash,
            after.collision.on_duplicate_hash,
        ),
        (
            "collision.on_missing_metadata",
            before.collision.on_missing_metadata,
            after.collision.on_missing_metadata,
        ),
    )
    changes = [
        SettingsFieldChange(field=field, before=before_value, after=after_value)
        for field, before_value, after_value in fields
        if before_value != after_value
    ]
    before_entries = before.artist_ids.entries or {}
    after_entries = after.artist_ids.entries or {}
    for source_artist in sorted(set(before_entries) | set(after_entries)):
        before_value = before_entries.get(source_artist)
        after_value = after_entries.get(source_artist)
        if before_value != after_value:
            changes.append(
                SettingsFieldChange(
                    field=f"artist_ids.entries.{source_artist}",
                    before=before_value,
                    after=after_value,
                )
            )
    before_preferences = before.artist_names.preferences or {}
    after_preferences = after.artist_names.preferences or {}
    for source_artist in sorted(set(before_preferences) | set(after_preferences)):
        before_value = before_preferences.get(source_artist)
        after_value = after_preferences.get(source_artist)
        if before_value != after_value:
            changes.append(
                SettingsFieldChange(
                    field=f"artist_names.preferences.{source_artist}",
                    before=before_value,
                    after=after_value,
                )
            )
    return tuple(changes)


def default_settings_preview(config: AppConfig) -> PathPolicyPreviewResult:
    """Render the backend-owned Settings sample using one complete Config draft."""
    return PreviewPathPolicyUseCase().execute(
        PathPolicyPreviewRequest(
            path_policy=config.path_policy,
            artist_ids=config.artist_ids,
            artist_names=config.artist_names,
            metadata=TrackMetadata(
                title=PATH_POLICY_PREVIEW_TITLE,
                artist=PATH_POLICY_PREVIEW_ARTIST,
                album=PATH_POLICY_PREVIEW_ALBUM,
                album_artist=PATH_POLICY_PREVIEW_ALBUM_ARTIST,
                year=PATH_POLICY_PREVIEW_YEAR,
                track_number=PATH_POLICY_PREVIEW_TRACK_NUMBER,
                disc_number=PATH_POLICY_PREVIEW_DISC_NUMBER,
                disc_total=PATH_POLICY_PREVIEW_DISC_TOTAL,
            ),
            file_extension=PATH_POLICY_PREVIEW_FILE_EXTENSION,
        )
    )


def _validate_optional_path(
    value: str | None,
    field: str,
    issues: list[SettingsValidationIssue],
) -> None:
    if value is not None and value.strip() == "":
        issues.append(SettingsValidationIssue(field=field, message=EMPTY_PATH_MESSAGE))


def _validate_choice(
    value: str,
    allowed: frozenset[str],
    field: str,
    issues: list[SettingsValidationIssue],
) -> None:
    if value not in allowed:
        issues.append(SettingsValidationIssue(field=field, message=UNSUPPORTED_CHOICE_MESSAGE))


if TYPE_CHECKING:
    from omym2.domain.models.app_config import AppConfig
    from omym2.features.settings.dto import SettingsChangeValue
