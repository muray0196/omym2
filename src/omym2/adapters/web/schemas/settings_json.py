"""
Summary: Converts settings JSON payloads into AppConfig values.
Why: Keeps Web API request parsing separate from settings route orchestration.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from omym2.adapters.config.config_validator import INCOMING_KEY, LIBRARY_KEY, PATHS_SECTION, validate_config_data
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.features.common_ports import ConfigStoreValidationError

if TYPE_CHECKING:
    from omym2.domain.models.app_config import AppConfig

CONFIG_FIELD = "config"
CONFIG_FIELD_ERROR = "Request body must contain a config object."
FILE_EXTENSION_FIELD = "file_extension"
METADATA_FIELD = "metadata"
REQUEST_BODY_ERROR = "Request body must be a JSON object."


@dataclass(frozen=True, slots=True)
class SettingsJsonResult:
    """Parsed settings JSON result."""

    config: AppConfig | None
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PathPreviewJsonResult:
    """Parsed path preview JSON result."""

    config: AppConfig | None
    metadata: TrackMetadata | None
    file_extension: str | None
    errors: tuple[str, ...]


def parse_settings_json(payload: object) -> SettingsJsonResult:
    """Convert a JSON request body into a validated AppConfig."""
    if not isinstance(payload, Mapping):
        return SettingsJsonResult(config=None, errors=(REQUEST_BODY_ERROR,))

    payload_mapping = cast("Mapping[str, object]", payload)
    config_payload = payload_mapping.get(CONFIG_FIELD)
    if not isinstance(config_payload, Mapping):
        return SettingsJsonResult(config=None, errors=(CONFIG_FIELD_ERROR,))

    try:
        config = validate_config_data(_normalized_config(cast("Mapping[str, object]", config_payload)))
    except ConfigStoreValidationError as exc:
        return SettingsJsonResult(config=None, errors=exc.errors)
    return SettingsJsonResult(config=config, errors=())


def parse_path_preview_json(payload: object) -> PathPreviewJsonResult:
    """Convert a JSON request body into preview inputs."""
    settings_result = parse_settings_json(payload)
    if settings_result.config is None:
        return PathPreviewJsonResult(config=None, metadata=None, file_extension=None, errors=settings_result.errors)

    payload_mapping = cast("Mapping[str, object]", payload)
    metadata_result = _preview_metadata_from_payload(payload_mapping.get(METADATA_FIELD))
    file_extension_result = _preview_file_extension_from_payload(payload_mapping)
    return PathPreviewJsonResult(
        config=settings_result.config,
        metadata=metadata_result.metadata,
        file_extension=file_extension_result.file_extension,
        errors=metadata_result.errors + file_extension_result.errors,
    )


def _normalized_config(config_payload: Mapping[str, object]) -> dict[str, object]:
    normalized_config = dict(config_payload)
    paths_payload = normalized_config.get(PATHS_SECTION)
    if not isinstance(paths_payload, Mapping):
        return normalized_config

    normalized_paths = dict(cast("Mapping[str, object]", paths_payload))
    for path_key in (LIBRARY_KEY, INCOMING_KEY):
        if _is_empty_optional_path(normalized_paths.get(path_key)):
            _ = normalized_paths.pop(path_key, None)
    normalized_config[PATHS_SECTION] = normalized_paths
    return normalized_config


def _is_empty_optional_path(value: object) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


@dataclass(frozen=True, slots=True)
class _MetadataParseResult:
    metadata: TrackMetadata | None
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _FileExtensionParseResult:
    file_extension: str | None
    errors: tuple[str, ...]


def _preview_metadata_from_payload(value: object) -> _MetadataParseResult:
    if value is None:
        return _MetadataParseResult(metadata=None, errors=())
    if not isinstance(value, Mapping):
        return _MetadataParseResult(metadata=None, errors=("Preview metadata must be an object.",))

    metadata_payload = cast("Mapping[str, object]", value)
    int_errors: list[str] = []
    year = _optional_int(metadata_payload.get("year"), "metadata.year", int_errors)
    disc_number = _optional_int(metadata_payload.get("disc_number"), "metadata.disc_number", int_errors)
    track_number = _optional_int(metadata_payload.get("track_number"), "metadata.track_number", int_errors)
    if int_errors:
        return _MetadataParseResult(metadata=None, errors=tuple(int_errors))
    return _MetadataParseResult(
        metadata=TrackMetadata(
            title=_optional_text(metadata_payload.get("title")),
            artist=_optional_text(metadata_payload.get("artist")),
            album=_optional_text(metadata_payload.get("album")),
            album_artist=_optional_text(metadata_payload.get("album_artist")),
            year=year,
            disc_number=disc_number,
            track_number=track_number,
        ),
        errors=(),
    )


def _preview_file_extension_from_payload(payload: Mapping[str, object]) -> _FileExtensionParseResult:
    raw_extension = payload.get(FILE_EXTENSION_FIELD)
    metadata_payload = payload.get(METADATA_FIELD)
    if raw_extension is None and isinstance(metadata_payload, Mapping):
        raw_extension = cast("Mapping[str, object]", metadata_payload).get("extension")
    if raw_extension is None:
        return _FileExtensionParseResult(file_extension=None, errors=())
    if not isinstance(raw_extension, str):
        return _FileExtensionParseResult(file_extension=None, errors=("Preview file_extension must be a string.",))
    return _FileExtensionParseResult(file_extension=raw_extension, errors=())


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_int(value: object, field_name: str, errors: list[str]) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        if value.strip() == "":
            return None
        try:
            return int(value)
        except ValueError:
            errors.append(f"Preview {field_name} must be an integer.")
            return None
    errors.append(f"Preview {field_name} must be an integer.")
    return None
