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
    from omym2.domain.models.check_issue import CheckIssue, CheckIssueType
    from omym2.domain.models.check_run import CheckRun
    from omym2.domain.models.file_event import FileEvent, FileEventStatus
    from omym2.domain.models.file_scan_entry import FileScanEntry
    from omym2.domain.models.file_snapshot import FileSnapshot
    from omym2.domain.models.library import Library
    from omym2.domain.models.plan import Plan, PlanStatus, PlanType
    from omym2.domain.models.plan_action import ActionStatus, PlanAction
    from omym2.domain.models.run import Run, RunStatus
    from omym2.domain.models.track import Track, TrackGrouping, TrackStatus
    from omym2.domain.models.track_metadata import TrackMetadata
    from omym2.shared.ids import ActionId, CheckRunId, EventId, LibraryId, PlanId, RunId, TrackId
    from omym2.shared.pagination import FacetValue, GroupCount, Page, PageRequest

type FileSystemPath = str | PathLike[str]


class ConfigStoreValidationError(ValueError):
    """Raised when persisted settings cannot be converted into AppConfig."""

    def __init__(self, errors: Sequence[str]) -> None:
        """Store stable validation messages for feature and CLI callers."""
        self.errors: tuple[str, ...] = tuple(errors)
        super().__init__("; ".join(self.errors))


class MetadataReadError(ValueError):
    """Raised when a metadata adapter cannot read a supported tag mapping."""


class CheckRunRepository(Protocol):
    """Persistence contract for one Library's latest completed check run."""

    def save(self, check_run: CheckRun) -> None:
        """Persist a CheckRun header without deciding business policy."""
        ...

    def latest(self, library_id: LibraryId) -> CheckRun | None:
        """Return the latest CheckRun for one Library, if any."""
        ...

    def earliest_checked_at(self) -> datetime | None:
        """Return the minimum checked_at across every Library's latest check run, or None if none exist."""
        ...

    def delete_for_library(self, library_id: LibraryId) -> None:
        """Delete the CheckRun row for one Library, cascading its CheckIssues."""
        ...


