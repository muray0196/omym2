"""
Summary: Tests complete Settings projections and revision-safe Config saves.
Why: Protects revision precedence, closed choices, and deterministic field changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from omym2.config import (
    UNPROCESSED_RESULT_PREVIEW_LIMIT_MAX,
    UNPROCESSED_RESULT_PREVIEW_LIMIT_MIN,
)
from omym2.domain.models.app_config import (
    AppConfig,
    ArtistIdConfig,
    CollisionConfig,
    CompanionsConfig,
    HashingConfig,
    LoggingConfig,
    MusicBrainzConfig,
    PathPolicyConfig,
    PathsConfig,
    UnprocessedConfig,
)
from omym2.features.common_ports import (
    ConfigRevisionMismatchError,
    ConfigSnapshot,
    ConfigSnapshotState,
)
from omym2.features.settings.dto import SaveSettingsRequest, ValidateSettingsRequest
from omym2.features.settings.ports import SettingsPorts
from omym2.features.settings.settings_projection import settings_field_changes
from omym2.features.settings.usecases.get_settings_edit import GetSettingsEditUseCase
from omym2.features.settings.usecases.save_settings_candidate import (
    SaveSettingsCandidateUseCase,
    SettingsCandidateValidationError,
)
from omym2.features.settings.usecases.validate_settings_candidate import ValidateSettingsCandidateUseCase
from tests.fakes.runtime import MappingArtistNameResolver

CONFIG_REVISION = "v1:settings-current"
SAVED_CONFIG_REVISION = "v1:settings-saved"
STALE_CONFIG_REVISION = "v1:settings-stale"
PERSISTED_CONFIG_ERROR = "Persisted Config is invalid."
UNSUPPORTED_CHOICE = "unsupported"
EXPECTED_PREVIEW_PATH = "Aimer/2024_Example-Album/1-03_Example-Song.flac"
SOURCE_ARTIST = "Existing Artist"
SOURCE_ARTIST_ID = "EXST"
NO_USABLE_ARTIST = "!!!"
JAPANESE_ARTIST = "宇多田ヒカル"
PREFERRED_JAPANESE_ARTIST = "Hikaru Utada"
UNSAFE_FALLBACK_ID = "A-B"
UNSAFE_MAX_LENGTH = 2
UNPROCESSED_PREVIEW_LIMIT = 250


def test_get_settings_edit_preserves_invalid_recovery_revision_and_backend_choices() -> None:
    """Invalid raw storage returns a normal recovery draft without exposing TOML."""
    store = FakeConfigStore(state=ConfigSnapshotState.INVALID, errors=(PERSISTED_CONFIG_ERROR,))

    result = GetSettingsEditUseCase(_settings_ports(store)).execute()

    assert not result.valid
    assert result.config == AppConfig()
    assert result.config_revision == CONFIG_REVISION
    assert [(issue.field, issue.message) for issue in result.validation_issues] == [("config", PERSISTED_CONFIG_ERROR)]
    assert result.choices.logging_levels == ("CRITICAL", "DEBUG", "ERROR", "INFO", "WARNING")
    assert result.choices.unprocessed_result_preview_limit_min == UNPROCESSED_RESULT_PREVIEW_LIMIT_MIN
    assert result.choices.unprocessed_result_preview_limit_max == UNPROCESSED_RESULT_PREVIEW_LIMIT_MAX
    assert result.choices.path_placeholders[0] == "album_artist"
    assert result.preview.path == EXPECTED_PREVIEW_PATH


def test_validate_settings_candidate_reports_every_unchecked_closed_choice_in_field_order() -> None:
    """Feature validation covers closed values and non-empty strings outside nested domain checks."""
    logging = LoggingConfig()
    object.__setattr__(logging, "level", UNSUPPORTED_CHOICE)
    candidate = AppConfig(
        paths=PathsConfig(library=" "),
        path_policy=PathPolicyConfig(template=" "),
        collision=CollisionConfig(
            on_target_exists=UNSUPPORTED_CHOICE,
            on_duplicate_hash=UNSUPPORTED_CHOICE,
            on_missing_metadata=UNSUPPORTED_CHOICE,
        ),
        logging=logging,
    )

    result = ValidateSettingsCandidateUseCase(_settings_ports(FakeConfigStore())).execute(
        ValidateSettingsRequest(config=candidate, expected_config_revision=CONFIG_REVISION)
    )

    assert not result.valid
    assert [issue.field for issue in result.validation_issues] == [
        "paths.library",
        "path_policy.template",
        "collision.on_target_exists",
        "collision.on_duplicate_hash",
        "collision.on_missing_metadata",
        "logging.level",
    ]


def test_settings_field_changes_are_scalar_and_deterministic() -> None:
    """Field changes use stable schema order."""
    before = AppConfig(
        paths=PathsConfig(library="/music/before"),
        artist_ids=ArtistIdConfig(max_length=8),
    )
    after = AppConfig(
        paths=PathsConfig(library="/music/after"),
        artist_ids=ArtistIdConfig(max_length=10),
    )

    changes = settings_field_changes(before, after)

    assert [(change.field, change.before, change.after) for change in changes] == [
        ("paths.library", "/music/before", "/music/after"),
        ("artist_ids.max_length", 8, 10),
    ]


def test_settings_field_changes_include_every_runtime_control_in_schema_order() -> None:
    """Operational settings remain reviewable scalar changes, including floating-point values."""
    before = AppConfig()
    musicbrainz = MusicBrainzConfig(
        enabled=False,
        application_name="OMYM2 Test",
        contact="test@example.invalid",
        timeout_seconds=2.5,
        retry_limit=2,
        rate_limit_seconds=1.5,
    )
    after = AppConfig(
        musicbrainz=musicbrainz,
        hashing=HashingConfig(read_chunk_size_bytes=2_048),
        logging=LoggingConfig(
            destination="logs/test.log",
            level="DEBUG",
            rotation_max_bytes=4_096,
            retention_files=5,
        ),
        companions=CompanionsConfig(enabled=True),
        unprocessed=UnprocessedConfig(
            enabled=True,
            directory="Review Later",
            result_preview_limit=UNPROCESSED_PREVIEW_LIMIT,
        ),
    )

    changes = settings_field_changes(before, after)

    assert [(change.field, change.after) for change in changes] == [
        ("musicbrainz.enabled", False),
        ("musicbrainz.application_name", "OMYM2 Test"),
        ("musicbrainz.contact", "test@example.invalid"),
        ("musicbrainz.timeout_seconds", 2.5),
        ("musicbrainz.retry_limit", 2),
        ("musicbrainz.rate_limit_seconds", 1.5),
        ("hashing.read_chunk_size_bytes", 2_048),
        ("logging.destination", "logs/test.log"),
        ("logging.level", "DEBUG"),
        ("logging.rotation_max_bytes", 4_096),
        ("logging.retention_files", 5),
        ("companions.enabled", True),
        ("unprocessed.enabled", True),
        ("unprocessed.directory", "Review Later"),
        ("unprocessed.result_preview_limit", UNPROCESSED_PREVIEW_LIMIT),
    ]


def test_save_settings_candidate_checks_revision_then_validation_before_writing() -> None:
    """Stale and invalid candidates never reach ConfigStore.save."""
    store = FakeConfigStore()
    usecase = SaveSettingsCandidateUseCase(_settings_ports(store))
    invalid = AppConfig(collision=CollisionConfig(on_target_exists=UNSUPPORTED_CHOICE))

    with pytest.raises(ConfigRevisionMismatchError):
        _ = usecase.execute(SaveSettingsRequest(invalid, STALE_CONFIG_REVISION))
    with pytest.raises(SettingsCandidateValidationError):
        _ = usecase.execute(SaveSettingsRequest(invalid, CONFIG_REVISION))

    assert store.save_count == 0
    valid = AppConfig(paths=PathsConfig(library="/music/library"))
    result = usecase.execute(SaveSettingsRequest(valid, CONFIG_REVISION))
    assert store.save_count == 1
    assert result.config_revision == SAVED_CONFIG_REVISION
    assert [change.field for change in result.changes] == ["paths.library"]


@dataclass(slots=True)
class FakeConfigStore:
    """Revision-aware ConfigStore fake for Settings projection tests."""

    config: AppConfig = field(default_factory=AppConfig)
    state: ConfigSnapshotState = ConfigSnapshotState.VALID
    errors: tuple[str, ...] = ()
    config_revision: str = CONFIG_REVISION
    save_count: int = 0

    def read_snapshot(self) -> ConfigSnapshot:
        """Return the configured raw-state projection."""
        return ConfigSnapshot(
            state=self.state,
            config=self.config,
            config_revision=self.config_revision,
            errors=self.errors,
        )

    def load(self) -> AppConfig:
        """Return the current recovery Config."""
        return self.config

    def save(self, config: AppConfig, *, expected_config_revision: str) -> ConfigSnapshot:
        """Apply a deterministic CAS save for valid test calls."""
        if expected_config_revision != self.config_revision:
            raise ConfigRevisionMismatchError(expected_config_revision, self.config_revision)
        self.save_count += 1
        self.config = config
        self.config_revision = SAVED_CONFIG_REVISION
        self.state = ConfigSnapshotState.VALID
        self.errors = ()
        return self.read_snapshot()


def _settings_ports(store: FakeConfigStore) -> SettingsPorts:
    return SettingsPorts(store, MappingArtistNameResolver())
