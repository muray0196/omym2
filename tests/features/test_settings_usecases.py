"""
Summary: Tests current Settings load behavior.
Why: Protects recovery-capable Config loading beside Candidate save/validation tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from omym2.domain.models.app_config import AppConfig, PathsConfig
from omym2.features.common_ports import (
    ConfigRevisionMismatchError,
    ConfigSnapshot,
    ConfigSnapshotState,
    ConfigStoreValidationError,
)
from omym2.features.settings.ports import SettingsPorts
from omym2.features.settings.usecases.load_settings import LoadSettingsUseCase
from tests.fakes.runtime import MappingArtistNameResolver

EXPECTED_ERROR = "expected config validation error"
LIBRARY_PATH = "/music/library"
CONFIG_REVISION = "v1:current"
SAVED_CONFIG_REVISION = "v1:saved"


def test_load_settings_exposes_config_and_raw_revision() -> None:
    """Load exposes the valid Config and its opaque raw-storage identity."""
    config = AppConfig(paths=PathsConfig(library=LIBRARY_PATH))

    loaded = LoadSettingsUseCase(
        SettingsPorts(
            config_store=FakeConfigStore(config=config),
            artist_name_resolver=MappingArtistNameResolver(),
        )
    ).execute()

    assert loaded.state is ConfigSnapshotState.VALID
    assert loaded.config == config
    assert loaded.config_revision == CONFIG_REVISION
    assert loaded.errors == ()


def test_load_settings_returns_invalid_recovery_state_with_revision() -> None:
    """Invalid persisted Config still yields a recovery draft and opaque revision."""
    result = LoadSettingsUseCase(
        SettingsPorts(
            config_store=FakeConfigStore(
                state=ConfigSnapshotState.INVALID,
                errors=(EXPECTED_ERROR,),
            ),
            artist_name_resolver=MappingArtistNameResolver(),
        )
    ).execute()

    assert result.state is ConfigSnapshotState.INVALID
    assert result.config == AppConfig()
    assert result.errors == (EXPECTED_ERROR,)
    assert result.config_revision == CONFIG_REVISION


@dataclass(slots=True)
class FakeConfigStore:
    """ConfigStore fake for Settings loading."""

    config: AppConfig = field(default_factory=AppConfig)
    state: ConfigSnapshotState = ConfigSnapshotState.VALID
    config_revision: str = CONFIG_REVISION
    errors: tuple[str, ...] = ()

    def read_snapshot(self) -> ConfigSnapshot:
        """Return configured raw-state recovery data."""
        return ConfigSnapshot(
            state=self.state,
            config=self.config,
            config_revision=self.config_revision,
            errors=self.errors,
        )

    def load(self) -> AppConfig:
        """Return Config or raise configured validation errors."""
        if self.errors:
            raise ConfigStoreValidationError(self.errors)
        return self.config

    def save(self, config: AppConfig, *, expected_config_revision: str) -> ConfigSnapshot:
        """Persist a matching revision if another test reuses this fake."""
        if expected_config_revision != self.config_revision:
            raise ConfigRevisionMismatchError(expected_config_revision, self.config_revision)
        self.config = config
        self.state = ConfigSnapshotState.VALID
        self.config_revision = SAVED_CONFIG_REVISION
        self.errors = ()
        return self.read_snapshot()
