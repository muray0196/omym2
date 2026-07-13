"""
Summary: Defines durable Operation, polling, and planning Web resources.
Why: Generates one typed client contract for accepted work, progress, and navigation results.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003  # Pydantic resolves timestamp schema types at runtime.
from re import fullmatch
from typing import Annotated, Literal
from uuid import UUID  # noqa: TC003  # Pydantic resolves UUID schema types at runtime.

from pydantic import Field, field_validator, model_validator

from omym2.adapters.web.schemas.api_errors import ApiError, ApiErrorCode, ApiModel
from omym2.domain.models.operation import (  # Pydantic resolves enum schema types at runtime.
    OperationKind,
    OperationStatus,
)

INVALID_REFRESH_TARGET_MESSAGE = "Refresh target_path must be set exactly for file or directory targets."
INVALID_OPERATION_RESOURCE_MESSAGE = "Operation resource fields do not match its lifecycle status."
INVALID_OPERATION_PROGRESS_MESSAGE = "Operation progress counts must be a valid nullable pair."
INVALID_OPERATION_STAGE_MESSAGE = "Operation progress stage_code must be stable snake_case."
INVALID_OPERATION_RESULT_MESSAGE = "Operation result does not match its kind or durable associations."
EMPTY_OPERATION_PATH_MESSAGE = "Operation path fields must not be empty."


class OperationRef(ApiModel):
    """Compact reference returned when durable work is accepted or replayed."""

    operation_id: UUID
    kind: OperationKind
    status: OperationStatus
    status_url: str
    poll_after_ms: int = Field(gt=0)


class OperationProgressResource(ApiModel):
    """Display-safe durable progress without fabricated percentages."""

    stage_code: str | None
    completed_units: int | None
    total_units: int | None
    message: str | None

    @model_validator(mode="after")
    def validate_progress(self) -> OperationProgressResource:
        """Reject partial, negative, decreasing, or unstable-code progress evidence."""
        if self.stage_code is not None and fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*", self.stage_code) is None:
            raise ValueError(INVALID_OPERATION_STAGE_MESSAGE)
        if (self.completed_units is None) != (self.total_units is None):
            raise ValueError(INVALID_OPERATION_PROGRESS_MESSAGE)
        if (
            self.completed_units is not None
            and self.total_units is not None
            and (self.completed_units < 0 or self.total_units < 0 or self.completed_units > self.total_units)
        ):
            raise ValueError(INVALID_OPERATION_PROGRESS_MESSAGE)
        return self


class PlanCreatedResultResource(ApiModel):
    """Navigation result for planning Operations."""

    kind: Literal["plan_created"] = "plan_created"
    plan_id: UUID


class RegisteredWithoutPlanResultResource(ApiModel):
    """Navigation result for a clean Organize registration."""

    kind: Literal["registered_without_plan"] = "registered_without_plan"
    library_id: UUID
    track_count: int = Field(ge=0)


class CheckCompletedResultResource(ApiModel):
    """Navigation result for persisted Check findings."""

    kind: Literal["check_completed"] = "check_completed"
    check_run_ids: tuple[UUID, ...] = Field(min_length=1)
    issue_count: int = Field(ge=0)


class RunCompletedResultResource(ApiModel):
    """Navigation result for Apply Operations."""

    kind: Literal["run_completed"] = "run_completed"
    run_id: UUID


type OperationResultResource = Annotated[
    PlanCreatedResultResource
    | RegisteredWithoutPlanResultResource
    | CheckCompletedResultResource
    | RunCompletedResultResource,
    Field(discriminator="kind"),
]


class OperationResource(ApiModel):
    """Full retained Operation status returned by polling."""

    operation_id: UUID
    kind: OperationKind
    status: OperationStatus
    library_id: UUID | None
    plan_id: UUID | None
    run_id: UUID | None
    progress: OperationProgressResource
    result: OperationResultResource | None
    error: ApiError | None
    requested_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    @model_validator(mode="after")
    def validate_lifecycle(self) -> OperationResource:
        """Reject malformed status fields before the resource reaches generated clients."""
        if self.status is OperationStatus.QUEUED:
            valid = self.started_at is None and self.completed_at is None and self.result is None and self.error is None
        elif self.status is OperationStatus.RUNNING:
            valid = (
                self.started_at is not None and self.completed_at is None and self.result is None and self.error is None
            )
        elif self.status is OperationStatus.SUCCEEDED:
            valid = (
                self.started_at is not None
                and self.completed_at is not None
                and self.result is not None
                and self.error is None
            )
        elif self.status is OperationStatus.FAILED:
            valid = (
                self.started_at is not None
                and self.completed_at is not None
                and self.result is None
                and self.error is not None
                and self.error.code in {ApiErrorCode.METADATA_READ_FAILED, ApiErrorCode.OPERATION_FAILED}
            )
        else:
            valid = (
                self.completed_at is not None
                and self.result is None
                and self.error is not None
                and self.error.code is ApiErrorCode.OPERATION_INTERRUPTED
            )
        if not valid or (self.started_at is not None and self.started_at < self.requested_at):
            raise ValueError(INVALID_OPERATION_RESOURCE_MESSAGE)
        if self.completed_at is not None and (
            self.completed_at < self.requested_at
            or (self.started_at is not None and self.completed_at < self.started_at)
        ):
            raise ValueError(INVALID_OPERATION_RESOURCE_MESSAGE)
        self._validate_result_associations()
        return self

    def _validate_result_associations(self) -> None:
        result = self.result
        if result is None:
            return
        allowed = {
            OperationKind.ADD_PLAN: (PlanCreatedResultResource,),
            OperationKind.ORGANIZE_PLAN: (PlanCreatedResultResource, RegisteredWithoutPlanResultResource),
            OperationKind.REFRESH_PLAN: (PlanCreatedResultResource,),
            OperationKind.CHECK: (CheckCompletedResultResource,),
            OperationKind.APPLY_PLAN: (RunCompletedResultResource,),
            OperationKind.UNDO_PLAN: (PlanCreatedResultResource,),
        }
        associations_match = (
            (not isinstance(result, PlanCreatedResultResource) or result.plan_id == self.plan_id)
            and (not isinstance(result, RegisteredWithoutPlanResultResource) or result.library_id == self.library_id)
            and (not isinstance(result, RunCompletedResultResource) or result.run_id == self.run_id)
        )
        if type(result) not in allowed[self.kind] or not associations_match:
            raise ValueError(INVALID_OPERATION_RESULT_MESSAGE)


class AddPlanRequest(ApiModel):
    """Validated Add planning inputs."""

    source_path: str | None = None
    library_id: UUID | None = None

    @field_validator("source_path")
    @classmethod
    def validate_source_path(cls, value: str | None) -> str | None:
        """Reject an explicit empty source without rewriting valid path text."""
        if value is not None and value.strip() == "":
            raise ValueError(EMPTY_OPERATION_PATH_MESSAGE)
        return value


class OrganizePlanRequest(ApiModel):
    """Explicit Library root for registration or reconciliation planning."""

    library_root: str

    @field_validator("library_root")
    @classmethod
    def validate_library_root(cls, value: str) -> str:
        """Reject a root that would otherwise normalize to the working directory."""
        if value.strip() == "":
            raise ValueError(EMPTY_OPERATION_PATH_MESSAGE)
        return value


class RefreshPlanRequest(ApiModel):
    """Exactly one selected Refresh scope for one Library."""

    library_id: UUID
    target_kind: Literal["file", "directory", "all"]
    target_path: str | None = None

    @model_validator(mode="after")
    def validate_target(self) -> RefreshPlanRequest:
        """Require paths for narrow targets and prohibit one for all-target refresh."""
        has_path = self.target_path is not None and self.target_path.strip() != ""
        if (self.target_kind == "all") == has_path:
            raise ValueError(INVALID_REFRESH_TARGET_MESSAGE)
        return self


class CheckRunRequest(ApiModel):
    """Optional Library scope for a persisted Check Operation."""

    library_id: UUID | None = None
