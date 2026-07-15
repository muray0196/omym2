"""
Summary: Tests complete Settings projections and draft-only artist ID generation.
Why: Protects revision precedence, closed choices, deterministic changes, and no-save drafts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from omym2.config import DEFAULT_COMMAND_MODE
from omym2.domain.models.app_config import (
    AppConfig,
    ArtistIdConfig,
    ArtistNameConfig,
    CollisionConfig,
    CommandConfig,
    OrganizeConfig,
    PathPolicyConfig,
    PathsConfig,
)
from omym2.features.artist_ids.dto import GenerateArtistIdDraftRequest
from omym2.features.artist_ids.usecases.generate_artist_id_draft import (
    ArtistIdDraftValidationError,
    GenerateArtistIdDraftUseCase,
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

CONFIG_REVISION = "v1:settings-current"
SAVED_CONFIG_REVISION = "v1:settings-saved"
STALE_CONFIG_REVISION = "v1:settings-stale"
PERSISTED_CONFIG_ERROR = "Persisted Config is invalid."
UNSUPPORTED_CHOICE = "unsupported"
EXPECTED_PREVIEW_PATH = "Aimer/2024_Example-Album/1-03_Example-Song.flac"
SOURCE_ARTIST = "Existing Artist"
SOURCE_ARTIST_ID = "EXST"
NEW_ARTIST = "New Artist"
EXPECTED_NEW_ARTIST_ID = "NEWARTST"
NO_USABLE_ARTIST = "!!!"
UNSAFE_FALLBACK_ID = "A-B"
UNSAFE_MAX_LENGTH = 2


def test_get_settings_edit_preserves_invalid_recovery_revision_and_backend_choices() -> None:
    """Invalid raw storage returns a normal recovery draft without exposing TOML."""
    store = FakeConfigStore(state=ConfigSnapshotState.INVALID, errors=(PERSISTED_CONFIG_ERROR,))

    result = GetSettingsEditUseCase(SettingsPorts(store)).execute()

    assert not result.valid
    assert result.config == AppConfig()
    assert result.config_revision == CONFIG_REVISION
    assert [(issue.field, issue.message) for issue in result.validation_issues] == [("config", PERSISTED_CONFIG_ERROR)]
    assert result.choices.command_modes == (DEFAULT_COMMAND_MODE,)
    assert result.choices.path_placeholders[0] == "album_artist"
    assert result.preview.path == EXPECTED_PREVIEW_PATH


def test_validate_settings_candidate_reports_every_unchecked_closed_choice_in_field_order() -> None:
    """Feature validation covers closed values and non-empty strings outside nested domain checks."""
    artist_names = ArtistNameConfig()
    object.__setattr__(artist_names, "preferences", {"": "Display Name"})
    candidate = AppConfig(
        paths=PathsConfig(library=" "),
        add=CommandConfig(default_mode=UNSUPPORTED_CHOICE),
        organize=OrganizeConfig(default_mode=UNSUPPORTED_CHOICE),
        refresh=CommandConfig(default_mode=UNSUPPORTED_CHOICE),
        path_policy=PathPolicyConfig(template=" "),
        artist_ids=ArtistIdConfig(entries={"": "EMPTY"}),
        artist_names=artist_names,
        collision=CollisionConfig(
            on_target_exists=UNSUPPORTED_CHOICE,
            on_duplicate_hash=UNSUPPORTED_CHOICE,
            on_missing_metadata=UNSUPPORTED_CHOICE,
        ),
    )

    result = ValidateSettingsCandidateUseCase(SettingsPorts(FakeConfigStore())).execute(
        ValidateSettingsRequest(config=candidate, expected_config_revision=CONFIG_REVISION)
    )

    assert not result.valid
    assert [issue.field for issue in result.validation_issues] == [
        "paths.library",
        "add.default_mode",
        "organize.default_mode",
        "refresh.default_mode",
        "path_policy.template",
        "collision.on_target_exists",
        "collision.on_duplicate_hash",
        "collision.on_missing_metadata",
        "artist_ids.entries",
        "artist_names.preferences",
    ]


def test_settings_field_changes_are_scalar_and_deterministic_for_artist_entries() -> None:
    """Field changes use schema order followed by sorted per-artist entry keys."""
    before = AppConfig(
        paths=PathsConfig(library="/music/before"),
        artist_ids=ArtistIdConfig(entries={"Zulu": "Z", "Alpha": "A"}),
        artist_names=ArtistNameConfig(preferences={"Zulu": "Zulu Before", "Alpha": "Alpha"}),
    )
    after = AppConfig(
        paths=PathsConfig(library="/music/after"),
        artist_ids=ArtistIdConfig(entries={"Beta": "B", "Alpha": "A2"}),
        artist_names=ArtistNameConfig(preferences={"Beta": "Beta Display", "Alpha": "Alpha Display"}),
    )

    changes = settings_field_changes(before, after)

    assert [(change.field, change.before, change.after) for change in changes] == [
        ("paths.library", "/music/before", "/music/after"),
        ("artist_ids.entries.Alpha", "A", "A2"),
        ("artist_ids.entries.Beta", None, "B"),
        ("artist_ids.entries.Zulu", "Z", None),
        ("artist_names.preferences.Alpha", "Alpha", "Alpha Display"),
        ("artist_names.preferences.Beta", None, "Beta Display"),
        ("artist_names.preferences.Zulu", "Zulu Before", None),
    ]


def test_save_settings_candidate_checks_revision_then_validation_before_writing() -> None:
    """Stale and invalid candidates never reach ConfigStore.save."""
    store = FakeConfigStore()
    usecase = SaveSettingsCandidateUseCase(SettingsPorts(store))
    invalid = AppConfig(add=CommandConfig(default_mode=UNSUPPORTED_CHOICE))

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


def test_generate_artist_id_draft_preserves_and_generates_without_config_store() -> None:
    """Draft generation uses supplied entries and never has a persistence collaborator."""
    usecase = GenerateArtistIdDraftUseCase()

    result = usecase.execute(
        GenerateArtistIdDraftRequest(
            artist_names=(SOURCE_ARTIST, NEW_ARTIST, NEW_ARTIST),
            overwrite=False,
            artist_ids=ArtistIdConfig(entries={SOURCE_ARTIST: SOURCE_ARTIST_ID}),
        )
    )

    assert [(entry.source_artist, entry.artist_id, entry.overwritten) for entry in result.entries] == [
        (SOURCE_ARTIST, SOURCE_ARTIST_ID, False),
        (NEW_ARTIST, EXPECTED_NEW_ARTIST_ID, False),
    ]


def test_generate_artist_id_draft_honors_overwrite_and_rejects_unsafe_generated_entries() -> None:
    """Overwrite intent is explicit and an invalid truncated fallback never reaches the draft."""
    usecase = GenerateArtistIdDraftUseCase()

    overwritten = usecase.execute(
        GenerateArtistIdDraftRequest(
            artist_names=(SOURCE_ARTIST,),
            overwrite=True,
            artist_ids=ArtistIdConfig(entries={SOURCE_ARTIST: SOURCE_ARTIST_ID}),
        )
    )

    assert overwritten.entries[0].overwritten
    assert overwritten.entries[0].artist_id != SOURCE_ARTIST_ID
    with pytest.raises(ArtistIdDraftValidationError):
        _ = usecase.execute(
            GenerateArtistIdDraftRequest(
                artist_names=(NO_USABLE_ARTIST,),
                overwrite=False,
                artist_ids=ArtistIdConfig(max_length=UNSAFE_MAX_LENGTH, fallback_id=UNSAFE_FALLBACK_ID),
            )
        )


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
