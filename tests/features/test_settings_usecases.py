"""
Summary: Tests settings usecases.
Why: Protects config feature boundaries before concrete UI settings work.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from omym2.domain.models.app_config import AppConfig, UiConfig
from omym2.domain.services.config_fingerprint import calculate_config_fingerprint
from omym2.features.common_ports import ConfigStoreValidationError
from omym2.features.settings.dto import SaveSettingsRequest
from omym2.features.settings.ports import SettingsPorts
from omym2.features.settings.usecases.load_settings import LoadSettingsUseCase
from omym2.features.settings.usecases.save_settings import SaveSettingsUseCase
from omym2.features.settings.usecases.validate_settings import ValidateSettingsUseCase

EXPECTED_ERROR = "expected config validation error"
UI_THEME_DARK = "dark"


def test_settings_usecases_load_and_save_through_config_store() -> None:
    """Load and save settings depend only on the ConfigStore port."""
    config = AppConfig(ui=UiConfig(theme=UI_THEME_DARK))
    store = FakeConfigStore(config=config)
    ports = SettingsPorts(config_store=store)

    assert LoadSettingsUseCase(ports).execute() == config

    SaveSettingsUseCase(ports).execute(SaveSettingsRequest(config=AppConfig()))

    assert store.saved_config == AppConfig()


def test_validate_settings_returns_hash_for_valid_config() -> None:
    """Validation succeeds with a config hash for valid settings."""
    config = AppConfig()
    result = ValidateSettingsUseCase(SettingsPorts(config_store=FakeConfigStore(config=config))).execute()

    assert result.valid
    assert result.errors == ()
    assert result.config_hash == calculate_config_fingerprint(config)


def test_validate_settings_returns_errors_without_raising() -> None:
    """Validation converts ConfigStore validation failures into result data."""
    result = ValidateSettingsUseCase(SettingsPorts(config_store=FakeConfigStore(errors=(EXPECTED_ERROR,)))).execute()

    assert not result.valid
    assert result.errors == (EXPECTED_ERROR,)
    assert result.config_hash is None


@dataclass(slots=True)
class FakeConfigStore:
    """ConfigStore fake for settings usecase tests."""

    config: AppConfig = field(default_factory=AppConfig)
    errors: tuple[str, ...] = ()
    saved_config: AppConfig | None = None

    def load(self) -> AppConfig:
        """Return config or raise configured validation errors."""
        if self.errors:
            raise ConfigStoreValidationError(self.errors)
        return self.config

    def save(self, config: AppConfig) -> None:
        """Record the saved config."""
        self.saved_config = config