class CheckIssueRepository(Protocol):
    """Persistence contract for one check run's findings."""

    def save_many(self, check_run_id: CheckRunId, issues: Sequence[CheckIssue]) -> None:
        """Persist CheckIssues for one check run in insertion (issue_seq ASC) order."""
        ...

    def delete_for_library(self, library_id: LibraryId) -> None:
        """Delete every persisted CheckIssue for one Library."""
        ...

    def query_page(
        self,
        library_id: LibraryId | None,
        *,
        issue_type: CheckIssueType | None,
        page: PageRequest,
    ) -> Page[CheckIssue]:
        """Return one keyset page of CheckIssues, ordered issue_seq ASC.

        `library_id=None` scopes across every Library's latest check run.
        `page.total` counts rows matching the filters, ignoring the cursor.
        """
        ...

    def issue_type_facets(self, library_id: LibraryId | None) -> tuple[FacetValue, ...]:
        """Return CheckIssue issue_type facets, ordered count DESC then value ASC."""
        ...

    def group_page(self, library_id: LibraryId | None, page: PageRequest) -> Page[GroupCount]:
        """Return one keyset page of CheckIssue groups by issue_type, ordered count DESC then key ASC."""
        ...


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

    def query_page(
        self,
        library_id: LibraryId | None,
        *,
        track_id: TrackId | None,
        search: str | None,
        status: TrackStatus | None,
        page: PageRequest,
    ) -> Page[Track]:
        """Return one keyset page of Tracks, ordered (current_path, track_id).

        `library_id=None` scopes across every known Library. `search` matches
        title, artist, album, current_path, or track_id, case-insensitive
        substring. `page.total` counts rows matching the filters, ignoring
        the cursor.
        """
        ...

    def status_facets(self, library_id: LibraryId | None) -> tuple[FacetValue, ...]:
        """Return Track status value/count facets, ordered count DESC then value ASC."""
        ...

    def group_page(
        self,
        library_id: LibraryId | None,
        grouping: TrackGrouping,
        page: PageRequest,
    ) -> Page[GroupCount]:
        """Return one keyset page of Track groups, ordered count DESC then key ASC."""
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

    def query_page(
        self,
        library_id: LibraryId | None,
        *,
        status: PlanStatus | None,
        plan_type: PlanType | None,
        page: PageRequest,
    ) -> Page[Plan]:
        """Return one keyset page of Plans, ordered (created_at DESC, plan_id DESC).

        `library_id=None` scopes across every known Library. `page.total`
        counts rows matching the filters, ignoring the cursor.
        """
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

    def query_page(
        self,
        plan_id: PlanId,
        *,
        status: ActionStatus | None,
        page: PageRequest,
    ) -> Page[PlanAction]:
        """Return one keyset page of a Plan's actions, ordered (sort_order, action_id).

        `page.total` counts rows matching the filters, ignoring the cursor.
        """
        ...

    def status_facets(self, plan_id: PlanId) -> tuple[FacetValue, ...]:
        """Return PlanAction status facets for one Plan, ordered count DESC then value ASC."""
        ...

    def action_type_facets(self, plan_id: PlanId) -> tuple[FacetValue, ...]:
        """Return PlanAction type facets for one Plan, ordered count DESC then value ASC."""
        ...

    def list_target_paths(self, plan_id: PlanId) -> Sequence[str]:
        """Return the non-null target_path values recorded for one Plan's actions."""
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

    def query_page(
        self,
        library_id: LibraryId | None,
        *,
        plan_id: PlanId | None,
        status: RunStatus | None,
        page: PageRequest,
    ) -> Page[Run]:
        """Return one keyset page of Runs, ordered (started_at DESC, run_id DESC).

        `library_id=None` scopes across every known Library. `page.total`
        counts rows matching the filters, ignoring the cursor.
        """
        ...

    def status_facets(self, library_id: LibraryId | None) -> tuple[FacetValue, ...]:
        """Return Run status facets, ordered count DESC then value ASC."""
        ...


class FileEventRepository(Protocol):
    """Persistence contract for durable Library music file events."""

    def get(self, event_id: EventId) -> FileEvent | None:
        """Return one FileEvent by ID."""
        ...

    def list_by_run(self, run_id: RunId) -> Sequence[FileEvent]:
        """Return FileEvents recorded for one Run in sequence order."""
        ...

    def list_pending_by_library(self, library_id: LibraryId) -> Sequence[FileEvent]:
        """Return PENDING FileEvents for one Library in sequence order."""
        ...

    def save(self, event: FileEvent) -> None:
        """Persist a FileEvent before or after a filesystem mutation."""
        ...

    def query_page(
        self,
        run_id: RunId,
        *,
        status: FileEventStatus | None,
        page: PageRequest,
    ) -> Page[FileEvent]:
        """Return one keyset page of a Run's FileEvents, ordered (sequence_no, event_id).

        `page.total` counts rows matching the filters, ignoring the cursor.
        """
        ...

    def status_facets(self, run_id: RunId) -> tuple[FacetValue, ...]:
        """Return FileEvent status facets for one Run, ordered count DESC then value ASC."""
        ...

    def list_target_paths(self, run_id: RunId) -> Sequence[str]:
        """Return the target_path values recorded for one Run's FileEvents."""
        ...


class UnitOfWork(Protocol):
    """Transaction boundary for one usecase interaction with repositories."""

    @property
    def libraries(self) -> LibraryRepository:
        """Repository for Library identity and registration state."""
        ...

    @property
    def check_runs(self) -> CheckRunRepository:
        """Repository for each Library's latest completed check run."""
        ...

    @property
    def check_issues(self) -> CheckIssueRepository:
        """Repository for the latest check run's findings."""
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

    def new_check_run_id(self) -> CheckRunId:
        """Create a check-run ID."""
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

    def new_check_run_id(self) -> CheckRunId:
        """Create a UUIDv7-backed check-run ID."""
        return shared_ids.new_check_run_id()

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
