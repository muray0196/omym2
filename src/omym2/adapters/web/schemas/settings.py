"""
Summary: Defines typed Settings, preview, and draft artist-ID Web resources.
Why: Keeps the complete Config edit contract generated and independent from TOML I/O.
"""

from __future__ import annotations

from pydantic import field_validator

from omym2.adapters.web.schemas.api_errors import ApiError, ApiModel
from omym2.domain.models.accepted_artist_name import (
    ArtistNameProvider,  # noqa: TC001  # Pydantic resolves this enum at runtime.
    SelectedArtistNameKind,  # noqa: TC001  # Pydantic resolves this enum at runtime.
)
from omym2.domain.models.app_config import (
    AppConfig,
    ArtistIdConfig,
    CollisionConfig,
    CommandConfig,
    CompanionsConfig,
    HashingConfig,
    LoggingConfig,
    MetadataConfig,
    MusicBrainzConfig,
    OrganizeConfig,
    PathPolicyConfig,
    PathsConfig,
    UnprocessedConfig,
)
from omym2.domain.models.track_metadata import TrackMetadata

EMPTY_CONFIG_REVISION_MESSAGE = "expected_config_revision must not be empty."


class PathsConfigResource(ApiModel):
    """Editable Library and Incoming defaults."""

    library: str | None
    incoming: str | None


class CommandConfigResource(ApiModel):
    """Plan-first command defaults retained in Config."""

    default_mode: str
    auto_apply: bool


class PathPolicyConfigResource(ApiModel):
    """Editable canonical-path policy."""

    template: str
    unknown_artist: str
    unknown_album: str
    sanitize: bool
    max_filename_length: int
    disc_number_style: str
    disc_number_condition: str

    def to_domain(self) -> PathPolicyConfig:
        """Validate and convert the self-contained PathPolicy draft."""
        return PathPolicyConfig(
            template=self.template,
            unknown_artist=self.unknown_artist,
            unknown_album=self.unknown_album,
            sanitize=self.sanitize,
            max_filename_length=self.max_filename_length,
            disc_number_style=self.disc_number_style,
            disc_number_condition=self.disc_number_condition,
        )


class ArtistIdConfigResource(ApiModel):
    """Tunables for automatic internal artist-ID generation."""

    max_length: int
    fallback_id: str

    def to_domain(self) -> ArtistIdConfig:
        """Validate and convert the self-contained artist-ID draft."""
        return ArtistIdConfig(
            max_length=self.max_length,
            fallback_id=self.fallback_id,
        )


class MetadataConfigResource(ApiModel):
    """Editable metadata requirements and album-year policy."""

    prefer_album_artist: bool
    require_title: bool
    require_artist: bool
    require_album: bool
    album_year_resolution: str


class CollisionConfigResource(ApiModel):
    """Editable plan-time collision decisions."""

    on_target_exists: str
    on_duplicate_hash: str
    on_missing_metadata: str


class MusicBrainzConfigResource(ApiModel):
    """Persisted MusicBrainz enablement, identity, request, and cache controls."""

    enabled: bool
    application_name: str
    contact: str
    timeout_seconds: float
    retry_limit: int
    rate_limit_seconds: float
    cache_policy: str

    def to_domain(self) -> MusicBrainzConfig:
        """Validate and convert the complete MusicBrainz settings draft."""
        return MusicBrainzConfig(
            enabled=self.enabled,
            application_name=self.application_name,
            contact=self.contact,
            timeout_seconds=self.timeout_seconds,
            retry_limit=self.retry_limit,
            rate_limit_seconds=self.rate_limit_seconds,
            cache_policy=self.cache_policy,
        )


class HashingConfigResource(ApiModel):
    """Persisted streaming content-hash controls."""

    read_chunk_size_bytes: int

    def to_domain(self) -> HashingConfig:
        """Validate and convert the complete hashing settings draft."""
        return HashingConfig(read_chunk_size_bytes=self.read_chunk_size_bytes)


class LoggingConfigResource(ApiModel):
    """Persisted logging destination, severity, rotation, and retention controls."""

    destination: str | None
    level: str
    rotation_max_bytes: int
    retention_files: int

    def to_domain(self) -> LoggingConfig:
        """Validate and convert the complete logging settings draft."""
        return LoggingConfig(
            destination=self.destination,
            level=self.level,
            rotation_max_bytes=self.rotation_max_bytes,
            retention_files=self.retention_files,
        )


class CompanionsConfigResource(ApiModel):
    """Persisted opt-in control for companion lyrics and artwork."""

    enabled: bool

    def to_domain(self) -> CompanionsConfig:
        """Convert the complete companion settings draft."""
        return CompanionsConfig(enabled=self.enabled)


