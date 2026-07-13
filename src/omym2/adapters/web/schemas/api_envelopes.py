"""
Summary: Defines the generic Web API response envelope.
Why: Keeps success and failure transport shapes identical across routes.
"""

from __future__ import annotations

from typing import Annotated, Self

from pydantic import Field, model_validator

from omym2.adapters.web.schemas.api_errors import ApiError, ApiModel
from omym2.adapters.web.schemas.bootstrap import BootstrapData

EMPTY_ENVELOPE_MESSAGE = "An API envelope must contain data or at least one error."
MIXED_ENVELOPE_MESSAGE = "Only Bootstrap data may be combined with top-level errors."


class ApiEnvelope[EnvelopeData](ApiModel):
    """Generic response envelope with Bootstrap-compatible degradation."""

    data: EnvelopeData | None
    errors: tuple[ApiError, ...]

    @model_validator(mode="after")
    def validate_envelope_invariants(self) -> Self:
        """Reject empty envelopes and non-Bootstrap warning mixtures."""
        if self.data is None and not self.errors:
            raise ValueError(EMPTY_ENVELOPE_MESSAGE)
        if self.data is not None and self.errors and not isinstance(self.data, BootstrapData):
            raise ValueError(MIXED_ENVELOPE_MESSAGE)
        return self


class ApiFailureEnvelope(ApiModel):
    """Failure-only envelope used for declared error responses."""

    data: None
    errors: Annotated[tuple[ApiError, ...], Field(min_length=1)]
