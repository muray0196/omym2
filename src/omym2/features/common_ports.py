"""
Summary: Defines shared feature-layer ports.
Why: Lets usecases depend on contracts instead of concrete adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from os import PathLike
from typing import TYPE_CHECKING, Protocol, Self

from omym2.shared import ids as shared_ids
from omym2.shared.time import utc_now

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from contextlib import AbstractContextManager
    from datetime import datetime
    from types import TracebackType
    from uuid import UUID

    from omym2.domain.models.accepted_artist_name import AcceptedArtistName
    from omym2.domain.models.app_config import AppConfig
    from omym2.domain.models.check_issue import CheckIssue, CheckIssueGrouping, CheckIssueType
    from omym2.domain.models.check_run import CheckRun
    from omym2.domain.models.file_event import FileEvent, FileEventStatus
    from omym2.domain.models.file_scan_entry import FileScanEntry
    from omym2.domain.models.file_snapshot import FileSnapshot, FilesystemIdentity
    from omym2.domain.models.library import Library
    from omym2.domain.models.operation import Operation, OperationLookup
    from omym2.domain.models.plan import Plan, PlanStatus, PlanType
    from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction, PlanActionReason
    from omym2.domain.models.run import Run, RunStatus
    from omym2.domain.models.track import Track, TrackGrouping, TrackStatus
    from omym2.domain.models.track_metadata import TrackMetadata
    from omym2.shared.ids import ActionId, CheckRunId, EventId, LibraryId, OperationId, PlanId, RunId, TrackId
    from omym2.shared.pagination import FacetValue, GroupCount, Page, PageRequest

type FileSystemPath = str | PathLike[str]


class ConfigSnapshotState(StrEnum):
    """Raw Config storage states that participate in revision identity."""

    MISSING = "missing"
    INVALID = "invalid"
    VALID = "valid"


@dataclass(frozen=True, slots=True)
class ConfigSnapshot:
    """One parsed Config value coupled to its opaque raw-storage revision."""

    state: ConfigSnapshotState
    config: AppConfig
    config_revision: str
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExclusiveOperationRequest:
    """Diagnostic identity for one attempt to enter the mutation boundary."""

    operation_name: str


@dataclass(frozen=True, slots=True)
class ExclusiveOperationLease:
    """Proof that orchestration currently owns the shared mutation boundary."""

    request: ExclusiveOperationRequest


class ExclusiveOperationBusyError(RuntimeError):
    """Raised when another process or thread already owns mutation exclusion."""

    def __init__(self, request: ExclusiveOperationRequest, message: str) -> None:
        """Retain the rejected request for typed inbound-adapter handling."""
        self.request: ExclusiveOperationRequest = request
        super().__init__(message)


class IdempotencyKeyReusedError(RuntimeError):
    """Raised when one retained key names different canonical work."""


class OperationInProgressError(RuntimeError):
    """Raised when another durable Operation already owns the global slot."""

    def __init__(self, active_operation: Operation) -> None:
        """Retain the active identity for structured conflict remediation."""
        self.active_operation: Operation = active_operation
        super().__init__("Another state-changing Operation is in progress.")


class ConfigStoreValidationError(ValueError):
    """Raised when persisted settings cannot be converted into AppConfig."""

    def __init__(self, errors: Sequence[str]) -> None:
        """Store stable validation messages for feature and CLI callers."""
        self.errors: tuple[str, ...] = tuple(errors)
        super().__init__("; ".join(self.errors))


class ConfigRevisionMismatchError(RuntimeError):
    """Raised when Config storage no longer matches a caller's opaque revision."""

    def __init__(self, expected_config_revision: str, actual_config_revision: str) -> None:
        """Retain both opaque revisions for typed adapter-boundary handling."""
        self.expected_config_revision: str = expected_config_revision
        self.actual_config_revision: str = actual_config_revision
        super().__init__("Config storage changed after it was read.")


class ConfigStoreIoError(OSError):
    """Raised when raw Config storage cannot complete a requested I/O operation."""

    def __init__(self, cause: OSError) -> None:
        """Retain the operating-system failure for typed boundary translation."""
        self.cause: OSError = cause
        super().__init__(str(cause))


class MetadataReadError(ValueError):
    """Raised when a metadata adapter cannot read a supported tag mapping."""


@dataclass(frozen=True, slots=True)
class CheckIssueGroup:
    """One persisted-issue group plus its most common non-null path root."""

    key: str
    label: str
    count: int
    common_path_root: str | None


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


