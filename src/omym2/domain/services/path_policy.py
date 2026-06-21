"""
Summary: Defines canonical Library-relative path generation.
Why: Centralizes pure path policy shared by add, organize, and refresh.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.config import (
    LOGICAL_PATH_SEPARATOR,
    PATH_EXTENSION_PREFIX,
    PATH_POLICY_EMPTY_COMPONENT_REPLACEMENT,
    PATH_POLICY_TRACK_NUMBER_WIDTH,
    PATH_POLICY_UNSAFE_CHARACTERS,
)
from omym2.shared.paths import normalize_library_relative_path

if TYPE_CHECKING:
    from omym2.domain.models.app_config import PathPolicyConfig
    from omym2.domain.models.track_metadata import TrackMetadata

EMPTY_FILE_EXTENSION_MESSAGE = "File extension must not be empty."
MISSING_TITLE_MESSAGE = "Track title is required for canonical path generation."


@dataclass(frozen=True, slots=True)
class PathPolicy:
    """Pure service that generates canonical Library-root-relative paths."""

    config: PathPolicyConfig

    def canonical_path(self, metadata: TrackMetadata, file_extension: str) -> str:
        """Generate a normalized Library-root-relative canonical path."""
        extension = _normalize_extension(file_extension)
        raw_path = self.config.template.format(
            album_artist=self._album_artist(metadata),
            year=self._optional_number(metadata.year),
            album=self._album(metadata),
            disc=self._disc_number(metadata),
            track=self._track_number(metadata),
            title=self._title(metadata),
            ext=extension,
        )
        expected_suffix = f"{PATH_EXTENSION_PREFIX}{extension}"
        canonical_path = normalize_library_relative_path(
            _normalize_generated_path(raw_path, self.config, expected_suffix)
        )
        # Defense in depth for direct PathPolicyConfig construction paths: a
        # canonical music-file path must preserve the observed source extension.
        if not canonical_path.endswith(expected_suffix):
            raise ValueError(EMPTY_FILE_EXTENSION_MESSAGE)
        return canonical_path

    def _album_artist(self, metadata: TrackMetadata) -> str:
        return self._component(metadata.album_artist or metadata.artist or self.config.unknown_artist)

    def _album(self, metadata: TrackMetadata) -> str:
        return self._component(metadata.album or self.config.unknown_album)

    def _title(self, metadata: TrackMetadata) -> str:
        if metadata.title is None or metadata.title.strip() == "":
            raise ValueError(MISSING_TITLE_MESSAGE)
        return self._component(metadata.title)

    def _disc_number(self, metadata: TrackMetadata) -> str:
        return self._optional_number(metadata.disc_number)

    def _track_number(self, metadata: TrackMetadata) -> str:
        if metadata.track_number is None:
            return PATH_POLICY_EMPTY_COMPONENT_REPLACEMENT
        return str(metadata.track_number).zfill(PATH_POLICY_TRACK_NUMBER_WIDTH)

    def _optional_number(self, value: int | None) -> str:
        if value is None:
            return PATH_POLICY_EMPTY_COMPONENT_REPLACEMENT
        return str(value)

    def _component(self, value: str) -> str:
        if not self.config.sanitize:
            return value
        return _sanitize_component(value, self.config.max_filename_length)


def _normalize_extension(file_extension: str) -> str:
    extension = file_extension.strip().lower()
    if extension.startswith(PATH_EXTENSION_PREFIX):
        extension = extension.removeprefix(PATH_EXTENSION_PREFIX)
    if extension == "":
        raise ValueError(EMPTY_FILE_EXTENSION_MESSAGE)
    return _sanitize_component(extension, len(extension))


def _normalize_generated_path(raw_path: str, config: PathPolicyConfig, expected_suffix: str) -> str:
    parts = raw_path.split(LOGICAL_PATH_SEPARATOR)
    if config.sanitize:
        normalized_parts = [_sanitize_component(part, config.max_filename_length) for part in parts[:-1]]
        normalized_parts.append(
            _sanitize_component_preserving_suffix(parts[-1], config.max_filename_length, expected_suffix)
        )
    else:
        normalized_parts = [_limit_component(part, config.max_filename_length) for part in parts[:-1]]
        normalized_parts.append(
            _limit_component_preserving_suffix(parts[-1], config.max_filename_length, expected_suffix)
        )
    return LOGICAL_PATH_SEPARATOR.join(normalized_parts)


def _sanitize_component(value: str, max_length: int) -> str:
    cleaned = value.strip()
    for unsafe_character in PATH_POLICY_UNSAFE_CHARACTERS:
        cleaned = cleaned.replace(unsafe_character, PATH_POLICY_EMPTY_COMPONENT_REPLACEMENT)
    cleaned = cleaned[:max_length]
    if cleaned in {"", ".", ".."}:
        return PATH_POLICY_EMPTY_COMPONENT_REPLACEMENT
    return cleaned


def _sanitize_component_preserving_suffix(value: str, max_length: int, expected_suffix: str) -> str:
    cleaned = value.strip()
    for unsafe_character in PATH_POLICY_UNSAFE_CHARACTERS:
        cleaned = cleaned.replace(unsafe_character, PATH_POLICY_EMPTY_COMPONENT_REPLACEMENT)
    limited = _limit_component_preserving_suffix(cleaned, max_length, expected_suffix)
    if limited in {"", ".", ".."}:
        return PATH_POLICY_EMPTY_COMPONENT_REPLACEMENT
    return limited


def _limit_component(value: str, max_length: int) -> str:
    return value[:max_length]


def _limit_component_preserving_suffix(value: str, max_length: int, expected_suffix: str) -> str:
    if not value.endswith(expected_suffix) or len(value) <= max_length:
        return _limit_component(value, max_length)
    basename_length = max_length - len(expected_suffix)
    if basename_length <= 0:
        return expected_suffix
    return f"{value[:basename_length]}{expected_suffix}"
