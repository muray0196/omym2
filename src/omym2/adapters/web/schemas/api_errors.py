"""
Summary: Defines typed Web API errors and remediation.
Why: Gives every API failure one closed machine-readable envelope contract.
"""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict
from pydantic.experimental.missing_sentinel import MISSING


class ApiModel(BaseModel):
    """Strict immutable base for Web API request and response models."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)


class ApiErrorCode(StrEnum):
    """Closed top-level Web API error catalog."""

    INVALID_JSON = "invalid_json"
    CSRF_INVALID = "csrf_invalid"
    API_NOT_FOUND = "api_not_found"
    LIBRARY_NOT_FOUND = "library_not_found"
    TRACK_NOT_FOUND = "track_not_found"
    PLAN_NOT_FOUND = "plan_not_found"
    RUN_NOT_FOUND = "run_not_found"
    OPERATION_NOT_FOUND = "operation_not_found"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    CONFIG_INVALID = "config_invalid"
    CONFIG_CHANGED = "config_changed"
    ARTIST_NAME_MAPPINGS_CHANGED = "artist_name_mappings_changed"
    OPERATION_IN_PROGRESS = "operation_in_progress"
    IDEMPOTENCY_KEY_REUSED = "idempotency_key_reused"
    LIBRARY_SELECTION_AMBIGUOUS = "library_selection_ambiguous"
    LIBRARY_UNREGISTERED = "library_unregistered"
    LIBRARY_STALE = "library_stale"
    LIBRARY_BLOCKED = "library_blocked"
    PLAN_NOT_READY = "plan_not_ready"
    LIBRARY_ROOT_CHANGED = "library_root_changed"
    RUN_NOT_TERMINAL = "run_not_terminal"
    NOTHING_TO_UNDO = "nothing_to_undo"
    UNDO_REFRESH_METADATA_UNSUPPORTED = "undo_refresh_metadata_unsupported"
    ALREADY_UNDONE_OR_IN_PROGRESS = "already_undone_or_in_progress"
    PENDING_FILE_EVENT_REQUIRES_REVIEW = "pending_file_event_requires_review"
    OPERATION_EXPIRED = "operation_expired"
    VALIDATION_FAILED = "validation_failed"
    STORAGE_UNAVAILABLE = "storage_unavailable"
    CONFIG_IO_FAILED = "config_io_failed"
    INTERNAL_ERROR = "internal_error"
    OPERATION_INTERRUPTED = "operation_interrupted"
    METADATA_READ_FAILED = "metadata_read_failed"
    OPERATION_FAILED = "operation_failed"


class ApiRemediation(ApiModel):
    """Optional recovery action displayed but never executed automatically."""

    label: str
    route: str | MISSING = MISSING
    command: str | MISSING = MISSING


class ApiError(ApiModel):
    """One stable Web API error or disabled reason."""

    code: ApiErrorCode
    message: str
    field: str | MISSING = MISSING
    retryable: bool
    remediation: ApiRemediation | MISSING = MISSING