class AcceptedArtistNameRepository(Protocol):
    """Persistence contract for sticky accepted provider artist names."""

    def find_by_source_key(self, source_key: str) -> AcceptedArtistName | None:
        """Return the accepted name for one already-derived source key, if any."""
        ...

    def insert_if_absent(self, accepted_name: AcceptedArtistName) -> bool:
        """Insert one accepted name without replacing an existing sticky result."""
        ...


class CheckIssueRepository(Protocol):
    """Persistence contract for one check run's findings."""

    def save_many(self, check_run_id: CheckRunId, issues: Sequence[CheckIssue]) -> None:
        """Persist CheckIssues for one check run in insertion (issue_seq ASC) order."""
        ...

    def delete_for_library(self, library_id: LibraryId) -> None:
        """Delete every persisted CheckIssue for one Library."""
        ...

    def query_page(  # noqa: PLR0913  # Check browse filters are one stable port contract.
        self,
        library_id: LibraryId | None,
        *,
        search: str | None = None,
        issue_type: CheckIssueType | None,
        grouping: CheckIssueGrouping | None = None,
        group_key: str | None = None,
        page: PageRequest,
    ) -> Page[CheckIssue]:
        """Return one keyset page of CheckIssues, ordered issue_seq ASC.

        `library_id=None` scopes across every Library's latest check run.
        `page.total` counts rows matching the filters, ignoring the cursor.
        """
        ...

    def issue_type_facets(self, library_id: LibraryId | None, *, search: str | None = None) -> tuple[FacetValue, ...]:
        """Return CheckIssue issue_type facets, ordered count DESC then value ASC."""
        ...

    def group_page(  # Track groups share the list's search and facet scope.
        self,
        library_id: LibraryId | None,
        grouping: CheckIssueGrouping,
        page: PageRequest,
        *,
        search: str | None = None,
        issue_type: CheckIssueType | None = None,
    ) -> Page[CheckIssueGroup]:
        """Return one keyset page of CheckIssue groups, ordered count DESC then key ASC."""
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

    def save(self, track: Track) -> None:
        """Persist a Track without recalculating identity or paths."""
        ...

    def query_page(  # noqa: PLR0913  # Track browse filters form the repository's stable read contract.
        self,
        library_id: LibraryId | None,
        *,
        track_id: TrackId | None,
        search: str | None,
        status: TrackStatus | None,
        grouping: TrackGrouping | None,
        group_key: str | None,
        page: PageRequest,
    ) -> Page[Track]:
        """Return one keyset page of Tracks, ordered (current_path, track_id).

        `library_id=None` scopes across every known Library. `search` matches
        title, artist, album, current_path, or track_id, case-insensitive
        substring. An exact `grouping`/`group_key` pair instead orders matching
        group members by positive track number, title, then track ID. In both
        modes `page.total` counts rows matching the filters, ignoring the cursor.
        """
        ...

    def status_facets(self, library_id: LibraryId | None, *, search: str | None = None) -> tuple[FacetValue, ...]:
        """Return Track status value/count facets, ordered count DESC then value ASC."""
        ...

    def group_page(  # noqa: PLR0913  # Track groups share the list's search and facet scope.
        self,
        library_id: LibraryId | None,
        grouping: TrackGrouping,
        parent_key: str | None,
        page: PageRequest,
        *,
        search: str | None = None,
        status: TrackStatus | None = None,
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

    def list_by_source_run(self, source_run_id: RunId) -> Sequence[Plan]:
        """Return Undo Plans that record one source Run, in creation order."""
        ...

    def save(self, plan: Plan) -> None:
        """Persist a Plan header and summary."""
        ...

    def compare_and_set_status(
        self,
        plan_id: PlanId,
        expected_status: PlanStatus,
        replacement_status: PlanStatus,
    ) -> bool:
        """Atomically replace one Plan status only when its current status matches."""
        ...

    def query_page(  # noqa: PLR0913  # Plan browsing combines search and catalog filters in one stable port.
        self,
        library_id: LibraryId | None,
        *,
        search: str | None = None,
        status: PlanStatus | None,
        plan_type: PlanType | None,
        blocked_only: bool = False,
        page: PageRequest,
    ) -> Page[Plan]:
        """Return one keyset page of Plans, ordered (created_at DESC, plan_id DESC).

        `library_id=None` scopes across every known Library. `search` matches
        Plan identity and header fields. `page.total` counts rows matching the
        filters, ignoring the cursor. `blocked_only` selects Plans whose
        persisted summary records blocked actions.
        """
        ...


@dataclass(frozen=True, slots=True)
class PlanActionGroupRow:
    """Per-action projection for deriving Plan review group keys in usecases.

    Carries only the fields the grouping business rules need, so grouping
    stays in the feature layer instead of SQL.
    """

    action_id: ActionId
    track_id: TrackId | None
    sort_order: int
    status: ActionStatus
    reason: PlanActionReason | None
    action_type: ActionType
    source_path: str | None
    target_path: str | None
    content_hash_at_plan: str | None
    metadata_hash_at_plan: str | None


class PlanActionRepository(Protocol):
    """Persistence contract for recorded PlanActions."""

    def get(self, action_id: ActionId) -> PlanAction | None:
        """Return one PlanAction by ID."""
        ...

    def list_by_plan(self, plan_id: PlanId) -> Sequence[PlanAction]:
        """Return the actions recorded for a Plan in apply order."""
        ...

    def list_by_ids(self, action_ids: Sequence[ActionId]) -> Sequence[PlanAction]:
        """Return the PlanActions with the given IDs, ordered (sort_order, action_id)."""
        ...

    def save(self, action: PlanAction) -> None:
        """Persist a PlanAction without recalculating target paths."""
        ...

    def query_page(  # noqa: PLR0913  # PlanAction browse filters are one stable port contract.
        self,
        plan_id: PlanId,
        *,
        search: str | None = None,
        status: ActionStatus | None,
        action_type: ActionType | None = None,
        reason: PlanActionReason | None = None,
        page: PageRequest,
    ) -> Page[PlanAction]:
        """Return one keyset page of a Plan's actions, ordered (sort_order, action_id).

        `page.total` counts rows matching the filters, ignoring the cursor.
        """
        ...

    def status_facets(
        self,
        plan_id: PlanId,
        *,
        search: str | None = None,
        action_type: ActionType | None = None,
        reason: PlanActionReason | None = None,
    ) -> tuple[FacetValue, ...]:
        """Return PlanAction status facets for one Plan, ordered count DESC then value ASC."""
        ...

    def action_type_facets(
        self,
        plan_id: PlanId,
        *,
        search: str | None = None,
        status: ActionStatus | None = None,
        reason: PlanActionReason | None = None,
    ) -> tuple[FacetValue, ...]:
        """Return PlanAction type facets for one Plan, ordered count DESC then value ASC."""
        ...

    def reason_facets(
        self,
        plan_id: PlanId,
        *,
        search: str | None = None,
        status: ActionStatus | None = None,
        action_type: ActionType | None = None,
    ) -> tuple[FacetValue, ...]:
        """Return non-null PlanAction reason facets for one Plan, ordered count DESC then value ASC."""
        ...

    def count_filtered(
        self,
        plan_id: PlanId,
        *,
        search: str | None,
        status: ActionStatus | None,
        action_type: ActionType | None,
        reason: PlanActionReason | None,
    ) -> int:
        """Return the number of PlanActions matching every browse filter."""
        ...

    def count_target_collisions(self, plan_id: PlanId) -> int:
        """Return how many distinct non-null target_path values are recorded by 2+ of the Plan's actions."""
        ...

    def action_counts_by_plan(
        self,
        plan_ids: Sequence[PlanId],
    ) -> Mapping[PlanId, Mapping[tuple[ActionStatus, ActionType], int]]:
        """Return current status/action-type counts for all requested Plans in one aggregate query."""
        ...

    def list_group_rows(self, plan_id: PlanId) -> Sequence[PlanActionGroupRow]:
        """Return per-action group projections for one Plan, ordered (sort_order, action_id)."""
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
        search: str | None = None,
        plan_id: PlanId | None,
        status: RunStatus | None,
        page: PageRequest,
    ) -> Page[Run]:
        """Return one keyset page of Runs, ordered (started_at DESC, run_id DESC).

        `library_id=None` scopes across every known Library. `search` matches
        Run identity and diagnostic fields. `page.total` counts rows matching
        the filters, ignoring the cursor.
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

    def list_by_library(self, library_id: LibraryId) -> Sequence[FileEvent]:
        """Return FileEvents recorded for one Library in durable order."""
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


class OperationRepository(Protocol):
    """Persistence contract for durable background request lifecycle records."""

    def lookup(self, operation_id: OperationId) -> OperationLookup | None:
        """Return a full Operation or retained tombstone by stable ID."""
        ...

    def find_by_idempotency_key(self, idempotency_key: UUID) -> OperationLookup | None:
        """Return retained request identity for idempotent replay classification."""
        ...

    def list_reconciliation_candidates(self) -> Sequence[Operation]:
        """Return full unfinished/interrupted Operations in deterministic request order."""
        ...

    def find_active(self) -> Operation | None:
        """Return the single queued or running Operation, if one exists."""
        ...

    def save(self, operation: Operation) -> None:
        """Persist one full Operation without deciding lifecycle policy."""
        ...

    def expire_terminal_payloads(self, now: datetime) -> int:
        """Clear expired result/error payloads and return the affected row count."""
        ...

    def purge_expired_tombstones(self, now: datetime) -> int:
        """Delete expired terminal tombstones and return the affected row count."""
        ...


class UnitOfWork(Protocol):
    """Transaction boundary for one usecase interaction with repositories."""

    def usecase_scope(self) -> AbstractContextManager[None]:
        """Retain adapter resources across this usecase's transaction scopes."""
        ...

    @property
    def accepted_artist_names(self) -> AcceptedArtistNameRepository:
        """Repository for sticky accepted provider artist names."""
        ...

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

    @property
    def operations(self) -> OperationRepository:
        """Repository for durable background request lifecycle records."""
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

    def claim_apply(self, plan_id: PlanId, run: Run, operation: Operation) -> bool:
        """Stage the ready Plan claim, running Run, and queued Operation in this transaction."""
        ...


