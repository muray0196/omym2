"""
Summary: Provides in-memory repository fakes for usecase tests.
Why: Lets feature tests exercise ports before SQLite adapters exist.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Self

from omym2.domain.models.file_event import FileEventStatus
from omym2.domain.models.operation import Operation, OperationLookup, OperationStatus, OperationTombstone
from omym2.domain.models.plan import PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus
from omym2.domain.models.track import TrackGrouping
from omym2.features.common_ports import CheckIssueGroup, PlanActionGroupRow
from omym2.shared.pagination import (
    INVALID_CURSOR_MESSAGE,
    CursorDecodeError,
    FacetValue,
    GroupCount,
    Page,
    paginate_group_counts,
)
from omym2.shared.text import ascii_lower
from tests.fakes.grouping import (
    common_path_root_for_check_issue,
    derive_check_issue_group_key,
    derive_track_group_key,
    track_group_member_sort_key,
)

if TYPE_CHECKING:
    from collections.abc import Generator, Sequence
    from datetime import datetime
    from types import TracebackType
    from uuid import UUID

    from omym2.domain.models.accepted_artist_name import AcceptedArtistName
    from omym2.domain.models.check_issue import CheckIssue, CheckIssueGrouping, CheckIssueType
    from omym2.domain.models.check_run import CheckRun
    from omym2.domain.models.companion_asset import CompanionAsset
    from omym2.domain.models.file_event import FileEvent
    from omym2.domain.models.library import Library
    from omym2.domain.models.plan import Plan
    from omym2.domain.models.plan_action import ActionType, PlanAction, PlanActionDependency, PlanActionReason
    from omym2.domain.models.run import Run, RunStatus
    from omym2.domain.models.track import Track, TrackStatus
    from omym2.shared.ids import (
        ActionId,
        CheckRunId,
        CompanionAssetId,
        EventId,
        LibraryId,
        OperationId,
        PlanId,
        RunId,
        TrackId,
    )
    from omym2.shared.pagination import PageRequest

KEYSET_CURSOR_KEY_LENGTH = 2  # every Track/Track-group cursor key is a 2-tuple
TRACK_GROUP_MEMBER_CURSOR_KEY_LENGTH = 4  # grouped Track member cursor: rank, number, title, track ID
CHECK_ISSUE_CURSOR_KEY_LENGTH = 1  # a CheckIssue cursor key is a single issue_seq value
TRACK_GROUP_FILTER_PAIRING_MESSAGE = "grouping and group_key must be provided together."


@dataclass(slots=True)
class InMemoryAcceptedArtistNameRepository:
    """In-memory AcceptedArtistNameRepository fake."""

    records: dict[str, AcceptedArtistName] = field(default_factory=dict)

    def find_by_source_key(self, source_key: str) -> AcceptedArtistName | None:
        """Return the accepted artist name for one already-derived source key."""
        return self.records.get(source_key)

    def insert_if_absent(self, accepted_name: AcceptedArtistName) -> bool:
        """Insert one accepted name without replacing an existing record."""
        if accepted_name.source_key in self.records:
            return False
        self.records[accepted_name.source_key] = accepted_name
        return True


@dataclass(slots=True)
class InMemoryLibraryRepository:
    """In-memory LibraryRepository fake."""

    records: dict[LibraryId, Library] = field(default_factory=dict)

    def get(self, library_id: LibraryId) -> Library | None:
        """Return one Library by ID."""
        return self.records.get(library_id)

    def find_by_root_path(self, root_path: str) -> Library | None:
        """Return the Library currently stored for a root path."""
        for library in self.records.values():
            if library.root_path == root_path:
                return library
        return None

    def list_all(self) -> tuple[Library, ...]:
        """Return all Libraries in insertion order."""
        return tuple(self.records.values())

    def save(self, library: Library) -> None:
        """Store or replace one Library."""
        self.records[library.library_id] = library


@dataclass(slots=True)
class InMemoryCheckRunRepository:
    """In-memory CheckRunRepository fake."""

    records: dict[LibraryId, CheckRun] = field(default_factory=dict)

    def save(self, check_run: CheckRun) -> None:
        """Store or replace one Library's CheckRun."""
        self.records[check_run.library_id] = check_run

    def latest(self, library_id: LibraryId) -> CheckRun | None:
        """Return the latest CheckRun for one Library, if any."""
        return self.records.get(library_id)

    def earliest_checked_at(self) -> datetime | None:
        """Return the minimum checked_at across every Library's latest check run, or None if none exist."""
        checked_at_values = [check_run.checked_at for check_run in self.records.values()]
        return min(checked_at_values) if checked_at_values else None

    def delete_for_library(self, library_id: LibraryId) -> None:
        """Delete the CheckRun row for one Library."""
        _ = self.records.pop(library_id, None)


