"""
Summary: Tests settings usecases.
Why: Protects config feature boundaries before concrete UI settings work.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from omym2.domain.models.app_config import AppConfig, PathsConfig
from omym2.domain.services.config_fingerprint import calculate_config_fingerprint
from omym2.features.common_ports import (
    ConfigRevisionMismatchError,
    ConfigSnapshot,
    ConfigSnapshotState,
    ConfigStoreValidationError,
)
from omym2.features.settings.dto import SaveSettingsRequest, ValidateSettingsRequest
from omym2.features.settings.ports import SettingsPorts
from omym2.features.settings.usecases.load_settings import LoadSettingsUseCase
from omym2.features.settings.usecases.save_settings import SaveSettingsUseCase
from omym2.features.settings.usecases.validate_settings import ValidateSettingsUseCase

EXPECTED_ERROR = "expected config validation error"
LIBRARY_PATH = "/music/library"
CONFIG_REVISION = "v1:current"
SAVED_CONFIG_REVISION = "v1:saved"
STALE_CONFIG_REVISION = "v1:stale"


def test_settings_usecases_load_and_save_with_raw_config_revisions() -> None:
    """Load exposes raw identity and save returns the atomically installed revision."""
    config = AppConfig(paths=PathsConfig(library=LIBRARY_PATH))
    store = FakeConfigStore(config=config)
    ports = SettingsPorts(config_store=store)

    loaded = LoadSettingsUseCase(ports).execute()

    assert loaded.state is ConfigSnapshotState.VALID
    assert loaded.config == config
    assert loaded.config_revision == CONFIG_REVISION
    assert loaded.errors == ()

    saved = SaveSettingsUseCase(ports).execute(
        SaveSettingsRequest(config=AppConfig(), expected_config_revision=loaded.config_revision)
    )

    assert store.saved_config == AppConfig()
    assert saved.config == AppConfig()
    assert saved.config_revision == SAVED_CONFIG_REVISION


def test_validate_settings_returns_hash_for_valid_config() -> None:
    """Candidate validation succeeds when the caller's raw edit base remains current."""
    config = AppConfig()
    result = ValidateSettingsUseCase(SettingsPorts(config_store=FakeConfigStore())).execute(
        ValidateSettingsRequest(config=config, expected_config_revision=CONFIG_REVISION)
    )

    assert result.valid
    assert result.errors == ()
    assert result.config_revision == CONFIG_REVISION
    assert result.config_hash == calculate_config_fingerprint(config)


def test_load_settings_returns_invalid_recovery_state_with_revision() -> None:
    """Invalid persisted Config still yields a recovery draft and opaque revision."""
    result = LoadSettingsUseCase(
        SettingsPorts(
            config_store=FakeConfigStore(
                state=ConfigSnapshotState.INVALID,
                errors=(EXPECTED_ERROR,),
            )
        )
    ).execute()

    assert result.state is ConfigSnapshotState.INVALID
    assert result.config == AppConfig()
    assert result.errors == (EXPECTED_ERROR,)
    assert result.config_revision == CONFIG_REVISION


def test_validate_settings_rejects_stale_raw_revision() -> None:
    """Candidate validation never reports against a Config state other than its edit base."""
    usecase = ValidateSettingsUseCase(SettingsPorts(config_store=FakeConfigStore()))

    with pytest.raises(ConfigRevisionMismatchError) as exc_info:
        _ = usecase.execute(ValidateSettingsRequest(config=AppConfig(), expected_config_revision=STALE_CONFIG_REVISION))

    assert exc_info.value.expected_config_revision == STALE_CONFIG_REVISION
    assert exc_info.value.actual_config_revision == CONFIG_REVISION


@dataclass(slots=True)
class FakeConfigStore:
    """ConfigStore fake for settings usecase tests."""

    config: AppConfig = field(default_factory=AppConfig)
    state: ConfigSnapshotState = ConfigSnapshotState.VALID
    config_revision: str = CONFIG_REVISION
    errors: tuple[str, ...] = ()
    saved_config: AppConfig | None = None

    def read_snapshot(self) -> ConfigSnapshot:
        """Return configured raw-state recovery data."""
        return ConfigSnapshot(
            state=self.state,
            config=self.config,
            config_revision=self.config_revision,
            errors=self.errors,
        )

    def load(self) -> AppConfig:
        """Return config or raise configured validation errors."""
        if self.errors:
            raise ConfigStoreValidationError(self.errors)
        return self.config

    def save(self, config: AppConfig, *, expected_config_revision: str) -> ConfigSnapshot:
        """Record a save only for the current raw revision."""
        if expected_config_revision != self.config_revision:
            raise ConfigRevisionMismatchError(expected_config_revision, self.config_revision)
        self.saved_config = config
        self.config = config
        self.state = ConfigSnapshotState.VALID
        self.config_revision = SAVED_CONFIG_REVISION
        self.errors = ()
        return self.read_snapshot()