class UnprocessedConfigResource(ApiModel):
    """Persisted controls for reviewed unprocessed-file collection."""

    enabled: bool
    directory: str
    result_preview_limit: int

    def to_domain(self) -> UnprocessedConfig:
        """Validate and convert the complete unprocessed settings draft."""
        return UnprocessedConfig(
            enabled=self.enabled,
            directory=self.directory,
            result_preview_limit=self.result_preview_limit,
        )


class AppConfigResource(ApiModel):
    """Complete supported AppConfig representation."""

    version: int
    paths: PathsConfigResource
    add: CommandConfigResource
    organize: CommandConfigResource
    refresh: CommandConfigResource
    path_policy: PathPolicyConfigResource
    artist_ids: ArtistIdConfigResource
    metadata: MetadataConfigResource
    collision: CollisionConfigResource
    musicbrainz: MusicBrainzConfigResource
    hashing: HashingConfigResource
    logging: LoggingConfigResource
    companions: CompanionsConfigResource
    unprocessed: UnprocessedConfigResource

    @classmethod
    def from_domain(cls, config: AppConfig) -> AppConfigResource:
        """Project one domain Config without losing hidden persisted fields."""
        return cls(
            version=config.version,
            paths=PathsConfigResource(library=config.paths.library, incoming=config.paths.incoming),
            add=_command_resource(config.add),
            organize=_command_resource(config.organize),
            refresh=_command_resource(config.refresh),
            path_policy=PathPolicyConfigResource(
                template=config.path_policy.template,
                unknown_artist=config.path_policy.unknown_artist,
                unknown_album=config.path_policy.unknown_album,
                sanitize=config.path_policy.sanitize,
                max_filename_length=config.path_policy.max_filename_length,
                disc_number_style=config.path_policy.disc_number_style,
                disc_number_condition=config.path_policy.disc_number_condition,
            ),
            artist_ids=ArtistIdConfigResource(
                max_length=config.artist_ids.max_length,
                fallback_id=config.artist_ids.fallback_id,
            ),
            metadata=MetadataConfigResource(
                prefer_album_artist=config.metadata.prefer_album_artist,
                require_title=config.metadata.require_title,
                require_artist=config.metadata.require_artist,
                require_album=config.metadata.require_album,
                album_year_resolution=config.metadata.album_year_resolution,
            ),
            collision=CollisionConfigResource(
                on_target_exists=config.collision.on_target_exists,
                on_duplicate_hash=config.collision.on_duplicate_hash,
                on_missing_metadata=config.collision.on_missing_metadata,
            ),
            musicbrainz=MusicBrainzConfigResource(
                enabled=config.musicbrainz.enabled,
                application_name=config.musicbrainz.application_name,
                contact=config.musicbrainz.contact,
                timeout_seconds=config.musicbrainz.timeout_seconds,
                retry_limit=config.musicbrainz.retry_limit,
                rate_limit_seconds=config.musicbrainz.rate_limit_seconds,
                cache_policy=config.musicbrainz.cache_policy,
            ),
            hashing=HashingConfigResource(read_chunk_size_bytes=config.hashing.read_chunk_size_bytes),
            logging=LoggingConfigResource(
                destination=config.logging.destination,
                level=config.logging.level,
                rotation_max_bytes=config.logging.rotation_max_bytes,
                retention_files=config.logging.retention_files,
            ),
            companions=CompanionsConfigResource(enabled=config.companions.enabled),
            unprocessed=UnprocessedConfigResource(
                enabled=config.unprocessed.enabled,
                directory=config.unprocessed.directory,
                result_preview_limit=config.unprocessed.result_preview_limit,
            ),
        )

    def to_domain(self) -> AppConfig:
        """Validate and convert the complete HTTP draft to domain Config."""
        return AppConfig(
            version=self.version,
            paths=PathsConfig(library=self.paths.library, incoming=self.paths.incoming),
            add=CommandConfig(default_mode=self.add.default_mode, auto_apply=self.add.auto_apply),
            organize=OrganizeConfig(
                default_mode=self.organize.default_mode,
                auto_apply=self.organize.auto_apply,
            ),
            refresh=CommandConfig(
                default_mode=self.refresh.default_mode,
                auto_apply=self.refresh.auto_apply,
            ),
            path_policy=self.path_policy.to_domain(),
            artist_ids=self.artist_ids.to_domain(),
            metadata=MetadataConfig(
                prefer_album_artist=self.metadata.prefer_album_artist,
                require_title=self.metadata.require_title,
                require_artist=self.metadata.require_artist,
                require_album=self.metadata.require_album,
                album_year_resolution=self.metadata.album_year_resolution,
            ),
            collision=CollisionConfig(
                on_target_exists=self.collision.on_target_exists,
                on_duplicate_hash=self.collision.on_duplicate_hash,
                on_missing_metadata=self.collision.on_missing_metadata,
            ),
            musicbrainz=self.musicbrainz.to_domain(),
            hashing=self.hashing.to_domain(),
            logging=self.logging.to_domain(),
            companions=self.companions.to_domain(),
            unprocessed=self.unprocessed.to_domain(),
        )