@dataclass(slots=True)
class InMemoryCheckIssueRepository:
    """In-memory CheckIssueRepository fake."""

    records: dict[int, CheckIssue] = field(default_factory=dict)
    _next_issue_seq: int = field(default=1, init=False)

    def save_many(self, check_run_id: CheckRunId, issues: Sequence[CheckIssue]) -> None:
        """Store CheckIssues for one check run in insertion (issue_seq ASC) order."""
        del check_run_id
        for issue in issues:
            self.records[self._next_issue_seq] = issue
            self._next_issue_seq += 1

    def delete_for_library(self, library_id: LibraryId) -> None:
        """Delete every persisted CheckIssue for one Library."""
        for issue_seq in [seq for seq, issue in self.records.items() if issue.library_id == library_id]:
            del self.records[issue_seq]

    def query_page(  # noqa: PLR0913  # Mirrors the stable CheckIssueRepository browse contract.
        self,
        library_id: LibraryId | None,
        *,
        search: str | None = None,
        issue_type: CheckIssueType | None,
        grouping: CheckIssueGrouping | None = None,
        group_key: str | None = None,
        page: PageRequest,
    ) -> Page[CheckIssue]:
        """Return one keyset page of CheckIssues ordered issue_seq ASC."""
        entries = [
            (issue_seq, issue)
            for issue_seq, issue in sorted(self.records.items())
            if (library_id is None or issue.library_id == library_id)
            and (not search or _check_issue_matches_search(issue, search))
            and (issue_type is None or issue.issue_type == issue_type)
            and (
                grouping is None or group_key is None or derive_check_issue_group_key(issue, grouping).key == group_key
            )
        ]
        total = len(entries)

        if page.cursor_key is not None:
            if len(page.cursor_key) != CHECK_ISSUE_CURSOR_KEY_LENGTH:
                raise CursorDecodeError(INVALID_CURSOR_MESSAGE)
            (cursor_text,) = page.cursor_key
            try:
                cursor_issue_seq = int(cursor_text)
            except ValueError as error:
                raise CursorDecodeError(INVALID_CURSOR_MESSAGE) from error
            entries = [(issue_seq, issue) for issue_seq, issue in entries if issue_seq > cursor_issue_seq]

        page_entries = entries[: page.limit]
        has_more = len(entries) > page.limit
        page_items = tuple(issue for _, issue in page_entries)
        next_cursor_key = (str(page_entries[-1][0]),) if has_more else None
        return Page(items=page_items, next_cursor_key=next_cursor_key, total=total)

    def issue_type_facets(self, library_id: LibraryId | None, *, search: str | None = None) -> tuple[FacetValue, ...]:
        """Return CheckIssue issue_type facets, ordered count DESC then value ASC."""
        counts: dict[str, int] = {}
        for issue in self.records.values():
            if library_id is not None and issue.library_id != library_id:
                continue
            if search and not _check_issue_matches_search(issue, search):
                continue
            counts[issue.issue_type.value] = counts.get(issue.issue_type.value, 0) + 1
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return tuple(FacetValue(value=value, count=count) for value, count in ordered)

    def group_page(
        self,
        library_id: LibraryId | None,
        grouping: CheckIssueGrouping,
        page: PageRequest,
        *,
        search: str | None = None,
        issue_type: CheckIssueType | None = None,
    ) -> Page[CheckIssueGroup]:
        """Return one keyset page of CheckIssue groups ordered count DESC then key ASC."""
        groups_by_key: dict[str, tuple[str, int, dict[str, int]]] = {}
        for issue in self.records.values():
            if library_id is not None and issue.library_id != library_id:
                continue
            if search and not _check_issue_matches_search(issue, search):
                continue
            if issue_type is not None and issue.issue_type is not issue_type:
                continue
            derived = derive_check_issue_group_key(issue, grouping)
            label, count, root_counts = groups_by_key.get(derived.key, (derived.label, 0, {}))
            path_root = common_path_root_for_check_issue(issue)
            if path_root is not None:
                root_counts[path_root] = root_counts.get(path_root, 0) + 1
            groups_by_key[derived.key] = (label, count + 1, root_counts)
        groups = [
            CheckIssueGroup(
                key=key,
                label=label,
                count=count,
                common_path_root=_top_check_issue_path_root(root_counts),
            )
            for key, (label, count, root_counts) in groups_by_key.items()
        ]
        return paginate_group_counts(groups, page)


def _top_check_issue_path_root(root_counts: dict[str, int]) -> str | None:
    """Return the most frequent path root, breaking ties by the smaller label."""
    if not root_counts:
        return None
    return min(root_counts.items(), key=lambda item: (-item[1], item[0]))[0]


def _check_issue_matches_search(issue: CheckIssue, search: str) -> bool:
    """Mirror the persisted CheckIssue substring-search fields."""
    needle = ascii_lower(search)
    values = (
        str(issue.library_id),
        issue.path,
        None if issue.track_id is None else str(issue.track_id),
        None if issue.plan_id is None else str(issue.plan_id),
        None if issue.companion_asset_id is None else str(issue.companion_asset_id),
        issue.detail,
    )
    return any(value is not None and needle in ascii_lower(value) for value in values)


