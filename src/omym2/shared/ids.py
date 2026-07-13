"""
Summary: Defines typed ID helpers for stable OMYM2 identities.
Why: Keeps identity generation separate from paths, hashes, and metadata.
"""

from __future__ import annotations

from typing import NewType
from uuid import UUID, uuid7

from omym2.config import UUID_VERSION

ActionId = NewType("ActionId", UUID)
CheckRunId = NewType("CheckRunId", UUID)
EventId = NewType("EventId", UUID)
LibraryId = NewType("LibraryId", UUID)
OperationId = NewType("OperationId", UUID)
PlanId = NewType("PlanId", UUID)
RunId = NewType("RunId", UUID)
TrackId = NewType("TrackId", UUID)


def new_uuid7() -> UUID:
    """Create a UUIDv7 value for stable internal identifiers."""
    return uuid7()


def is_uuid7(value: UUID) -> bool:
    """Return whether a UUID value uses the documented UUIDv7 version."""
    return value.version == UUID_VERSION


def new_action_id() -> ActionId:
    """Create an action identifier."""
    return ActionId(new_uuid7())


def new_check_run_id() -> CheckRunId:
    """Create a check-run identifier."""
    return CheckRunId(new_uuid7())


def new_event_id() -> EventId:
    """Create a file-event identifier."""
    return EventId(new_uuid7())


def new_library_id() -> LibraryId:
    """Create a Library identifier."""
    return LibraryId(new_uuid7())


def new_operation_id() -> OperationId:
    """Create an Operation identifier."""
    return OperationId(new_uuid7())


def new_plan_id() -> PlanId:
    """Create a Plan identifier."""
    return PlanId(new_uuid7())


def new_run_id() -> RunId:
    """Create a Run identifier."""
    return RunId(new_uuid7())


def new_track_id() -> TrackId:
    """Create a Track identifier."""
    return TrackId(new_uuid7())


def parse_uuid(raw_value: str) -> UUID:
    """Parse a persisted UUID string into a UUID value."""
    return UUID(raw_value)


def id_to_string(value: UUID) -> str:
    """Render a persisted ID value without shortening it."""
    return str(value)