class FileScanner(Protocol):
    """Filesystem discovery contract for cheap candidate file scans."""

    def scan(self, root: FileSystemPath) -> Sequence[FileScanEntry]:
        """Return file discovery entries without tags or hashes."""
        ...


class FileStatReader(Protocol):
    """Filesystem contract for one cheap file stat observation."""

    def observe(self, path: FileSystemPath) -> FileScanEntry:
        """Return size, mtime, and extension without tags or hashes."""
        ...


class FileSnapshotReader(Protocol):
    """Filesystem observation contract for full file snapshots."""

    def capture(self, path: FileSystemPath) -> FileSnapshot:
        """Capture a fresh stat plus metadata and hashes for one file."""
        ...


@dataclass(frozen=True, slots=True)
class FileSnapshotCaptureRequest:
    """One full-snapshot request within a batch capture."""

    path: FileSystemPath


class BatchFileSnapshotReader(Protocol):
    """Bounded, input-order-preserving full file snapshot capture."""

    def capture_many(self, requests: Sequence[FileSnapshotCaptureRequest]) -> Sequence[FileSnapshot | None]:
        """Return results in request order, using None only for files that disappeared."""
        ...


class FilePresence(Protocol):
    """Filesystem presence contract for conflict checks that do not inspect files."""

    def exists(self, path: FileSystemPath) -> bool:
        """Return whether a filesystem entry exists at the supplied path."""
        ...


