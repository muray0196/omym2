"""
Summary: Defines canonical Library-relative path generation.
Why: Centralizes pure path policy shared by add, organize, and refresh.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from omym2.config import (
    LOGICAL_PATH_SEPARATOR,
    PATH_EXTENSION_PREFIX,
    PATH_POLICY_EMPTY_COMPONENT_REPLACEMENT,
    PATH_POLICY_RESERVED_WINDOWS_DEVICE_NAMES,
    PATH_POLICY_TRACK_NUMBER_WIDTH,
    SANITIZER_ALBUM_MAX_BYTES,
    SANITIZER_ALLOWED_EXTENSION_PATTERN,
    SANITIZER_APOSTROPHE,
    SANITIZER_ARTIST_MAX_BYTES,
    SANITIZER_FALLBACK_TITLE,
    SANITIZER_HYPHEN_RUN_PATTERN,
    SANITIZER_REPLACEMENT,
    SANITIZER_UNSAFE_PATTERN,
    SANITIZER_UTF8_ENCODING,
)
from omym2.shared.paths import normalize_library_relative_path

if TYPE_CHECKING:
    from omym2.domain.models.app_config import AppConfig, ArtistIdConfig, PathPolicyConfig
    from omym2.domain.models.track_metadata import TrackMetadata

from omym2.domain.models.app_config import ArtistIdConfig
from omym2.domain.services.artist_id import generate_artist_id

EMPTY_FILE_EXTENSION_MESSAGE = "File extension must not be empty."
MISSING_TITLE_MESSAGE = "Track title is required for canonical path generation."

_ALLOWED_EXTENSION_PATTERN = re.compile(SANITIZER_ALLOWED_EXTENSION_PATTERN)
_HYPHEN_RUN_PATTERN = re.compile(SANITIZER_HYPHEN_RUN_PATTERN)
_UNSAFE_PATTERN = re.compile(SANITIZER_UNSAFE_PATTERN)


@dataclass(frozen=True, slots=True)
class PathPolicy:
    """Pure service that generates canonical Library-root-relative paths."""

    config: PathPolicyConfig
    artist_ids: ArtistIdConfig = field(default_factory=ArtistIdConfig)

    @classmethod
    def from_path_policy_config(cls, config: PathPolicyConfig, artist_ids: ArtistIdConfig) -> PathPolicy:
        """Build a PathPolicy from its path-policy and artist-id configs.

        This is the single assembly point for PathPolicy construction so a
        future constructor parameter only needs updating here.
        """
        return cls(config, artist_ids)

    @classmethod
    def from_app_config(cls, config: AppConfig) -> PathPolicy:
        """Build a PathPolicy from the AppConfig fields it depends on."""
        return cls.from_path_policy_config(config.path_policy, config.artist_ids)

    def canonical_path(self, metadata: TrackMetadata, file_extension: str) -> str:
        """Generate a normalized Library-root-relative canonical path."""
        extension_suffix = _normalize_extension_suffix(file_extension)
        raw_stem = self._render_raw_stem(metadata)
        generated_path = _normalize_generated_path(raw_stem, extension_suffix, self.config)
        return normalize_library_relative_path(generated_path)

    def _render_raw_stem(self, metadata: TrackMetadata) -> str:
        return self.config.template.format(
            album_artist=self._album_artist(metadata),
            year=self._optional_number(metadata.year),
            album=self._album(metadata),
            disc=self._disc_number(metadata),
            track=self._track_number(metadata),
            title=self._title(metadata),
            artist=self._artist(metadata),
            artist_id=self._artist_id(metadata),
        )

    def _album_artist(self, metadata: TrackMetadata) -> str:
        return self._artist_component(metadata.album_artist or metadata.artist or self.config.unknown_artist)

    def _artist(self, metadata: TrackMetadata) -> str:
        return self._artist_component(metadata.artist or metadata.album_artist or self.config.unknown_artist)

    def _artist_id(self, metadata: TrackMetadata) -> str:
        source_artist = metadata.artist or metadata.album_artist or self.config.unknown_artist
        saved_artist_id = self.artist_ids.entries.get(source_artist) if self.artist_ids.entries is not None else None
        if saved_artist_id is not None:
            sanitized_saved_artist_id = self._artist_id_component(saved_artist_id)
            # A saved entry is normally validated as sanitizer-stable at config
            # construction (ArtistIdConfig.__post_init__), so sanitizing here is
            # defense-in-depth. If sanitizing still collapses it to nothing,
            # fall through to the generated ID instead of returning an empty
            # component, which would otherwise silently drop a path directory
            # level.
            if sanitized_saved_artist_id != "":
                return sanitized_saved_artist_id
        generated_artist_id = generate_artist_id(
            source_artist,
            max_length=self.artist_ids.max_length,
            fallback_id=self.artist_ids.fallback_id,
        )
        # The generated ID is already [A-Za-z0-9]+, so sanitizing it is a
        # harmless no-op; routing both branches through the same helper keeps
        # {artist_id} rendering consistent regardless of which branch is used.
        return self._artist_id_component(generated_artist_id)

    def _artist_id_component(self, value: str) -> str:
        if not self.config.sanitize:
            return value
        return sanitize_path_component(value)

    def _album(self, metadata: TrackMetadata) -> str:
        value = metadata.album or self.config.unknown_album
        if not self.config.sanitize:
            return value
        return sanitize_path_component(value, SANITIZER_ALBUM_MAX_BYTES)

    def _title(self, metadata: TrackMetadata) -> str:
        if metadata.title is None or metadata.title.strip() == "":
            raise ValueError(MISSING_TITLE_MESSAGE)
        if not self.config.sanitize:
            return metadata.title
        return sanitize_track_title(metadata.title)

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

    def _artist_component(self, value: str) -> str:
        if not self.config.sanitize:
            return value
        return sanitize_path_component(value, SANITIZER_ARTIST_MAX_BYTES)


def sanitize_string(
    value: str | float | None,
    max_length: int | None = None,
    *,
    preserve_extension: bool = False,
) -> str:
    """Sanitize text using the migrated OMYM filename pipeline.

    Args:
        value: Text-like value supplied by metadata or wrapper code.
        max_length: Optional maximum output length measured in UTF-8 bytes.
        preserve_extension: Whether to preserve an allowed final extension.

    Returns:
        Sanitized text, or an empty string when no allowed content remains.
    """
    if not value:
        return ""

    raw_text = str(value)
    base_text, extension_suffix = _split_preserved_extension(raw_text, preserve_extension=preserve_extension)
    sanitized_base = _sanitize_base_text(base_text)
    return _limit_sanitized_with_extension(sanitized_base, extension_suffix, max_length)


def sanitize_artist_name(value: str | float | None) -> str:
    """Sanitize artist text using the migrated artist byte limit."""
    return sanitize_string(value, max_length=SANITIZER_ARTIST_MAX_BYTES)


def sanitize_album_name(value: str | float | None) -> str:
    """Sanitize album text using the migrated album byte limit."""
    return sanitize_string(value, max_length=SANITIZER_ALBUM_MAX_BYTES)


def sanitize_track_title(value: str | float | None, max_length: int | None = None) -> str:
    """Sanitize title text and fall back when no title-safe text remains."""
    sanitized_title = sanitize_string(value, max_length=max_length)
    if sanitized_title != "":
        return sanitized_title
    return _limit_utf8(SANITIZER_FALLBACK_TITLE, max_length)


def sanitize_path_component(
    value: str | float | None,
    max_length: int | None = None,
    *,
    preserve_extension: bool = False,
) -> str:
    """Sanitize one path component with optional final-extension preservation."""
    if not value:
        return ""

    sanitized_component = sanitize_string(value, max_length=max_length, preserve_extension=preserve_extension)
    if sanitized_component != "":
        return sanitized_component

    # Path generation cannot store empty non-final components. Keep the generic
    # sanitizer empty-result behavior, but give path components a stable name.
    return PATH_POLICY_EMPTY_COMPONENT_REPLACEMENT


def sanitize_path_components(value: str | float | None, max_length: int | None = None) -> str:
    """Sanitize a logical path, preserving an allowed extension on the final component."""
    if not value:
        return ""

    raw_components = str(value).split(LOGICAL_PATH_SEPARATOR)
    final_index = len(raw_components) - 1
    sanitized_components = [
        sanitize_path_component(
            component,
            max_length=max_length,
            preserve_extension=index == final_index,
        )
        for index, component in enumerate(raw_components)
    ]
    return LOGICAL_PATH_SEPARATOR.join(component for component in sanitized_components if component != "")


def _normalize_extension_suffix(file_extension: str) -> str:
    extension = file_extension.strip().lower()
    if extension.startswith(PATH_EXTENSION_PREFIX):
        extension = extension.removeprefix(PATH_EXTENSION_PREFIX)
    if extension == "":
        raise ValueError(EMPTY_FILE_EXTENSION_MESSAGE)
    sanitized_extension = sanitize_string(extension, len(extension))
    if sanitized_extension == "":
        raise ValueError(EMPTY_FILE_EXTENSION_MESSAGE)
    return f"{PATH_EXTENSION_PREFIX}{sanitized_extension}"


def _normalize_generated_path(raw_stem: str, extension_suffix: str, config: PathPolicyConfig) -> str:
    parts = raw_stem.split(LOGICAL_PATH_SEPARATOR)
    if config.sanitize:
        normalized_parts = [sanitize_path_component(part, config.max_filename_length) for part in parts[:-1]]
        normalized_parts.append(
            sanitize_path_component(
                _append_extension(parts[-1], extension_suffix),
                config.max_filename_length,
                preserve_extension=True,
            )
        )
    else:
        normalized_parts = [_limit_component(part, config.max_filename_length) for part in parts[:-1]]
        normalized_parts.append(_limit_component_with_suffix(parts[-1], extension_suffix, config.max_filename_length))
    return LOGICAL_PATH_SEPARATOR.join(normalized_parts)


def _sanitize_base_text(value: str) -> str:
    # NFKC folds compatibility characters while preserving letters from
    # non-Latin scripts, matching the legacy OMYM sanitizer behavior.
    normalized = unicodedata.normalize("NFKC", value)
    without_apostrophes = normalized.replace(SANITIZER_APOSTROPHE, "")
    replaced = _UNSAFE_PATTERN.sub(SANITIZER_REPLACEMENT, without_apostrophes)
    collapsed = _HYPHEN_RUN_PATTERN.sub(SANITIZER_REPLACEMENT, replaced)
    return collapsed.strip(SANITIZER_REPLACEMENT)


def _split_preserved_extension(value: str, *, preserve_extension: bool) -> tuple[str, str]:
    if not preserve_extension:
        return value, ""

    base, separator, extension = value.rpartition(PATH_EXTENSION_PREFIX)
    if separator == "" or extension == "":
        return value, ""
    if _ALLOWED_EXTENSION_PATTERN.fullmatch(extension) is None:
        return value, ""
    return base, f"{PATH_EXTENSION_PREFIX}{extension}"


def _limit_sanitized_with_extension(base: str, extension_suffix: str, max_length: int | None) -> str:
    if extension_suffix != "":
        limited_base = _limit_utf8(base, max_length).strip(SANITIZER_REPLACEMENT)
        if limited_base == "" or _is_reserved_windows_device_name(limited_base):
            return f"{PATH_POLICY_EMPTY_COMPONENT_REPLACEMENT}{extension_suffix}"
        return f"{limited_base}{extension_suffix}"

    if max_length is None:
        limited_base = base
    elif max_length <= 0:
        return ""
    else:
        limited_base = _limit_utf8(base, max_length).strip(SANITIZER_REPLACEMENT)

    # Treat a stem that is a reserved Windows device name (case-insensitive)
    # the same as a sanitized-to-empty stem, so callers apply the same "_"
    # fallback machinery they already use for empty components.
    if _is_reserved_windows_device_name(limited_base):
        return ""
    return limited_base


def _is_reserved_windows_device_name(value: str) -> bool:
    return value.upper() in PATH_POLICY_RESERVED_WINDOWS_DEVICE_NAMES


def _limit_component_with_suffix(value: str, extension_suffix: str, max_length: int) -> str:
    extension_bytes = _utf8_length(extension_suffix)
    if max_length <= extension_bytes:
        return "" if extension_bytes > max_length else extension_suffix
    return f"{_limit_component(value, max_length - extension_bytes)}{extension_suffix}"


def _limit_component(value: str, max_length: int) -> str:
    return _limit_utf8(value, max_length)


def _limit_utf8(value: str, max_length: int | None) -> str:
    if max_length is None:
        return value
    if max_length <= 0:
        return ""

    encoded = value.encode(SANITIZER_UTF8_ENCODING)
    if len(encoded) <= max_length:
        return value
    return encoded[:max_length].decode(SANITIZER_UTF8_ENCODING, errors="ignore")


def _utf8_length(value: str) -> int:
    return len(value.encode(SANITIZER_UTF8_ENCODING))


def _append_extension(path_stem: str, extension_suffix: str) -> str:
    return f"{path_stem}{extension_suffix}"