@dataclass(slots=True)
class InMemoryTrackRepository:
    """In-memory TrackRepository fake."""

    records: dict[TrackId, Track] = field(default_factory=dict)

    def get(self, track_id: TrackId) -> Track | None:
        """Return one Track by ID."""
        return self.records.get(track_id)

    def list_by_library(self, library_id: LibraryId) -> tuple[Track, ...]:
        """Return Tracks owned by a Library."""
        return tuple(track for track in self.records.values() if track.library_id == library_id)

    def save(self, track: Track) -> None:
        """Store or replace one Track."""
        self.records[track.track_id] = track

    def query_page(  # noqa: PLR0913  # Mirrors the stable TrackRepository browse-filter contract.
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
        """Return one keyset page of Tracks ordered (current_path, track_id)."""
        if (grouping is None) != (group_key is None):
            raise ValueError(TRACK_GROUP_FILTER_PAIRING_MESSAGE)
        tracks = [
            track
            for track in self.records.values()
            if (library_id is None or track.library_id == library_id)
            and (track_id is None or track.track_id == track_id)
            and (status is None or track.status == status)
            and (not search or _track_matches_search(track, search))
            and (grouping is None or group_key is None or derive_track_group_key(track, grouping).key == group_key)
        ]
        if grouping is None:
            tracks.sort(key=lambda track: (track.current_path, str(track.track_id)))
        else:
            tracks.sort(key=track_group_member_sort_key)
        total = len(tracks)

        if page.cursor_key is not None:
            if grouping is None:
                if len(page.cursor_key) != KEYSET_CURSOR_KEY_LENGTH:
                    raise CursorDecodeError(INVALID_CURSOR_MESSAGE)
                cursor_path, cursor_track_id = page.cursor_key
                tracks = [
                    track
                    for track in tracks
                    if (track.current_path, str(track.track_id)) > (cursor_path, cursor_track_id)
                ]
            else:
                cursor = _track_group_member_cursor_from_key(page.cursor_key)
                tracks = [track for track in tracks if track_group_member_sort_key(track) > cursor]

        page_items = tuple(tracks[: page.limit])
        has_more = len(tracks) > page.limit
        if has_more:
            next_cursor_key = (
                (page_items[-1].current_path, str(page_items[-1].track_id))
                if grouping is None
                else tuple(str(value) for value in track_group_member_sort_key(page_items[-1]))
            )
        else:
            next_cursor_key = None
        return Page(items=page_items, next_cursor_key=next_cursor_key, total=total)

    def status_facets(self, library_id: LibraryId | None, *, search: str | None = None) -> tuple[FacetValue, ...]:
        """Return Track status facet counts, ordered count DESC then value ASC."""
        counts: dict[str, int] = {}
        for track in self.records.values():
            if library_id is not None and track.library_id != library_id:
                continue
            if search and not _track_matches_search(track, search):
                continue
            counts[track.status.value] = counts.get(track.status.value, 0) + 1
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return tuple(FacetValue(value=value, count=count) for value, count in ordered)

    def group_page(  # noqa: PLR0913  # Mirrors the stable TrackRepository group contract.
        self,
        library_id: LibraryId | None,
        grouping: TrackGrouping,
        parent_key: str | None,
        page: PageRequest,
        *,
        search: str | None = None,
        status: TrackStatus | None = None,
    ) -> Page[GroupCount]:
        """Return one keyset page of Track groups ordered count DESC then key ASC."""
        groups: dict[str, tuple[str, int]] = {}
        for track in self.records.values():
            if library_id is not None and track.library_id != library_id:
                continue
            if search and not _track_matches_search(track, search):
                continue
            if status is not None and track.status is not status:
                continue
            if (
                grouping is TrackGrouping.ALBUM
                and derive_track_group_key(track, TrackGrouping.ARTIST).key != parent_key
            ):
                continue
            if grouping is TrackGrouping.DISC and derive_track_group_key(track, TrackGrouping.ALBUM).key != parent_key:
                continue
            derived = derive_track_group_key(track, grouping)
            label, count = groups.get(derived.key, (derived.label, 0))
            groups[derived.key] = (label, count + 1)

        return paginate_group_counts(
            [GroupCount(key=key, label=label, count=count) for key, (label, count) in groups.items()],
            page,
        )


def _track_matches_search(track: Track, search: str) -> bool:
    needle = ascii_lower(search)
    haystacks = (
        track.metadata.title,
        track.metadata.artist,
        track.metadata.album,
        track.current_path,
        str(track.track_id),
    )
    return any(haystack is not None and needle in ascii_lower(haystack) for haystack in haystacks)


def _track_group_member_cursor_from_key(cursor_key: tuple[str, ...]) -> tuple[int, int, str, str]:
    """Decode the exact grouped Track member cursor shape used by the SQLite adapter."""
    if len(cursor_key) != TRACK_GROUP_MEMBER_CURSOR_KEY_LENGTH:
        raise CursorDecodeError(INVALID_CURSOR_MESSAGE)
    rank_text, number_text, title, track_id = cursor_key
    try:
        return (int(rank_text), int(number_text), title, track_id)
    except ValueError as error:
        raise CursorDecodeError(INVALID_CURSOR_MESSAGE) from error


@dataclass(slots=True)
class InMemoryCompanionAssetRepository:
    """In-memory CompanionAssetRepository fake."""

    records: dict[CompanionAssetId, CompanionAsset] = field(default_factory=dict)

    def get(self, companion_asset_id: CompanionAssetId) -> CompanionAsset | None:
        """Return one companion asset by stable ID."""
        return self.records.get(companion_asset_id)

    def list_by_library(self, library_id: LibraryId) -> tuple[CompanionAsset, ...]:
        """Return companion assets for one Library in stable path order."""
        return tuple(
            sorted(
                (asset for asset in self.records.values() if asset.library_id == library_id),
                key=lambda asset: (asset.current_path, str(asset.companion_asset_id)),
            )
        )

    def save(self, companion_asset: CompanionAsset) -> None:
        """Store or replace one companion asset."""
        self.records[companion_asset.companion_asset_id] = companion_asset


@dataclass(slots=True)
class InMemoryPlanRepository:
    """In-memory PlanRepository fake."""

    records: dict[PlanId, Plan] = field(default_factory=dict)
    plan_actions: InMemoryPlanActionRepository | None = field(default=None, repr=False)

    def get(self, plan_id: PlanId) -> Plan | None:
        """Return one Plan by ID."""
        return self.records.get(plan_id)

    def list_by_library(self, library_id: LibraryId) -> tuple[Plan, ...]:
        """Return Plans owned by a Library."""
        return tuple(plan for plan in self.records.values() if plan.library_id == library_id)

    def list_by_source_run(self, source_run_id: RunId) -> tuple[Plan, ...]:
        """Return Undo Plans that record one source Run, in creation order."""
        plans = (
            plan
            for plan in self.records.values()
            if plan.plan_type is PlanType.UNDO and plan.source_run_id == source_run_id
        )
        return tuple(sorted(plans, key=lambda plan: (plan.created_at, str(plan.plan_id))))

    def save(self, plan: Plan) -> None:
        """Store or replace one Plan."""
        self.records[plan.plan_id] = plan

    def compare_and_set_status(
        self,
        plan_id: PlanId,
        expected_status: PlanStatus,
        replacement_status: PlanStatus,
    ) -> bool:
        """Replace one fake Plan status only when the current state matches."""
        plan = self.records.get(plan_id)
        if plan is None or plan.status is not expected_status:
            return False
        if replacement_status is PlanStatus.APPLYING:
            replacement = replace(plan, status=PlanStatus.APPLYING)
        elif replacement_status is PlanStatus.CANCELLED:
            replacement = plan.mark_cancelled()
        else:
            raise ValueError(replacement_status)
        self.records[plan_id] = replacement
        return True

    def query_page(  # noqa: PLR0913  # Mirrors the stable PlanRepository browse contract.
        self,
        library_id: LibraryId | None,
        *,
        search: str | None = None,
        status: PlanStatus | None,
        plan_type: PlanType | None,
        blocked_only: bool = False,
        page: PageRequest,
    ) -> Page[Plan]:
        """Return one keyset page of Plans ordered (created_at DESC, plan_id DESC)."""
        plans = [
            plan
            for plan in self.records.values()
            if (library_id is None or plan.library_id == library_id)
            and (search is None or _plan_matches_search(plan, search))
            and (status is None or plan.status == status)
            and (plan_type is None or plan.plan_type == plan_type)
            and (not blocked_only or self._has_blocked_action(plan.plan_id))
        ]
        plans.sort(key=lambda plan: (plan.created_at, str(plan.plan_id)), reverse=True)
        total = len(plans)

        if page.cursor_key is not None:
            if len(page.cursor_key) != KEYSET_CURSOR_KEY_LENGTH:
                raise CursorDecodeError(INVALID_CURSOR_MESSAGE)
            cursor_created_at, cursor_plan_id = page.cursor_key
            plans = [
                plan
                for plan in plans
                if (plan.created_at.isoformat(), str(plan.plan_id)) < (cursor_created_at, cursor_plan_id)
            ]

        page_items = tuple(plans[: page.limit])
        has_more = len(plans) > page.limit
        next_cursor_key = (page_items[-1].created_at.isoformat(), str(page_items[-1].plan_id)) if has_more else None
        return Page(items=page_items, next_cursor_key=next_cursor_key, total=total)

    def _has_blocked_action(self, plan_id: PlanId) -> bool:
        """Return whether this fake UnitOfWork records a currently blocked action for the Plan."""
        repository = self.plan_actions
        return repository is not None and any(
            action.plan_id == plan_id and action.status is ActionStatus.BLOCKED
            for action in repository.records.values()
        )


def _plan_matches_search(plan: Plan, search: str) -> bool:
    """Mirror the persisted Plan header substring-search fields."""
    needle = ascii_lower(search)
    values = (
        str(plan.plan_id),
        str(plan.library_id),
        plan.plan_type.value,
        plan.status.value,
    )
    return any(needle in ascii_lower(value) for value in values)


@dataclass(slots=True)
class InMemoryPlanActionRepository:
    """In-memory PlanActionRepository fake."""

    records: dict[ActionId, PlanAction] = field(default_factory=dict)

    def get(self, action_id: ActionId) -> PlanAction | None:
        """Return one PlanAction by ID."""
        return self.records.get(action_id)

    def list_by_plan(self, plan_id: PlanId) -> tuple[PlanAction, ...]:
        """Return PlanActions for a Plan in apply order."""
        return tuple(
            sorted(
                (action for action in self.records.values() if action.plan_id == plan_id),
                key=lambda action: action.sort_order,
            )
        )

    def save(self, action: PlanAction) -> None:
        """Store or replace one PlanAction."""
        self.records[action.action_id] = action

    def query_page(  # noqa: PLR0913  # Mirrors the stable PlanActionRepository browse contract.
        self,
        plan_id: PlanId,
        *,
        search: str | None = None,
        status: ActionStatus | None,
        action_type: ActionType | None = None,
        reason: PlanActionReason | None = None,
        page: PageRequest,
    ) -> Page[PlanAction]:
        """Return one keyset page of a Plan's actions ordered (sort_order, action_id)."""
        actions = [
            action
            for action in self.records.values()
            if action.plan_id == plan_id
            and (not search or _plan_action_matches_search(action, search))
            and (status is None or action.status is status)
            and (action_type is None or action.action_type is action_type)
            and (reason is None or action.reason is reason)
        ]
        actions.sort(key=lambda action: (action.sort_order, str(action.action_id)))
        total = len(actions)

        if page.cursor_key is not None:
            if len(page.cursor_key) != KEYSET_CURSOR_KEY_LENGTH:
                raise CursorDecodeError(INVALID_CURSOR_MESSAGE)
            cursor_sort_order_text, cursor_action_id = page.cursor_key
            try:
                cursor_sort_order = int(cursor_sort_order_text)
            except ValueError as error:
                raise CursorDecodeError(INVALID_CURSOR_MESSAGE) from error
            actions = [
                action
                for action in actions
                if (action.sort_order, str(action.action_id)) > (cursor_sort_order, cursor_action_id)
            ]

        page_items = tuple(actions[: page.limit])
        has_more = len(actions) > page.limit
        next_cursor_key = (str(page_items[-1].sort_order), str(page_items[-1].action_id)) if has_more else None
        return Page(items=page_items, next_cursor_key=next_cursor_key, total=total)

    def status_facets(
        self,
        plan_id: PlanId,
        *,
        search: str | None = None,
        action_type: ActionType | None = None,
        reason: PlanActionReason | None = None,
    ) -> tuple[FacetValue, ...]:
        """Return PlanAction status facets for one Plan, ordered count DESC then value ASC."""
        counts: dict[str, int] = {}
        for action in self.records.values():
            if action.plan_id != plan_id or (search and not _plan_action_matches_search(action, search)):
                continue
            if action_type is not None and action.action_type is not action_type:
                continue
            if reason is not None and action.reason is not reason:
                continue
            counts[action.status.value] = counts.get(action.status.value, 0) + 1
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return tuple(FacetValue(value=value, count=count) for value, count in ordered)

    def action_type_facets(
        self,
        plan_id: PlanId,
        *,
        search: str | None = None,
        status: ActionStatus | None = None,
        reason: PlanActionReason | None = None,
    ) -> tuple[FacetValue, ...]:
        """Return PlanAction type facets for one Plan, ordered count DESC then value ASC."""
        counts: dict[str, int] = {}
        for action in self.records.values():
            if action.plan_id != plan_id or (search and not _plan_action_matches_search(action, search)):
                continue
            if status is not None and action.status is not status:
                continue
            if reason is not None and action.reason is not reason:
                continue
            counts[action.action_type.value] = counts.get(action.action_type.value, 0) + 1
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return tuple(FacetValue(value=value, count=count) for value, count in ordered)

    def reason_facets(
        self,
        plan_id: PlanId,
        *,
        search: str | None = None,
        status: ActionStatus | None = None,
        action_type: ActionType | None = None,
    ) -> tuple[FacetValue, ...]:
        """Return non-null PlanAction reason facets for one Plan, ordered count DESC then value ASC."""
        counts: dict[str, int] = {}
        for action in self.records.values():
            if action.plan_id != plan_id or action.reason is None:
                continue
            if search and not _plan_action_matches_search(action, search):
                continue
            if status is not None and action.status is not status:
                continue
            if action_type is not None and action.action_type is not action_type:
                continue
            counts[action.reason.value] = counts.get(action.reason.value, 0) + 1
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return tuple(FacetValue(value=value, count=count) for value, count in ordered)

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
        return sum(
            1
            for action in self.records.values()
            if action.plan_id == plan_id
            and (not search or _plan_action_matches_search(action, search))
            and (status is None or action.status is status)
            and (action_type is None or action.action_type is action_type)
            and (reason is None or action.reason is reason)
        )

    def count_target_collisions(self, plan_id: PlanId) -> int:
        """Return how many distinct non-null target_path values are recorded by 2+ of the Plan's actions."""
        counts: dict[str, int] = {}
        for action in self.records.values():
            if action.plan_id != plan_id or action.target_path is None:
                continue
            counts[action.target_path] = counts.get(action.target_path, 0) + 1
        return sum(1 for count in counts.values() if count > 1)

    def action_counts_by_plan(
        self,
        plan_ids: Sequence[PlanId],
    ) -> dict[PlanId, dict[tuple[ActionStatus, ActionType], int]]:
        """Return current status/action-type counts for every requested Plan."""
        counts_by_plan: dict[PlanId, dict[tuple[ActionStatus, ActionType], int]] = {plan_id: {} for plan_id in plan_ids}
        for action in self.records.values():
            counts = counts_by_plan.get(action.plan_id)
            if counts is None:
                continue
            key = (action.status, action.action_type)
            counts[key] = counts.get(key, 0) + 1
        return counts_by_plan

    def list_by_ids(self, action_ids: Sequence[ActionId]) -> tuple[PlanAction, ...]:
        """Return the PlanActions with the given IDs, ordered (sort_order, action_id)."""
        wanted = set(action_ids)
        return tuple(
            sorted(
                (action for action in self.records.values() if action.action_id in wanted),
                key=lambda action: (action.sort_order, str(action.action_id)),
            )
        )

    def list_group_rows(self, plan_id: PlanId) -> tuple[PlanActionGroupRow, ...]:
        """Return per-action group projections for one Plan, ordered (sort_order, action_id)."""
        actions = sorted(
            (action for action in self.records.values() if action.plan_id == plan_id),
            key=lambda action: (action.sort_order, str(action.action_id)),
        )
        return tuple(
            PlanActionGroupRow(
                action_id=action.action_id,
                track_id=action.track_id,
                sort_order=action.sort_order,
                status=action.status,
                reason=action.reason,
                action_type=action.action_type,
                source_path=action.source_path,
                target_path=action.target_path,
                content_hash_at_plan=action.content_hash_at_plan,
                metadata_hash_at_plan=action.metadata_hash_at_plan,
            )
            for action in actions
        )


def _plan_action_matches_search(action: PlanAction, search: str) -> bool:
    """Mirror the persisted PlanAction substring-search fields."""
    needle = ascii_lower(search)
    values = (
        str(action.action_id),
        None if action.track_id is None else str(action.track_id),
        None if action.companion_asset_id is None else str(action.companion_asset_id),
        None if action.owner_action_id is None else str(action.owner_action_id),
        action.source_path,
        action.target_path,
        action.content_hash_at_plan,
        action.metadata_hash_at_plan,
    )
    return any(value is not None and needle in ascii_lower(value) for value in values)


@dataclass(slots=True)
class InMemoryPlanActionDependencyRepository:
    """In-memory PlanActionDependencyRepository fake."""

    records: dict[tuple[ActionId, ActionId], PlanActionDependency] = field(default_factory=dict)

    def list_by_action(self, action_id: ActionId) -> tuple[PlanActionDependency, ...]:
        """Return one action's dependencies in stable dependency-ID order."""
        return tuple(
            sorted(
                (dependency for dependency in self.records.values() if dependency.action_id == action_id),
                key=lambda dependency: str(dependency.depends_on_action_id),
            )
        )

    def save(self, dependency: PlanActionDependency) -> None:
        """Store or replace one PlanAction dependency."""
        self.records[(dependency.action_id, dependency.depends_on_action_id)] = dependency


@dataclass(slots=True)
class InMemoryRunRepository:
    """In-memory RunRepository fake."""

    records: dict[RunId, Run] = field(default_factory=dict)

    def get(self, run_id: RunId) -> Run | None:
        """Return one Run by ID."""
        return self.records.get(run_id)

    def list_by_library(self, library_id: LibraryId) -> tuple[Run, ...]:
        """Return Runs owned by a Library."""
        return tuple(run for run in self.records.values() if run.library_id == library_id)

    def list_by_plan(self, plan_id: PlanId) -> tuple[Run, ...]:
        """Return Runs created for a Plan."""
        return tuple(run for run in self.records.values() if run.plan_id == plan_id)

    def save(self, run: Run) -> None:
        """Store or replace one Run."""
        self.records[run.run_id] = run

    def query_page(
        self,
        library_id: LibraryId | None,
        *,
        search: str | None = None,
        plan_id: PlanId | None,
        status: RunStatus | None,
        page: PageRequest,
    ) -> Page[Run]:
        """Return one keyset page of Runs ordered (started_at DESC, run_id DESC)."""
        runs = [
            run
            for run in self.records.values()
            if (library_id is None or run.library_id == library_id)
            and (search is None or _run_matches_search(run, search))
            and (plan_id is None or run.plan_id == plan_id)
            and (status is None or run.status == status)
        ]
        runs.sort(key=lambda run: (run.started_at, str(run.run_id)), reverse=True)
        total = len(runs)

        if page.cursor_key is not None:
            if len(page.cursor_key) != KEYSET_CURSOR_KEY_LENGTH:
                raise CursorDecodeError(INVALID_CURSOR_MESSAGE)
            cursor_started_at, cursor_run_id = page.cursor_key
            runs = [
                run
                for run in runs
                if (run.started_at.isoformat(), str(run.run_id)) < (cursor_started_at, cursor_run_id)
            ]

        page_items = tuple(runs[: page.limit])
        has_more = len(runs) > page.limit
        next_cursor_key = (page_items[-1].started_at.isoformat(), str(page_items[-1].run_id)) if has_more else None
        return Page(items=page_items, next_cursor_key=next_cursor_key, total=total)

    def status_facets(self, library_id: LibraryId | None) -> tuple[FacetValue, ...]:
        """Return Run status facet counts, ordered count DESC then value ASC."""
        counts: dict[str, int] = {}
        for run in self.records.values():
            if library_id is not None and run.library_id != library_id:
                continue
            counts[run.status.value] = counts.get(run.status.value, 0) + 1
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return tuple(FacetValue(value=value, count=count) for value, count in ordered)


def _run_matches_search(run: Run, search: str) -> bool:
    """Mirror the persisted Run substring-search fields."""
    needle = ascii_lower(search)
    values = (
        str(run.run_id),
        str(run.plan_id),
        str(run.library_id),
        run.status.value,
        run.error_summary,
    )
    return any(value is not None and needle in ascii_lower(value) for value in values)


@dataclass(slots=True)
class InMemoryFileEventRepository:
    """In-memory FileEventRepository fake."""

    records: dict[EventId, FileEvent] = field(default_factory=dict)

    def get(self, event_id: EventId) -> FileEvent | None:
        """Return one FileEvent by ID."""
        return self.records.get(event_id)

    def list_by_run(self, run_id: RunId) -> tuple[FileEvent, ...]:
        """Return FileEvents for a Run in durable sequence order."""
        return tuple(
            sorted(
                (event for event in self.records.values() if event.run_id == run_id),
                key=lambda event: event.sequence_no,
            )
        )

    def list_by_library(self, library_id: LibraryId) -> tuple[FileEvent, ...]:
        """Return FileEvents for a Library in durable order."""
        return tuple(
            sorted(
                (event for event in self.records.values() if event.library_id == library_id),
                key=lambda event: (event.started_at, event.sequence_no, event.event_id),
            )
        )

    def list_pending_by_library(self, library_id: LibraryId) -> tuple[FileEvent, ...]:
        """Return PENDING FileEvents for a Library in durable sequence order."""
        return tuple(
            sorted(
                (
                    event
                    for event in self.records.values()
                    if event.library_id == library_id and event.status == FileEventStatus.PENDING
                ),
                key=lambda event: event.sequence_no,
            )
        )

    def save(self, event: FileEvent) -> None:
        """Store or replace one FileEvent."""
        self.records[event.event_id] = event

    def query_page(
        self,
        run_id: RunId,
        *,
        status: FileEventStatus | None,
        page: PageRequest,
    ) -> Page[FileEvent]:
        """Return one keyset page of a Run's FileEvents ordered (sequence_no, event_id)."""
        events = [
            event
            for event in self.records.values()
            if event.run_id == run_id and (status is None or event.status == status)
        ]
        events.sort(key=lambda event: (event.sequence_no, str(event.event_id)))
        total = len(events)

        if page.cursor_key is not None:
            if len(page.cursor_key) != KEYSET_CURSOR_KEY_LENGTH:
                raise CursorDecodeError(INVALID_CURSOR_MESSAGE)
            cursor_sequence_no_text, cursor_event_id = page.cursor_key
            try:
                cursor_sequence_no = int(cursor_sequence_no_text)
            except ValueError as error:
                raise CursorDecodeError(INVALID_CURSOR_MESSAGE) from error
            events = [
                event
                for event in events
                if (event.sequence_no, str(event.event_id)) > (cursor_sequence_no, cursor_event_id)
            ]

        page_items = tuple(events[: page.limit])
        has_more = len(events) > page.limit
        next_cursor_key = (str(page_items[-1].sequence_no), str(page_items[-1].event_id)) if has_more else None
        return Page(items=page_items, next_cursor_key=next_cursor_key, total=total)

    def status_facets(self, run_id: RunId) -> tuple[FacetValue, ...]:
        """Return FileEvent status facet counts, ordered count DESC then value ASC."""
        counts: dict[str, int] = {}
        for event in self.records.values():
            if event.run_id != run_id:
                continue
            counts[event.status.value] = counts.get(event.status.value, 0) + 1
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return tuple(FacetValue(value=value, count=count) for value, count in ordered)

    def list_target_paths(self, run_id: RunId) -> tuple[str, ...]:
        """Return target_path values for a Run in durable sequence order."""
        return tuple(event.target_path for event in self.list_by_run(run_id))


@dataclass(slots=True)
class InMemoryOperationRepository:
    """In-memory OperationRepository fake."""

    records: dict[OperationId, OperationLookup] = field(default_factory=dict)

    def lookup(self, operation_id: OperationId) -> OperationLookup | None:
        """Return a full Operation or retained tombstone by stable ID."""
        return self.records.get(operation_id)

    def find_by_idempotency_key(self, idempotency_key: UUID) -> OperationLookup | None:
        """Return retained request identity for idempotent replay classification."""
        return next(
            (record for record in self.records.values() if record.idempotency_key == idempotency_key),
            None,
        )

    def list_reconciliation_candidates(self) -> tuple[Operation, ...]:
        """Return full unfinished/interrupted Operations in deterministic request order."""
        candidates = (
            record
            for record in self.records.values()
            if isinstance(record, Operation)
            and record.status in {OperationStatus.QUEUED, OperationStatus.RUNNING, OperationStatus.INTERRUPTED}
        )
        return tuple(sorted(candidates, key=lambda record: (record.requested_at, str(record.operation_id))))

    def find_active(self) -> Operation | None:
        """Return the single queued or running Operation, if one exists."""
        return next(
            (
                record
                for record in self.list_reconciliation_candidates()
                if record.status in {OperationStatus.QUEUED, OperationStatus.RUNNING}
            ),
            None,
        )

    def save(self, operation: Operation) -> None:
        """Store or replace one full Operation."""
        self.records[operation.operation_id] = operation

    def expire_terminal_payloads(self, now: datetime) -> int:
        """Replace expired full Operations with minimal retained tombstones."""
        expired = tuple(
            operation
            for operation in self.records.values()
            if isinstance(operation, Operation)
            and operation.is_terminal
            and operation.result_expires_at is not None
            and operation.result_expires_at <= now
        )
        for operation in expired:
            if operation.tombstone_expires_at is None:
                continue
            self.records[operation.operation_id] = OperationTombstone(
                operation_id=operation.operation_id,
                idempotency_key=operation.idempotency_key,
                kind=operation.kind,
                request_fingerprint=operation.request_fingerprint,
                tombstone_expires_at=operation.tombstone_expires_at,
            )
        return len(expired)

    def purge_expired_tombstones(self, now: datetime) -> int:
        """Delete terminal records whose tombstone retention elapsed."""
        expired_ids = tuple(
            operation_id
            for operation_id, record in self.records.items()
            if (isinstance(record, OperationTombstone) and record.tombstone_expires_at <= now)
            or (
                isinstance(record, Operation)
                and record.is_terminal
                and record.tombstone_expires_at is not None
                and record.tombstone_expires_at <= now
            )
        )
        for operation_id in expired_ids:
            del self.records[operation_id]
        return len(expired_ids)


@dataclass(slots=True)
class InMemoryUnitOfWork:
    """In-memory UnitOfWork fake with observable transaction calls."""

    accepted_artist_names: InMemoryAcceptedArtistNameRepository = field(
        default_factory=InMemoryAcceptedArtistNameRepository
    )
    libraries: InMemoryLibraryRepository = field(default_factory=InMemoryLibraryRepository)
    check_runs: InMemoryCheckRunRepository = field(default_factory=InMemoryCheckRunRepository)
    check_issues: InMemoryCheckIssueRepository = field(default_factory=InMemoryCheckIssueRepository)
    tracks: InMemoryTrackRepository = field(default_factory=InMemoryTrackRepository)
    companion_assets: InMemoryCompanionAssetRepository = field(default_factory=InMemoryCompanionAssetRepository)
    plans: InMemoryPlanRepository = field(default_factory=InMemoryPlanRepository)
    plan_actions: InMemoryPlanActionRepository = field(default_factory=InMemoryPlanActionRepository)
    plan_action_dependencies: InMemoryPlanActionDependencyRepository = field(
        default_factory=InMemoryPlanActionDependencyRepository
    )
    runs: InMemoryRunRepository = field(default_factory=InMemoryRunRepository)
    file_events: InMemoryFileEventRepository = field(default_factory=InMemoryFileEventRepository)
    operations: InMemoryOperationRepository = field(default_factory=InMemoryOperationRepository)
    commit_count: int = 0
    rollback_count: int = 0
    usecase_scope_enter_count: int = 0
    usecase_scope_exit_count: int = 0

    def __post_init__(self) -> None:
        """Wire the Plan query fake to the current PlanAction fake for blocked filtering."""
        self.plans.plan_actions = self.plan_actions

    @contextmanager
    def usecase_scope(self) -> Generator[None]:
        """Record one outer usecase lifetime without changing transaction behavior."""
        self.usecase_scope_enter_count += 1
        try:
            yield
        finally:
            self.usecase_scope_exit_count += 1

    def __enter__(self) -> Self:
        """Open the fake transaction boundary."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        """Rollback on exceptions so tests can assert transaction intent."""
        del exc, tb
        if exc_type is not None:
            self.rollback()
        return None

    def commit(self) -> None:
        """Record a commit call."""
        self.commit_count += 1

    def rollback(self) -> None:
        """Record a rollback call."""
        self.rollback_count += 1

    def claim_apply(self, plan_id: PlanId, run: Run, operation: Operation) -> bool:
        """Stage one fake atomic Apply claim for feature tests."""
        claimed = self.plans.compare_and_set_status(plan_id, PlanStatus.READY, PlanStatus.APPLYING)
        if not claimed:
            return False
        self.runs.save(run)
        self.operations.save(operation)
        return True
