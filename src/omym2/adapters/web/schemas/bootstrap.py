"""
Summary: Defines the bundled Web API Bootstrap resource.
Why: Starts the SPA with typed recovery, readiness, and polling policy data.
"""

from __future__ import annotations

from uuid import UUID  # noqa: TC003  # Pydantic resolves UUID schema types at runtime.

from omym2.adapters.web.schemas.api_errors import ApiError, ApiModel
from omym2.adapters.web.schemas.libraries import (
    LibraryResource,  # noqa: TC001  # Pydantic resolves nested schema types at runtime.
)


class ConfigValidationResource(ApiModel):
    """Current Config validity and opaque raw-storage revision."""

    valid: bool
    config_revision: str | None
    errors: tuple[ApiError, ...]


class RuntimeCapabilities(ApiModel):
    """Backend-authoritative application runtime availability."""

    can_read_state: bool
    can_change_settings: bool
    can_start_operations: bool
    can_start_organize: bool
    disabled_reasons: tuple[ApiError, ...]


class OperationPollingPolicy(ApiModel):
    """Polling policy serialized from backend-owned tunables."""

    initial_ms: int
    backoff_factor: float
    max_ms: int


class BootstrapData(ApiModel):
    """Initial application state returned even when recovery is required."""

    app_version: str
    csrf_token: str
    status_catalog_version: int
    active_library: LibraryResource | None
    library_diagnostics: tuple[ApiError, ...]
    config_validation: ConfigValidationResource
    runtime_capabilities: RuntimeCapabilities
    operation_polling: OperationPollingPolicy
    active_operation_id: UUID | None