class ExclusiveOperationLock(Protocol):
    """Cross-process nonblocking boundary shared by every state-changing flow."""

    def hold(self, request: ExclusiveOperationRequest) -> AbstractContextManager[ExclusiveOperationLease]:
        """Return a context that retains exclusion for its complete lifetime."""
        ...


class MetadataReader(Protocol):
    """Metadata adapter contract for reading music tags."""

    def read(self, path: FileSystemPath) -> TrackMetadata:
        """Read music metadata from one file."""
        ...


class FileMover(Protocol):
    """Filesystem mutation contract used only by apply-like usecases."""

    def move(  # noqa: PLR0913  # Source identity and content hash are separate mutation preconditions.
        self,
        source: FileSystemPath,
        target: FileSystemPath,
        *,
        source_root: FileSystemPath | None = None,
        target_root: FileSystemPath | None = None,
        expected_source_identity: FilesystemIdentity | None = None,
        expected_source_content_hash: str | None = None,
    ) -> None:
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


class ConfigReader(Protocol):
    """Read-only parsed application config contract."""

    def load(self) -> AppConfig:
        """Load application settings."""
        ...


class ConfigSnapshotReader(Protocol):
    """Read-only raw Config snapshot contract used by Bootstrap and Settings."""

    def read_snapshot(self) -> ConfigSnapshot:
        """Return parsed recovery data and an opaque revision from one raw read."""
        ...


class ConfigStore(ConfigReader, ConfigSnapshotReader, Protocol):
    """Revision-aware application config persistence contract."""

    def save(self, config: AppConfig, *, expected_config_revision: str) -> ConfigSnapshot:
        """Atomically save settings only when raw storage still has the expected revision."""
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

    def new_operation_id(self) -> OperationId:
        """Create an Operation ID."""
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

    def new_operation_id(self) -> OperationId:
        """Create a UUIDv7-backed Operation ID."""
        return shared_ids.new_operation_id()
