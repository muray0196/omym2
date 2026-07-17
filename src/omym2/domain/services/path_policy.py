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
    PATH_POLICY_ALLOWED_PLACEHOLDERS,
    PATH_POLICY_DISC_NUMBER_CONDITION_MULTIPLE_DISCS,
    PATH_POLICY_DISC_NUMBER_PREFIX,
    PATH_POLICY_DISC_NUMBER_STYLE_D_PREFIXED,
    PATH_POLICY_EMPTY_COMPONENT_REPLACEMENT,
    PATH_POLICY_RESERVED_WINDOWS_DEVICE_NAMES,
    PATH_POLICY_TRACK_NUMBER_WIDTH,
    SANITIZER_ALLOWED_EXTENSION_PATTERN,
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
    from omym2.domain.services.artist_name import ArtistNameProjection

from omym2.domain.models.app_config import ArtistIdConfig
from omym2.domain.services.artist_id import generate_artist_id
from omym2.domain.services.config_fingerprint import template_uses_placeholder

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
    _used_placeholders: frozenset[str] = field(init=False, repr=False, compare=False)
    _path_component_cache: dict[tuple[str, int | None], str] = field(
        default_factory=dict,
        init=False,
        repr=False,
        compare=False,
    )
    _generated_artist_id_cache: dict[str, str] = field(default_factory=dict, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Cache the template fields that can affect this policy instance."""
        object.__setattr__(
            self,
            "_used_placeholders",
            frozenset(
                placeholder
                for placeholder in PATH_POLICY_ALLOWED_PLACEHOLDERS
                if template_uses_placeholder(self.config.template, placeholder)
            ),
        )

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

    def canonical_path(
        self,
        metadata: TrackMetadata,
        file_extension: str,
        *,
        album_disc_total: int | None = None,
        artist_names: ArtistNameProjection | None = None,
    ) -> str:
        """Generate a normalized Library-root-relative canonical path."""
        extension_suffix = _normalize_extension_suffix(file_extension)
        raw_stem = self._render_raw_stem(metadata, album_disc_total, artist_names)
        generated_path = _normalize_generated_path(raw_stem, extension_suffix, self.config)
        return normalize_library_relative_path(generated_path)

    def _render_raw_stem(
        self,
        metadata: TrackMetadata,
        album_disc_total: int | None,
        artist_names: ArtistNameProjection | None,
    ) -> str:
        # Title validity predates template-aware rendering and remains a
        # PathPolicy invariant even when a custom template omits {title}.
        if metadata.title is None or metadata.title.strip() == "":
            raise ValueError(MISSING_TITLE_MESSAGE)

        values: dict[str, str] = {}
        if "album_artist" in self._used_placeholders:
            values["album_artist"] = self._album_artist(metadata, artist_names)
        if "year" in self._used_placeholders:
            values["year"] = self._optional_number(metadata.year)
        if "album" in self._used_placeholders:
            values["album"] = self._album(metadata)
        if "disc" in self._used_placeholders:
            values["disc"] = self._disc_number(metadata, album_disc_total)
        if "track" in self._used_placeholders:
            values["track"] = self._track_number(metadata)
        if "title" in self._used_placeholders:
            values["title"] = self._title(metadata)
        if "artist" in self._used_placeholders:
            values["artist"] = self._artist(metadata, artist_names)
        if "artist_id" in self._used_placeholders:
            values["artist_id"] = self._artist_id(metadata, artist_names)
        return self.config.template.format(**values)

    def _album_artist(self, metadata: TrackMetadata, artist_names: ArtistNameProjection | None) -> str:
        projected_album_artist = None if artist_names is None else artist_names.album_artist
        projected_artist = None if artist_names is None else artist_names.artist
        return self._artist_component(
            projected_album_artist
            or metadata.album_artist
            or projected_artist
            or metadata.artist
            or self.config.unknown_artist
        )

    def _artist(self, metadata: TrackMetadata, artist_names: ArtistNameProjection | None) -> str:
        projected_artist = None if artist_names is None else artist_names.artist
        projected_album_artist = None if artist_names is None else artist_names.album_artist
        return self._artist_component(
            projected_artist
            or metadata.artist
            or projected_album_artist
            or metadata.album_artist
            or self.config.unknown_artist
        )

    def _artist_id(self, metadata: TrackMetadata, artist_names: ArtistNameProjection | None) -> str:
        source_artist = metadata.artist or metadata.album_artist or self.config.unknown_artist
        cached_artist_id = self._generated_artist_id_cache.get(source_artist)
        if cached_artist_id is not None:
            return cached_artist_id

        projected_artist = None
        if artist_names is not None:
            projected_artist = artist_names.artist if metadata.artist else artist_names.album_artist
        generation_artist = projected_artist or source_artist
        generated_artist_id = generate_artist_id(
            generation_artist,
            max_length=self.artist_ids.max_length,
            fallback_id=self.artist_ids.fallback_id,
        )
        # The generated ID is already [A-Za-z0-9]+, so sanitizing it is a
        # harmless no-op; routing both branches through the same helper keeps
        # {artist_id} rendering consistent regardless of which branch is used.
        sanitized_generated_artist_id = self._artist_id_component(generated_artist_id)
        self._generated_artist_id_cache[source_artist] = sanitized_generated_artist_id
        return sanitized_generated_artist_id

    def _artist_id_component(self, value: str) -> str:
        if not self.config.sanitize:
            return value
        return self._path_component(value)

    def _album(self, metadata: TrackMetadata) -> str:
        value = metadata.album or self.config.unknown_album
        if not self.config.sanitize:
            return value
        return self._path_component(value)

    def _title(self, metadata: TrackMetadata) -> str:
        if metadata.title is None or metadata.title.strip() == "":
            raise ValueError(MISSING_TITLE_MESSAGE)
        if not self.config.sanitize:
            return metadata.title
        return sanitize_track_title(metadata.title)

    def _disc_number(self, metadata: TrackMetadata, album_disc_total: int | None) -> str:
        inferred_disc_total = album_disc_total if album_disc_total is not None else metadata.disc_total
        if (
            self.config.disc_number_condition == PATH_POLICY_DISC_NUMBER_CONDITION_MULTIPLE_DISCS
            and not _is_multi_disc_album(inferred_disc_total)
        ):
            return ""

        rendered_number = self._optional_number(metadata.disc_number)
        if rendered_number == PATH_POLICY_EMPTY_COMPONENT_REPLACEMENT:
            return rendered_number
        if self.config.disc_number_style == PATH_POLICY_DISC_NUMBER_STYLE_D_PREFIXED:
            return f"{PATH_POLICY_DISC_NUMBER_PREFIX}{rendered_number}"
        return rendered_number

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
        return self._path_component(value)

    def _path_component(self, value: str, max_length: int | None = None) -> str:
        cache_key = (value, max_length)
        cached_component = self._path_component_cache.get(cache_key)
        if cached_component is None:
            cached_component = sanitize_path_component(value, max_length)
            self._path_component_cache[cache_key] = cached_component
        return cached_component


def sanitize_string(
    value: str | float | None,
    max_length: int | None = None,
    *,
    preserve_extension: bool = False,
) -> str:
    """Normalize text into one portable OMYM2 filename component.

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


def _is_multi_disc_album(album_disc_total: int | None) -> bool:
    return album_disc_total is not None and album_disc_total > 1


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
    # NFKC gives canonically equivalent metadata one deterministic path while
    # preserving letters from non-Latin scripts.
    normalized = unicodedata.normalize("NFKC", value)
    replaced = _UNSAFE_PATTERN.sub(SANITIZER_REPLACEMENT, normalized)
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
        # max_length budgets the TOTAL component (stem + extension), matching
        # the sanitize=False branch. Extension preservation dominates the
        # budget: the suffix is never truncated or dropped, and a non-empty
        # stem keeps at least its first character even when the budget is
        # smaller than the extension bytes, so a degenerate max_length can
        # exceed the configured budget by necessity.
        stem_budget = None if max_length is None else max_length - _utf8_length(extension_suffix)
        limited_base = _limit_utf8(base, stem_budget).strip(SANITIZER_REPLACEMENT)
        if limited_base == "" and base != "":
            limited_base = base[:1]
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
    # Extension preservation dominates the length budget: the suffix is never
    # truncated or dropped, and a non-empty stem keeps at least its first
    # character even when max_length <= extension bytes. With such degenerate
    # budgets the total necessarily exceeds max_length; filesystem-level limit
    # failures surface fail-closed at apply time.
    extension_bytes = _utf8_length(extension_suffix)
    limited_stem = _limit_component(value, max_length - extension_bytes)
    if limited_stem == "" and value != "":
        limited_stem = value[:1]
    return f"{limited_stem}{extension_suffix}"


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
