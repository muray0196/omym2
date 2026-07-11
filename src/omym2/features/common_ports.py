"""
Summary: Defines shared feature-layer ports.
Why: Lets usecases depend on contracts instead of concrete adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from os import PathLike
from typing import TYPE_CHECKING, Protocol, Self

from omym2.shared import ids as shared_ids
from omym2.shared.time import utc_now

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime
    from types import TracebackType

    from omym2.domain.models.app_config import AppConfig
    from omym2.domain.models.file_event import FileEvent
    from omym2.domain.models.file_scan_entry import FileScanEntry
    from omym2.domain.models.file_snapshot import FileSnapshot
    from omym2.domain.models.library import Library
    from omym2.domain.models.plan import Plan
    from omym2.domain.models.plan_action import PlanAction
    from omym2.domain.models.run import Run
    from omym2.domain.models.track import Track
    from omym2.domain.models.track_metadata import TrackMetadata
    from omym2.shared.ids import ActionId, EventId, LibraryId, PlanId, RunId, TrackId

type FileSystemPath = str | PathLike[str]


class ConfigStoreValidationError(ValueError):
    """Raised when persisted settings cannot be converted into AppConfig."""

    def __init__(self, errors: Sequence[str]) -> None:
        """Store stable validation messages for feature and CLI callers."""
        self.errors: tuple[str, ...] = tuple(errors)
        super().__init__("; ".join(self.errors))


class LibraryRepository(Protocol):
    """Persistence contract for Library identity and registration state."""

    def get(self, library_id: LibraryId) -> Library | None:
        """Return one Library by stable ID."""
        ...

    def find_by_root_path(self, root_path: str) -> Library | None:
        """Return the Library currently registered for a root path, if any."""
        ...

    def list_all(self) -> Sequence[Library]:
        """Return all known Libraries."""
        ...

    def save(self, library: Library) -> None:
        """Persist a Library without deciding business policy."""
        ...


class TrackRepository(Protocol):
    """Persistence contract for managed Track state."""

    def get(self, track_id: TrackId) -> Track | None:
        """Return one Track by stable ID."""
        ...

    def list_by_library(self, library_id: LibraryId) -> Sequence[Track]:
        """Return Tracks owned by one Library."""
        ...

    def find_by_content_hash(self, library_id: LibraryId, content_hash: str) -> Sequence[Track]:
        """Return Tracks with a matching content hash in one Library."""
        ...

    def save(self, track: Track) -> None:
        """Persist a Track without recalculating identity or paths."""
        ...


class PlanRepository(Protocol):
    """Persistence contract for reviewed Plans."""

    def get(self, plan_id: PlanId) -> Plan | None:
        """Return one Plan by ID."""
        ...

    def list_by_library(self, library_id: LibraryId) -> Sequence[Plan]:
        """Return Plans owned by one Library."""
        ...

    def save(self, plan: Plan) -> None:
        """Persist a Plan header and summary."""
        ...


class PlanActionRepository(Protocol):
    """Persistence contract for recorded PlanActions."""

    def get(self, action_id: ActionId) -> PlanAction | None:
        """Return one PlanAction by ID."""
        ...

    def list_by_plan(self, plan_id: PlanId) -> Sequence[PlanAction]:
        """Return the actions recorded for a Plan in apply order."""
        ...

    def save(self, action: PlanAction) -> None:
        """Persist a PlanAction without recalculating target paths."""
        ...


class RunRepository(Protocol):
    """Persistence contract for apply execution attempts."""

    def get(self, run_id: RunId) -> Run | None:
        """Return one Run by ID."""
        ...

    def list_by_library(self, library_id: LibraryId) -> Sequence[Run]:
        """Return Runs owned by one Library."""
        ...

    def list_by_plan(self, plan_id: PlanId) -> Sequence[Run]:
        """Return Runs created for one Plan."""
        ...

    def save(self, run: Run) -> None:
        """Persist Run state transitions."""
        ...


class FileEventRepository(Protocol):
    """Persistence contract for durable Library music file events."""

    def get(self, event_id: EventId) -> FileEvent | None:
        """Return one FileEvent by ID."""
        ...

    def list_by_run(self, run_id: RunId) -> Sequence[FileEvent]:
        """Return FileEvents recorded for one Run in sequence order."""
        ...

    def list_by_library(self, library_id: LibraryId) -> Sequence[FileEvent]:
        """Return FileEvents recorded for one Library in durable order."""
        ...

    def save(self, event: FileEvent) -> None:
        """Persist a FileEvent before or after a filesystem mutation."""
        ...


class UnitOfWork(Protocol):
    """Transaction boundary for one usecase interaction with repositories."""

    @property
    def libraries(self) -> LibraryRepository:
        """Repository for Library identity and registration state."""
        ...

    @property
    def tracks(self) -> TrackRepository:
        """Repository for managed Track state."""
        ...

    @property
    def plans(self) -> PlanRepository:
        """Repository for reviewed Plans."""
        ...

    @property
    def plan_actions(self) -> PlanActionRepository:
        """Repository for recorded PlanActions."""
        ...

    @property
    def runs(self) -> RunRepository:
        """Repository for apply Runs."""
        ...

    @property
    def file_events(self) -> FileEventRepository:
        """Repository for durable filesystem operation logs."""
        ...

    def __enter__(self) -> Self:
        """Open the transaction boundary."""
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        """Close the transaction boundary."""
        ...

    def commit(self) -> None:
        """Commit the current unit of work."""
        ...

    def rollback(self) -> None:
        """Rollback the current unit of work."""
        ...


class FileScanner(Protocol):
    """Filesystem discovery contract for cheap candidate file scans."""

    def scan(self, root: FileSystemPath) -> Sequence[FileScanEntry]:
        """Return file discovery entries without tags or hashes."""
        ...


class FileSnapshotReader(Protocol):
    """Filesystem observation contract for full file snapshots."""

    def capture(self, path: FileSystemPath) -> FileSnapshot:
        """Capture stat, metadata, and hash data for one file."""
        ...


class FilePresence(Protocol):
    """Filesystem presence contract for conflict checks that do not inspect files."""

    def exists(self, path: FileSystemPath) -> bool:
        """Return whether a filesystem entry exists at the supplied path."""
        ...


class MetadataReader(Protocol):
    """Metadata adapter contract for reading music tags."""

    def read(self, path: FileSystemPath) -> TrackMetadata:
        """Read music metadata from one file."""
        ...


class FileMover(Protocol):
    """Filesystem mutation contract used only by apply-like usecases."""

    def move(self, source: FileSystemPath, target: FileSystemPath) -> None:
        """Move one file without deciding PlanAction policy."""
        ...


class PathResolver(Protocol):
    """Filesystem boundary contract for Library-relative path conversion."""

    def resolve_library_path(self, library_root: FileSystemPath, library_relative_path: str) -> FileSystemPath:
        """Return an absolute path for one Library-relative path."""
        ...

    def relative_to_library(self, library_root: FileSystemPath, path: FileSystemPath) -> str:
        """Return the stored Library-relative form for a filesystem path."""
        ...


class ConfigStore(Protocol):
    """Application config persistence contract."""

    def load(self) -> AppConfig:
        """Load application settings."""
        ...

    def save(self, config: AppConfig) -> None:
        """Save application settings."""
        ...


class Clock(Protocol):
    """Time source contract for deterministic usecase tests."""

    def now(self) -> datetime:
        """Return the current timezone-aware timestamp."""
        ...


class IdGenerator(Protocol):
    """ID source contract for stable OMYM2 identities."""

    def new_library_id(self) -> LibraryId:
        """Create a Library ID."""
        ...

    def new_track_id(self) -> TrackId:
        """Create a Track ID."""
        ...

    def new_plan_id(self) -> PlanId:
        """Create a Plan ID."""
        ...

    def new_action_id(self) -> ActionId:
        """Create a PlanAction ID."""
        ...

    def new_run_id(self) -> RunId:
        """Create a Run ID."""
        ...

    def new_event_id(self) -> EventId:
        """Create a FileEvent ID."""
        ...


@dataclass(frozen=True, slots=True)
class SystemClock:
    """Clock implementation backed by the process clock."""

    def now(self) -> datetime:
        """Return the current timezone-aware UTC timestamp."""
        return utc_now()


@dataclass(frozen=True, slots=True)
class Uuid7IdGenerator:
    """ID generator backed by the documented UUIDv7 helpers."""

    def new_library_id(self) -> LibraryId:
        """Create a UUIDv7-backed Library ID."""
        return shared_ids.new_library_id()

    def new_track_id(self) -> TrackId:
        """Create a UUIDv7-backed Track ID."""
        return shared_ids.new_track_id()

    def new_plan_id(self) -> PlanId:
        """Create a UUIDv7-backed Plan ID."""
        return shared_ids.new_plan_id()

    def new_action_id(self) -> ActionId:
        """Create a UUIDv7-backed PlanAction ID."""
        return shared_ids.new_action_id()

    def new_run_id(self) -> RunId:
        """Create a UUIDv7-backed Run ID."""
        return shared_ids.new_run_id()

    def new_event_id(self) -> EventId:
        """Create a UUIDv7-backed FileEvent ID."""
        return shared_ids.new_event_id()