class SettingsChoices(ApiModel):
    """Backend-owned closed choices used by Settings controls."""

    command_modes: tuple[str, ...]
    disc_number_styles: tuple[str, ...]
    disc_number_conditions: tuple[str, ...]
    album_year_resolutions: tuple[str, ...]
    target_exists_policies: tuple[str, ...]
    duplicate_hash_policies: tuple[str, ...]
    missing_metadata_policies: tuple[str, ...]
    musicbrainz_cache_policies: tuple[str, ...]
    logging_levels: tuple[str, ...]
    unprocessed_result_preview_limit_min: int
    unprocessed_result_preview_limit_max: int
    path_placeholders: tuple[str, ...]


class SettingsValidation(ApiModel):
    """Candidate or persisted Config validation evidence."""

    valid: bool
    errors: tuple[ApiError, ...]


class PathPreview(ApiModel):
    """One rendered relative path or typed draft errors."""

    path: str | None
    errors: tuple[ApiError, ...]


type SettingsChangeValue = str | int | float | bool | None


class SettingsChange(ApiModel):
    """One deterministic field-level Config difference."""

    field: str
    before: SettingsChangeValue
    after: SettingsChangeValue


class ArtistNameMappingEntry(ApiModel):
    """One editable original-to-English artist-name mapping."""

    source_name: str
    english_name: str
    source: ArtistNameProvider
    selected_name_kind: SelectedArtistNameKind | None
    selected_locale: str | None


class ArtistNameMappingsData(ApiModel):
    """Revisioned complete artist-name mapping snapshot."""

    entries: tuple[ArtistNameMappingEntry, ...]
    revision: str


class SettingsData(ApiModel):
    """Current recovery-capable Settings edit state."""

    config: AppConfigResource
    config_revision: str
    choices: SettingsChoices
    validation: SettingsValidation
    preview: PathPreview
    artist_name_mappings: ArtistNameMappingsData


class SaveArtistNameMappingsRequestResource(ApiModel):
    """Complete mapping candidate tied to the snapshot the user edited."""

    entries: dict[str, str]
    expected_revision: str

    @field_validator("expected_revision")
    @classmethod
    def validate_revision(cls, value: str) -> str:
        """Reject an empty mapping compare-and-set identity."""
        if value.strip() == "":
            raise ValueError(EMPTY_CONFIG_REVISION_MESSAGE)
        return value


class SettingsCandidateRequest(ApiModel):
    """Complete candidate Config tied to the caller's edit base."""

    config: AppConfigResource
    expected_config_revision: str

    @field_validator("expected_config_revision")
    @classmethod
    def validate_revision(cls, value: str) -> str:
        """Reject an empty compare-and-set identity before feature execution."""
        if value.strip() == "":
            raise ValueError(EMPTY_CONFIG_REVISION_MESSAGE)
        return value


class SettingsCandidateData(ApiModel):
    """Validation or save result for one Settings candidate."""

    config: AppConfigResource
    config_revision: str
    changes: tuple[SettingsChange, ...]
    validation: SettingsValidation
    preview: PathPreview


class TrackMetadataResource(ApiModel):
    """Self-contained sample metadata used only for PathPolicy preview."""

    title: str | None = None
    artist: str | None = None
    album: str | None = None
    album_artist: str | None = None
    genre: str | None = None
    year: int | None = None
    track_number: int | None = None
    track_total: int | None = None
    disc_number: int | None = None
    disc_total: int | None = None

    def to_domain(self) -> TrackMetadata:
        """Convert sample metadata to the pure domain value."""
        return TrackMetadata(
            title=self.title,
            artist=self.artist,
            album=self.album,
            album_artist=self.album_artist,
            genre=self.genre,
            year=self.year,
            track_number=self.track_number,
            track_total=self.track_total,
            disc_number=self.disc_number,
            disc_total=self.disc_total,
        )


class PathPreviewRequest(ApiModel):
    """Self-contained PathPolicy preview input."""

    path_policy: PathPolicyConfigResource
    artist_ids: ArtistIdConfigResource
    metadata: TrackMetadataResource
    file_extension: str


def _command_resource(config: CommandConfig) -> CommandConfigResource:
    return CommandConfigResource(default_mode=config.default_mode, auto_apply=config.auto_apply)
