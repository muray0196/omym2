"""
Summary: Implements Plan action grouping by directory, artist/album, status, reason, and extension.
Why: Lets Web review read grouped Plan action counts with blocked/reason risk enrichment and pagination.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from posixpath import basename, dirname, splitext
from typing import TYPE_CHECKING

from omym2.domain.models.plan_action import ActionStatus
from omym2.features.plans.dto import PlanActionGroup, PlanActionGrouping
from omym2.features.plans.usecases.get_plan_header import PLAN_NOT_FOUND_MESSAGE, PlanNotFoundError
from omym2.shared.pagination import paginate_group_counts

if TYPE_CHECKING:
    from omym2.features.common_ports import PlanActionGroupRow
    from omym2.features.plans.dto import GroupPlanActionsRequest
    from omym2.features.plans.ports import PlanQueryPorts
    from omym2.shared.pagination import Page

PLAN_ACTION_GROUP_ROOT_LABEL = "(root)"  # group key/label for a Library-root target or source path
PLAN_ACTION_GROUP_UNKNOWN_KEY = "(unknown)"  # artist_album group key for actions without a target path
PLAN_ACTION_GROUP_UNKNOWN_LABEL = "Unknown Artist / Unknown Album"
PLAN_ACTION_GROUP_NO_EXTENSION_KEY = "(none)"  # extension group key/label for suffix-less file names
ARTIST_ALBUM_SEGMENT_LIMIT = 2  # artist_album derives from the first two target directory segments
ARTIST_ALBUM_KEY_SEPARATOR = "/"
ARTIST_ALBUM_LABEL_SEPARATOR = " / "


@dataclass(frozen=True, slots=True)
class PlanActionGroupKey:
    """Derived group key/label pair for one PlanAction under one grouping."""

    key: str
    label: str


def derive_plan_action_group_key(row: PlanActionGroupRow, grouping: PlanActionGrouping) -> PlanActionGroupKey | None:
    """Return the group key/label one action falls into, or None when it has no bucket.

    Deriving group keys from stored paths and recorded values is a business
    rule, so it is computed here instead of in SQL. The list-actions
    drill-down filter reuses exactly this derivation for group membership.
    """
    if grouping is PlanActionGrouping.ARTIST_ALBUM:
        return _artist_album_group(row.target_path)
    if grouping is PlanActionGrouping.EXTENSION:
        return _extension_group(row)
    if grouping in (PlanActionGrouping.TARGET_DIRECTORY, PlanActionGrouping.SOURCE_DIRECTORY):
        path = row.target_path if grouping is PlanActionGrouping.TARGET_DIRECTORY else row.source_path
        return _directory_group(path)
    value = _catalog_group_value(row, grouping)
    return None if value is None else PlanActionGroupKey(key=value, label=value)


def _catalog_group_value(row: PlanActionGroupRow, grouping: PlanActionGrouping) -> str | None:
    """Return the raw catalog value for the action_type/status/block_reason groupings."""
    if grouping is PlanActionGrouping.ACTION_TYPE:
        return row.action_type.value
    if grouping is PlanActionGrouping.STATUS:
        return row.status.value
    return None if row.reason is None else row.reason.value


@dataclass(frozen=True, slots=True)
class GroupPlanActionsUseCase:
    """List a Plan's actions grouped by the requested key, ordered count DESC then key ASC.

    Each group row is enriched with `blocked_count` (members with status
    blocked) and `top_reason` (most frequent non-null member reason; ties
    resolve to the lexicographically smallest value; None without reasons).
    Actions without the grouping's source value (e.g. a null target_path for
    target_directory) are skipped, except artist_album, which buckets them
    under `(unknown)`.
    """

    ports: PlanQueryPorts

    def execute(self, request: GroupPlanActionsRequest) -> Page[PlanActionGroup]:
        """Return one page of enriched action groups for the Plan.

        Raises PlanNotFoundError for an unknown Plan ID before listing rows.
        """
        with self.ports.uow as uow:
            if uow.plans.get(request.plan_id) is None:
                raise PlanNotFoundError(PLAN_NOT_FOUND_MESSAGE)
            rows = uow.plan_actions.list_group_rows(request.plan_id)

        accumulators: dict[str, _GroupAccumulator] = {}
        for row in rows:
            derived = derive_plan_action_group_key(row, request.grouping)
            if derived is None:
                continue
            accumulator = accumulators.setdefault(derived.key, _GroupAccumulator(label=derived.label))
            accumulator.count += 1
            if row.status is ActionStatus.BLOCKED:
                accumulator.blocked_count += 1
            if row.reason is not None:
                accumulator.reason_counts[row.reason.value] = accumulator.reason_counts.get(row.reason.value, 0) + 1

        groups = tuple(
            PlanActionGroup(
                key=key,
                label=accumulator.label,
                count=accumulator.count,
                blocked_count=accumulator.blocked_count,
                top_reason=_top_reason(accumulator.reason_counts),
            )
            for key, accumulator in accumulators.items()
        )
        return paginate_group_counts(groups, request.page)


@dataclass(slots=True)
class _GroupAccumulator:
    """Mutable per-group tally collected while walking the action projection."""

    label: str
    count: int = 0
    blocked_count: int = 0
    reason_counts: dict[str, int] = field(default_factory=dict)


def _top_reason(reason_counts: dict[str, int]) -> str | None:
    """Return the most frequent reason, breaking count ties by the smaller value."""
    if not reason_counts:
        return None
    return min(reason_counts.items(), key=lambda item: (-item[1], item[0]))[0]


def _directory_group(path: str | None) -> PlanActionGroupKey | None:
    """Group a stored path by its POSIX parent directory; a null path has no bucket."""
    if path is None:
        return None
    directory = dirname(path) or PLAN_ACTION_GROUP_ROOT_LABEL
    return PlanActionGroupKey(key=directory, label=directory)


def _artist_album_group(target_path: str | None) -> PlanActionGroupKey:
    """Group by the first two target directory segments; null targets bucket under `(unknown)`.

    Under the default path template `{album_artist}/{year}_{album}/...` the
    first two segments are the album-artist and album directories. This is a
    directory-structure derivation, not a Track metadata join: add-Plan
    actions carry no track_id, so no join is possible.
    """
    if target_path is None:
        return PlanActionGroupKey(key=PLAN_ACTION_GROUP_UNKNOWN_KEY, label=PLAN_ACTION_GROUP_UNKNOWN_LABEL)
    segments = [segment for segment in dirname(target_path).split("/") if segment][:ARTIST_ALBUM_SEGMENT_LIMIT]
    if not segments:
        return PlanActionGroupKey(key=PLAN_ACTION_GROUP_ROOT_LABEL, label=PLAN_ACTION_GROUP_ROOT_LABEL)
    return PlanActionGroupKey(
        key=ARTIST_ALBUM_KEY_SEPARATOR.join(segments),
        label=ARTIST_ALBUM_LABEL_SEPARATOR.join(segments),
    )


def _extension_group(row: PlanActionGroupRow) -> PlanActionGroupKey | None:
    """Group by the lowercased file suffix of source_path, falling back to target_path."""
    path = row.source_path if row.source_path is not None else row.target_path
    if path is None:
        return None
    suffix = splitext(basename(path))[1].removeprefix(".").lower()
    key = suffix or PLAN_ACTION_GROUP_NO_EXTENSION_KEY
    return PlanActionGroupKey(key=key, label=key)
