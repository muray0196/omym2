"""
Summary: Implements SQLite-backed domain repositories.
Why: Persists OMYM2 state without moving business rules into the DB adapter.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, cast
from uuid import UUID

from omym2.config import PERSISTED_JSON_ITEM_SEPARATOR, PERSISTED_JSON_KEY_SEPARATOR
from omym2.domain.models.check_issue import (
    CHECK_ISSUE_GROUP_ARTIST_ALBUM_LABEL_SEPARATOR,
    CHECK_ISSUE_GROUP_EXTERNAL_KEY,
    CHECK_ISSUE_GROUP_ROOT_KEY,
    CHECK_ISSUE_GROUP_UNKNOWN_ARTIST_ALBUM_LABEL,
    CHECK_ISSUE_GROUP_UNKNOWN_KEY,
    CheckIssue,
    CheckIssueGrouping,
    CheckIssueType,
)
from omym2.domain.models.check_run import CheckRun
from omym2.domain.models.file_event import FileEvent, FileEventStatus, FileEventType
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.operation import (
    CheckCompletedResult,
    Operation,
    OperationError,
    OperationErrorCode,
    OperationKind,
    OperationLookup,
    OperationProgress,
    OperationRemediation,
    OperationResult,
    OperationResultKind,
    OperationStatus,
    OperationTombstone,
    PlanCreatedResult,
    RegisteredWithoutPlanResult,
    RunCompletedResult,
)
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction, PlanActionReason
from omym2.domain.models.run import Run, RunStatus
from omym2.domain.models.track import (
    TRACK_GROUP_DISC_LABEL_PREFIX,
    TRACK_GROUP_LABEL_SEPARATOR,
    TRACK_GROUP_METADATA_WHITESPACE,
    TRACK_GROUP_UNKNOWN_KEY,
    TRACK_GROUP_UNNUMBERED_DISC_LABEL,
    Track,
    TrackGrouping,
    TrackStatus,
)
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.features.common_ports import CheckIssueGroup, PlanActionGroupRow
from omym2.shared.ids import (
    ActionId,
    CheckRunId,
    EventId,
    LibraryId,
    OperationId,
    PlanId,
    RunId,
    TrackId,
    parse_uuid,
)
from omym2.shared.pagination import INVALID_CURSOR_MESSAGE, CursorDecodeError, FacetValue, GroupCount, Page
from omym2.shared.time import as_utc

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Mapping, Sequence

    from omym2.shared.pagination import PageRequest

INVALID_JSON_OBJECT_MESSAGE = "Persisted JSON payload must be an object."
INVALID_METADATA_VALUE_MESSAGE = "Persisted metadata JSON contains an unsupported value."
INVALID_ROW_TEXT_MESSAGE = "Expected SQLite text value."
INVALID_ROW_INTEGER_MESSAGE = "Expected SQLite integer value."
INVALID_SUMMARY_VALUE_MESSAGE = "Persisted summary JSON must contain string values."
INVALID_OPERATION_PAYLOAD_MESSAGE = "Persisted Operation JSON does not match its typed discriminant."
LIKE_ESCAPE_CHAR = "\\"  # escape character used for LIKE search patterns
UNSUPPORTED_TRACK_GROUPING_MESSAGE = "Unsupported Track grouping"
TRACK_GROUP_FILTER_PAIRING_MESSAGE = "grouping and group_key must be provided together."
KEYSET_CURSOR_KEY_LENGTH = 2  # every keyset cursor key in this module is a 2-tuple
CHECK_ISSUE_CURSOR_KEY_LENGTH = 1  # a CheckIssue cursor key is a single issue_seq value
TRACK_GROUP_MEMBER_CURSOR_KEY_LENGTH = 4  # grouped Track member cursor: rank, number, title, track ID
MIN_POSITIVE_METADATA_NUMBER = 1  # positive raw TrackMetadata disc/track number lower bound
NUMBERED_TRACK_ORDER_RANK = 0  # grouped Track members with a positive track number sort first
UNNUMBERED_TRACK_ORDER_RANK = 1  # grouped Track members without a positive track number sort last
UNNUMBERED_TRACK_ORDER_VALUE = 0  # neutral numeric key for unnumbered grouped Track members

TRACK_SEARCH_WHERE_CLAUSE = f"""(
                LOWER(json_extract(metadata_json, '$.title')) LIKE LOWER(?) ESCAPE '{LIKE_ESCAPE_CHAR}' OR
                LOWER(json_extract(metadata_json, '$.artist')) LIKE LOWER(?) ESCAPE '{LIKE_ESCAPE_CHAR}' OR
                LOWER(json_extract(metadata_json, '$.album')) LIKE LOWER(?) ESCAPE '{LIKE_ESCAPE_CHAR}' OR
                LOWER(current_path) LIKE LOWER(?) ESCAPE '{LIKE_ESCAPE_CHAR}' OR
                LOWER(track_id) LIKE LOWER(?) ESCAPE '{LIKE_ESCAPE_CHAR}'
            )"""
PLAN_ACTION_SEARCH_COLUMN_NAMES = (
    "action_id",
    "track_id",
    "source_path",
    "target_path",
    "content_hash_at_plan",
    "metadata_hash_at_plan",
)
PLAN_SEARCH_COLUMN_NAMES = (
    "plan_id",
    "library_id",
    "plan_type",
    "status",
)
RUN_SEARCH_COLUMN_NAMES = ("run_id", "plan_id", "library_id", "status", "error_summary")
CHECK_ISSUE_SEARCH_COLUMN_NAMES = ("library_id", "path", "track_id", "plan_id", "detail")
TRACK_GROUP_SOURCE_SELECT = """
            SELECT
                COALESCE(json_extract(metadata_json, '$.album_artist'), json_extract(metadata_json, '$.artist'), ?)
                    AS group_artist,
                COALESCE(json_extract(metadata_json, '$.album'), ?) AS group_album
            FROM tracks
"""
CHECK_ISSUE_PATH_ROOT_SELECT = f"""
                CASE
                    WHEN ci.path IS NULL OR ci.path = '' THEN NULL
                    WHEN substr(ci.path, 1, 1) = '/' THEN '{CHECK_ISSUE_GROUP_EXTERNAL_KEY}'
                    WHEN instr(ci.path, '/') = 0 THEN '{CHECK_ISSUE_GROUP_ROOT_KEY}'
                    ELSE substr(ci.path, 1, instr(ci.path, '/'))
                END
"""
CHECK_ISSUE_ARTIST_SEGMENT_SELECT = f"""
                CASE
                    WHEN ci.path IS NULL OR ci.path = '' THEN NULL
                    WHEN substr(ci.path, 1, 1) = '/' THEN '{CHECK_ISSUE_GROUP_EXTERNAL_KEY}'
                    WHEN instr(ci.path, '/') = 0 THEN '{CHECK_ISSUE_GROUP_ROOT_KEY}'
                    ELSE substr(ci.path, 1, instr(ci.path, '/') - 1)
                END
"""
CHECK_ISSUE_ALBUM_SEGMENT_SELECT = f"""
                CASE
                    WHEN ci.path IS NULL OR ci.path = '' THEN NULL
                    WHEN substr(ci.path, 1, 1) = '/' THEN '{CHECK_ISSUE_GROUP_EXTERNAL_KEY}'
                    WHEN instr(ci.path, '/') = 0 THEN '{CHECK_ISSUE_GROUP_ROOT_KEY}'
                    WHEN instr(substr(ci.path, instr(ci.path, '/') + 1), '/') = 0 THEN '{CHECK_ISSUE_GROUP_ROOT_KEY}'
                    ELSE substr(
                        substr(ci.path, instr(ci.path, '/') + 1),
                        1,
                        instr(substr(ci.path, instr(ci.path, '/') + 1), '/') - 1
                    )
                END
"""
CHECK_ISSUE_SEVERITY_SELECT = """
                CASE ci.issue_type
                    WHEN 'db_file_missing' THEN 'error'
                    WHEN 'content_hash_changed' THEN 'error'
                    WHEN 'library_stale' THEN 'info'
                    ELSE 'warning'
                END
"""
CHECK_ISSUE_COMMAND_KEY_SELECT = """
                CASE
                    WHEN ci.issue_type IN ('db_file_missing', 'content_hash_changed', 'metadata_hash_changed') THEN 'refresh'
                    WHEN ci.issue_type = 'unmanaged_file_exists' THEN 'add'
                    WHEN ci.issue_type IN (
                        'current_path_differs_from_canonical_path',
                        'duplicate_candidate',
                        'plan_source_changed'
                    ) THEN 'organize'
                    WHEN ci.issue_type = 'pending_file_event_exists' THEN 'history'
                    ELSE 'check'
                END
"""
CHECK_ISSUE_COMMAND_LABEL_SELECT = """
                CASE
                    WHEN ci.issue_type IN ('db_file_missing', 'content_hash_changed', 'metadata_hash_changed')
                        THEN 'omym2 refresh <file>'
                    WHEN ci.issue_type = 'unmanaged_file_exists' THEN 'omym2 add <path>'
                    WHEN ci.issue_type IN (
                        'current_path_differs_from_canonical_path',
                        'duplicate_candidate',
                        'plan_source_changed'
                    ) THEN 'omym2 organize'
                    WHEN ci.issue_type = 'pending_file_event_exists' THEN 'omym2 history'
                    ELSE 'omym2 check'
                END
"""

TRACK_SELECT_FROM = """
            SELECT
                track_id,
                library_id,
                current_path,
                canonical_path,
                content_hash,
                metadata_hash,
                size,
                mtime,
                metadata_json,
                status,
                first_seen_at,
                last_seen_at,
                updated_at
            FROM tracks
"""
RUN_SELECT_FROM = """
            SELECT run_id, plan_id, library_id, status, started_at, completed_at, error_summary
            FROM runs
"""
PLAN_SELECT_FROM = """
            SELECT plan_id, library_id, source_run_id, plan_type, status, created_at, config_hash,
                   library_root_at_plan, summary_json
            FROM plans
"""
PLAN_ACTION_SELECT_FROM = """
            SELECT
                action_id,
                plan_id,
                library_id,
                track_id,
                action_type,
                source_path,
                target_path,
                reverses_event_id,
                content_hash_at_plan,
                metadata_hash_at_plan,
                status,
                reason,
                sort_order
            FROM plan_actions
"""
CHECK_RUN_SELECT_FROM = """
            SELECT check_run_id, library_id, checked_at, total_count
            FROM check_runs
"""
CHECK_ISSUE_SELECT_FROM = """
            SELECT issue_seq, check_run_id, library_id, issue_type, path, track_id, plan_id, detail
            FROM check_issues
"""
FILE_EVENT_SELECT_FROM = """
            SELECT
                event_id,
                library_id,
                run_id,
                plan_action_id,
                event_type,
                source_path,
                target_path,
                status,
                started_at,
                completed_at,
                error_code,
                error_message,
                sequence_no
            FROM file_events
"""
OPERATION_SELECT_FROM = """
            SELECT
                operation_id,
                library_id,
                plan_id,
                run_id,
                kind,
                status,
                idempotency_key,
                request_fingerprint,
                stage_code,
                completed_units,
                total_units,
                progress_message,
                result_kind,
                result_json,
                error_code,
                error_json,
                requested_at,
                started_at,
                updated_at,
                completed_at,
                result_expires_at,
                tombstone_expires_at
            FROM operations
"""


class _SQLiteRepository:
    """Base repository for shared SQLite connection handling."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Keep the connection owned by the surrounding UnitOfWork."""
        self._connection: sqlite3.Connection = connection


class SQLiteLibraryRepository(_SQLiteRepository):
    """SQLite implementation of LibraryRepository."""

    def get(self, library_id: LibraryId) -> Library | None:
        """Return one Library by stable ID."""
        row = _fetch_one(
            self._connection,
            """
            SELECT library_id, root_path, path_policy_hash, registered_at, status, created_at, updated_at
            FROM libraries
            WHERE library_id = ?
            """,
            (str(library_id),),
        )
        return None if row is None else _library_from_row(row)

    def find_by_root_path(self, root_path: str) -> Library | None:
        """Return the Library currently registered for a root path, if any."""
        row = _fetch_one(
            self._connection,
            """
            SELECT library_id, root_path, path_policy_hash, registered_at, status, created_at, updated_at
            FROM libraries
            WHERE root_path = ?
            """,
            (root_path,),
        )
        return None if row is None else _library_from_row(row)

    def list_all(self) -> tuple[Library, ...]:
        """Return all known Libraries."""
        rows = _fetch_all(
            self._connection,
            """
            SELECT library_id, root_path, path_policy_hash, registered_at, status, created_at, updated_at
            FROM libraries
            ORDER BY created_at, library_id
            """,
        )
        return tuple(_library_from_row(row) for row in rows)

    def save(self, library: Library) -> None:
        """Persist a Library without deciding business policy."""
        _ = self._connection.execute(
            """
            INSERT INTO libraries (
                library_id,
                root_path,
                path_policy_hash,
                registered_at,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(library_id) DO UPDATE SET
                root_path = excluded.root_path,
                path_policy_hash = excluded.path_policy_hash,
                registered_at = excluded.registered_at,
                status = excluded.status,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at
            """,
            (
                str(library.library_id),
                library.root_path,
                library.path_policy_hash,
                _optional_timestamp_to_text(library.registered_at),
                library.status.value,
                _timestamp_to_text(library.created_at),
                _timestamp_to_text(library.updated_at),
            ),
        )


class SQLiteCheckRunRepository(_SQLiteRepository):
    """SQLite implementation of CheckRunRepository."""

    def save(self, check_run: CheckRun) -> None:
        """Persist a CheckRun header without deciding business policy."""
        _ = self._connection.execute(
            """
            INSERT INTO check_runs (check_run_id, library_id, checked_at, total_count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(check_run_id) DO UPDATE SET
                library_id = excluded.library_id,
                checked_at = excluded.checked_at,
                total_count = excluded.total_count
            """,
            (
                str(check_run.check_run_id),
                str(check_run.library_id),
                _timestamp_to_text(check_run.checked_at),
                check_run.total_count,
            ),
        )

    def latest(self, library_id: LibraryId) -> CheckRun | None:
        """Return the latest CheckRun for one Library, if any."""
        row = _fetch_one(
            self._connection,
            CHECK_RUN_SELECT_FROM
            + """
            WHERE library_id = ?
            """,
            (str(library_id),),
        )
        return None if row is None else _check_run_from_row(row)

    def earliest_checked_at(self) -> datetime | None:
        """Return the minimum checked_at across every Library's latest check run, or None if none exist."""
        row = cast(
            "tuple[object, ...] | None", self._connection.execute("SELECT MIN(checked_at) FROM check_runs").fetchone()
        )
        if row is None or row[0] is None:
            return None
        value = row[0]
        if isinstance(value, str):
            return _timestamp_from_text(value)
        raise TypeError(INVALID_ROW_TEXT_MESSAGE)

    def delete_for_library(self, library_id: LibraryId) -> None:
        """Delete the CheckRun row for one Library, cascading its CheckIssues."""
        _ = self._connection.execute(
            "DELETE FROM check_runs WHERE library_id = ?",
            (str(library_id),),
        )


class SQLiteCheckIssueRepository(_SQLiteRepository):
    """SQLite implementation of CheckIssueRepository."""

    def save_many(self, check_run_id: CheckRunId, issues: Sequence[CheckIssue]) -> None:
        """Persist CheckIssues for one check run in insertion (issue_seq ASC) order."""
        _ = self._connection.executemany(
            """
            INSERT INTO check_issues (
                check_run_id,
                library_id,
                issue_type,
                path,
                track_id,
                plan_id,
                detail
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    str(check_run_id),
                    str(issue.library_id),
                    issue.issue_type.value,
                    issue.path,
                    None if issue.track_id is None else str(issue.track_id),
                    None if issue.plan_id is None else str(issue.plan_id),
                    issue.detail,
                )
                for issue in issues
            ],
        )

    def delete_for_library(self, library_id: LibraryId) -> None:
        """Delete every persisted CheckIssue for one Library."""
        _ = self._connection.execute(
            "DELETE FROM check_issues WHERE library_id = ?",
            (str(library_id),),
        )

    def query_page(  # noqa: PLR0913  # Check browse filters form the repository's stable read contract.
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
        if grouping is not None and group_key is not None:
            return self._group_member_page(library_id, search, issue_type, grouping, group_key, page)

        where_sql, where_params = _check_issue_filter_where(library_id, search, issue_type)
        # SQL-injection safety note: where_sql is built only from static clause templates bound with `?`; never raw input.
        count_sql = f"SELECT COUNT(*) FROM check_issues{where_sql}"  # noqa: S608
        total = _scalar_int(self._connection, count_sql, tuple(where_params))

        cursor_sql, cursor_params = _check_issue_cursor_clause(where_sql, page.cursor_key)
        rows = _fetch_all(
            self._connection,
            CHECK_ISSUE_SELECT_FROM
            + f"""
            {where_sql}{cursor_sql}
            ORDER BY issue_seq
            LIMIT ?
            """,
            (*where_params, *cursor_params, page.limit + 1),
        )

        issues = tuple(_check_issue_from_row(row) for row in rows)
        page_items = issues[: page.limit]
        has_more = len(issues) > page.limit
        next_cursor_key = (str(_row_int(rows[page.limit - 1], "issue_seq")),) if has_more else None
        return Page(items=page_items, next_cursor_key=next_cursor_key, total=total)

    def _group_member_page(  # noqa: PLR0913  # Delegates each Check browse filter to one group query.
        self,
        library_id: LibraryId | None,
        search: str | None,
        issue_type: CheckIssueType | None,
        grouping: CheckIssueGrouping,
        group_key: str,
        page: PageRequest,
    ) -> Page[CheckIssue]:
        """Return a keyset page of one server-derived CheckIssue group."""
        where_sql, where_params = _check_issue_group_filter_where(library_id, search, issue_type)
        source_sql = _check_issue_group_source_sql(grouping, where_sql)
        total = _scalar_int(
            self._connection,
            source_sql  # noqa: S608  # source SQL contains only static grouping expressions and bound filters
            + """
            SELECT COUNT(*)
            FROM source
            WHERE group_key = ?
            """,
            (*where_params, group_key),
        )

        cursor_sql, cursor_params = _check_issue_cursor_clause(" WHERE group_key = ?", page.cursor_key)
        rows = _fetch_all(
            self._connection,
            source_sql  # noqa: S608  # source SQL contains only static grouping expressions and bound filters
            + f"""
            SELECT issue_seq, check_run_id, library_id, issue_type, path, track_id, plan_id, detail
            FROM source
            WHERE group_key = ?{cursor_sql}
            ORDER BY issue_seq
            LIMIT ?
            """,  # noqa: S608  # cursor SQL is built from a static keyset clause with bound values
            (*where_params, group_key, *cursor_params, page.limit + 1),
        )
        issues = tuple(_check_issue_from_row(row) for row in rows)
        page_items = issues[: page.limit]
        has_more = len(issues) > page.limit
        next_cursor_key = (str(_row_int(rows[page.limit - 1], "issue_seq")),) if has_more else None
        return Page(items=page_items, next_cursor_key=next_cursor_key, total=total)

    def issue_type_facets(self, library_id: LibraryId | None, *, search: str | None = None) -> tuple[FacetValue, ...]:
        """Return CheckIssue issue_type facets, ordered count DESC then value ASC."""
        where_sql, where_params = _check_issue_filter_where(library_id, search, None)
        rows = _fetch_all(
            self._connection,
            # SQL-injection safety note: where_sql is a static clause template bound with `?`; never raw input.
            f"""
            SELECT issue_type, COUNT(*) AS count
            FROM check_issues
            {where_sql}
            GROUP BY issue_type
            ORDER BY count DESC, issue_type ASC
            """,  # noqa: S608
            tuple(where_params),
        )
        return tuple(FacetValue(value=_row_text(row, "issue_type"), count=_row_int(row, "count")) for row in rows)

    def group_page(
        self,
        library_id: LibraryId | None,
        grouping: CheckIssueGrouping,
        page: PageRequest,
        *,
        search: str | None = None,
        issue_type: CheckIssueType | None = None,
    ) -> Page[CheckIssueGroup]:
        """Return one keyset page of CheckIssue groups with their common path roots."""
        where_sql, where_params = _check_issue_group_filter_where(library_id, search, issue_type)
        source_sql = _check_issue_group_source_sql(grouping, where_sql)

        # SQL-injection safety note: source_sql is assembled solely from static SQL templates and bound filters.
        total = _scalar_int(
            self._connection,
            source_sql  # noqa: S608  # source SQL contains only static grouping expressions and bound filters
            + """
            SELECT COUNT(*) FROM (
                SELECT 1
                FROM source
                GROUP BY group_key
            )
            """,
            tuple(where_params),
        )

        cursor_sql, cursor_params = _track_group_cursor_clause(page.cursor_key)
        # SQL-injection safety note: source_sql and cursor_sql use only static templates and bound values.
        rows = _fetch_all(
            self._connection,
            source_sql  # noqa: S608  # source SQL contains only static grouping expressions and bound filters
            + f"""
            , group_counts AS (
                SELECT group_key AS key, MIN(group_label) AS label, COUNT(*) AS count
                FROM source
                GROUP BY group_key
            ), root_counts AS (
                SELECT group_key, path_root, COUNT(*) AS root_count
                FROM source
                WHERE path_root IS NOT NULL
                GROUP BY group_key, path_root
            )
            SELECT key, label, count, common_path_root
            FROM (
                SELECT
                    group_counts.key,
                    group_counts.label,
                    group_counts.count,
                    (
                        SELECT root_counts.path_root
                        FROM root_counts
                        WHERE root_counts.group_key = group_counts.key
                        ORDER BY root_counts.root_count DESC, root_counts.path_root ASC
                        LIMIT 1
                    ) AS common_path_root
                FROM group_counts
            )
            {cursor_sql}
            ORDER BY count DESC, key ASC
            LIMIT ?
            """,  # noqa: S608
            (*where_params, *cursor_params, page.limit + 1),
        )

        groups = tuple(
            CheckIssueGroup(
                key=_row_text(row, "key"),
                label=_row_text(row, "label"),
                count=_row_int(row, "count"),
                common_path_root=_row_optional_text(row, "common_path_root"),
            )
            for row in rows
        )
        page_items = groups[: page.limit]
        has_more = len(groups) > page.limit
        next_cursor_key = (str(page_items[-1].count), page_items[-1].key) if has_more else None
        return Page(items=page_items, next_cursor_key=next_cursor_key, total=total)


class SQLiteTrackRepository(_SQLiteRepository):
    """SQLite implementation of TrackRepository."""

    def get(self, track_id: TrackId) -> Track | None:
        """Return one Track by stable ID."""
        row = _fetch_one(
            self._connection,
            TRACK_SELECT_FROM
            + """
            WHERE track_id = ?
            """,
            (str(track_id),),
        )
        return None if row is None else _track_from_row(row)

    def list_by_library(self, library_id: LibraryId) -> tuple[Track, ...]:
        """Return Tracks owned by one Library."""
        rows = _fetch_all(
            self._connection,
            TRACK_SELECT_FROM
            + """
            WHERE library_id = ?
            ORDER BY current_path, track_id
            """,
            (str(library_id),),
        )
        return tuple(_track_from_row(row) for row in rows)

    def save(self, track: Track) -> None:
        """Persist a Track without recalculating identity or paths."""
        _ = self._connection.execute(
            """
            INSERT INTO tracks (
                track_id,
                library_id,
                current_path,
                canonical_path,
                content_hash,
                metadata_hash,
                size,
                mtime,
                metadata_json,
                status,
                first_seen_at,
                last_seen_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(track_id) DO UPDATE SET
                library_id = excluded.library_id,
                current_path = excluded.current_path,
                canonical_path = excluded.canonical_path,
                content_hash = excluded.content_hash,
                metadata_hash = excluded.metadata_hash,
                size = excluded.size,
                mtime = excluded.mtime,
                metadata_json = excluded.metadata_json,
                status = excluded.status,
                first_seen_at = excluded.first_seen_at,
                last_seen_at = excluded.last_seen_at,
                updated_at = excluded.updated_at
            """,
            (
                str(track.track_id),
                str(track.library_id),
                track.current_path,
                track.canonical_path,
                track.content_hash,
                track.metadata_hash,
                track.size,
                _optional_timestamp_to_text(track.mtime),
                _metadata_to_json(track.metadata),
                track.status.value,
                _timestamp_to_text(track.first_seen_at),
                _timestamp_to_text(track.last_seen_at),
                _timestamp_to_text(track.updated_at),
            ),
        )

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
        """Return one keyset page of Tracks ordered (current_path, track_id)."""
        if (grouping is None) != (group_key is None):
            raise ValueError(TRACK_GROUP_FILTER_PAIRING_MESSAGE)
        if grouping is not None and group_key is not None:
            return self._group_member_page(
                library_id,
                track_id=track_id,
                search=search,
                status=status,
                grouping=grouping,
                group_key=group_key,
                page=page,
            )

        where_sql, where_params = _track_filter_where(library_id, track_id, status, search)
        # SQL-injection safety note: where_sql is built only from static clause templates bound with `?`; never raw input.
        count_sql = f"SELECT COUNT(*) FROM tracks{where_sql}"  # noqa: S608
        total = _scalar_int(self._connection, count_sql, tuple(where_params))

        cursor_sql, cursor_params = _track_cursor_clause(where_sql, page.cursor_key)
        rows = _fetch_all(
            self._connection,
            TRACK_SELECT_FROM
            + f"""
            {where_sql}{cursor_sql}
            ORDER BY current_path, track_id
            LIMIT ?
            """,
            (*where_params, *cursor_params, page.limit + 1),
        )

        tracks = tuple(_track_from_row(row) for row in rows)
        page_items = tracks[: page.limit]
        has_more = len(tracks) > page.limit
        next_cursor_key = (page_items[-1].current_path, str(page_items[-1].track_id)) if has_more else None
        return Page(items=page_items, next_cursor_key=next_cursor_key, total=total)

    def _group_member_page(  # noqa: PLR0913  # Delegates every Track browse filter to one exact group query.
        self,
        library_id: LibraryId | None,
        *,
        track_id: TrackId | None,
        search: str | None,
        status: TrackStatus | None,
        grouping: TrackGrouping,
        group_key: str,
        page: PageRequest,
    ) -> Page[Track]:
        """Return one exact metadata group in deterministic music-friendly order."""
        where_sql, where_params = _track_filter_where(library_id, track_id, status, search)
        source_sql, source_params = _track_group_member_source_sql(grouping, where_sql, where_params)
        total = _scalar_int(
            self._connection,
            source_sql  # noqa: S608  # source SQL uses static grouping expressions and bound filters only
            + """
            SELECT COUNT(*)
            FROM source
            WHERE group_key = ?
            """,
            (*source_params, group_key),
        )

        cursor_sql, cursor_params = _track_group_member_cursor_clause(page.cursor_key)
        rows = _fetch_all(
            self._connection,
            source_sql  # noqa: S608  # source SQL uses static grouping expressions and bound filters only
            + f"""
            SELECT *
            FROM source
            WHERE group_key = ?{cursor_sql}
            ORDER BY track_number_rank, track_number_value, track_title, track_id
            LIMIT ?
            """,  # noqa: S608  # cursor SQL is a static keyset clause with bound values
            (*source_params, group_key, *cursor_params, page.limit + 1),
        )

        tracks = tuple(_track_from_row(row) for row in rows)
        page_items = tracks[: page.limit]
        has_more = len(tracks) > page.limit
        next_cursor_key = _track_group_member_cursor_key(page_items[-1]) if has_more else None
        return Page(items=page_items, next_cursor_key=next_cursor_key, total=total)

    def status_facets(self, library_id: LibraryId | None, *, search: str | None = None) -> tuple[FacetValue, ...]:
        """Return Track status facet counts, ordered count DESC then value ASC."""
        where_sql, where_params = _track_filter_where(library_id, None, None, search)
        rows = _fetch_all(
            self._connection,
            # SQL-injection safety note: where_sql is a static clause template bound with `?`; never raw input.
            f"""
            SELECT status, COUNT(*) AS count
            FROM tracks
            {where_sql}
            GROUP BY status
            ORDER BY count DESC, status ASC
            """,  # noqa: S608
            tuple(where_params),
        )
        return tuple(FacetValue(value=_row_text(row, "status"), count=_row_int(row, "count")) for row in rows)

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
        """Return one keyset page of Track groups ordered count DESC then key ASC."""
        if grouping is TrackGrouping.ARTIST_ALBUM:
            return self._legacy_artist_album_group_page(library_id, search, status, page)
        return self._hierarchy_group_page(library_id, grouping, parent_key, search, status, page)

    def _legacy_artist_album_group_page(
        self,
        library_id: LibraryId | None,
        search: str | None,
        status: TrackStatus | None,
        page: PageRequest,
    ) -> Page[GroupCount]:
        """Return the existing artist/album grouping without changing its key contract."""
        where_sql, where_params = _track_filter_where(library_id, None, status, search)
        source_params = [TRACK_GROUP_UNKNOWN_KEY, TRACK_GROUP_UNKNOWN_KEY, *where_params]

        # SQL-injection safety note: TRACK_GROUP_SOURCE_SELECT and where_sql are static templates bound with `?`.
        total = _scalar_int(
            self._connection,
            f"""
            SELECT COUNT(*) FROM (
                SELECT 1
                FROM (
                    {TRACK_GROUP_SOURCE_SELECT}
                    {where_sql}
                )
                GROUP BY group_artist, group_album
            )
            """,  # noqa: S608
            tuple(source_params),
        )

        cursor_sql, cursor_params = _track_group_cursor_clause(page.cursor_key)
        # SQL-injection safety note: TRACK_GROUP_SOURCE_SELECT, where_sql, and cursor_sql are static templates
        # bound with `?`; never raw input.
        rows = _fetch_all(
            self._connection,
            f"""
            SELECT key, label, count
            FROM (
                SELECT
                    group_artist || char(31) || group_album AS key,
                    group_artist || ? || group_album AS label,
                    COUNT(*) AS count
                FROM (
                    {TRACK_GROUP_SOURCE_SELECT}
                    {where_sql}
                )
                GROUP BY group_artist, group_album
            )
            {cursor_sql}
            ORDER BY count DESC, key ASC
            LIMIT ?
            """,  # noqa: S608
            (
                TRACK_GROUP_LABEL_SEPARATOR,
                TRACK_GROUP_UNKNOWN_KEY,
                TRACK_GROUP_UNKNOWN_KEY,
                *where_params,
                *cursor_params,
                page.limit + 1,
            ),
        )

        groups = tuple(
            GroupCount(key=_row_text(row, "key"), label=_row_text(row, "label"), count=_row_int(row, "count"))
            for row in rows
        )
        page_items = groups[: page.limit]
        has_more = len(groups) > page.limit
        next_cursor_key = (str(page_items[-1].count), page_items[-1].key) if has_more else None
        return Page(items=page_items, next_cursor_key=next_cursor_key, total=total)

    def _hierarchy_group_page(  # noqa: PLR0913  # Keeps hierarchy filtering aligned with Track lists.
        self,
        library_id: LibraryId | None,
        grouping: TrackGrouping,
        parent_key: str | None,
        search: str | None,
        status: TrackStatus | None,
        page: PageRequest,
    ) -> Page[GroupCount]:
        """Return artist, album, or disc hierarchy groups from stored metadata."""
        where_sql, where_params = _track_filter_where(library_id, None, status, search)
        source_sql, source_params = _track_hierarchy_source_sql(
            grouping,
            where_sql,
            where_params,
            parent_key=parent_key,
            apply_parent_scope=True,
        )
        total = _scalar_int(
            self._connection,
            source_sql  # noqa: S608  # source SQL uses static grouping expressions and bound filters only
            + """
            SELECT COUNT(*) FROM (
                SELECT 1
                FROM source
                GROUP BY group_key
            )
            """,
            tuple(source_params),
        )

        cursor_sql, cursor_params = _track_group_cursor_clause(page.cursor_key)
        rows = _fetch_all(
            self._connection,
            source_sql  # noqa: S608  # source SQL uses static grouping expressions and bound filters only
            + f"""
            SELECT key, label, count
            FROM (
                SELECT group_key AS key, MIN(group_label) AS label, COUNT(*) AS count
                FROM source
                GROUP BY group_key
            )
            {cursor_sql}
            ORDER BY count DESC, key ASC
            LIMIT ?
            """,  # noqa: S608  # cursor SQL is a static keyset clause with bound values
            (*source_params, *cursor_params, page.limit + 1),
        )

        groups = tuple(
            GroupCount(key=_row_text(row, "key"), label=_row_text(row, "label"), count=_row_int(row, "count"))
            for row in rows
        )
        page_items = groups[: page.limit]
        has_more = len(groups) > page.limit
        next_cursor_key = (str(page_items[-1].count), page_items[-1].key) if has_more else None
        return Page(items=page_items, next_cursor_key=next_cursor_key, total=total)


class SQLitePlanRepository(_SQLiteRepository):
    """SQLite implementation of PlanRepository."""

    def get(self, plan_id: PlanId) -> Plan | None:
        """Return one Plan by ID."""
        row = _fetch_one(
            self._connection,
            PLAN_SELECT_FROM
            + """
            WHERE plan_id = ?
            """,
            (str(plan_id),),
        )
        return None if row is None else _plan_from_row(row)

    def list_by_library(self, library_id: LibraryId) -> tuple[Plan, ...]:
        """Return Plans owned by one Library."""
        rows = _fetch_all(
            self._connection,
            PLAN_SELECT_FROM
            + """
            WHERE library_id = ?
            ORDER BY created_at, plan_id
            """,
            (str(library_id),),
        )
        return tuple(_plan_from_row(row) for row in rows)

    def list_by_source_run(self, source_run_id: RunId) -> tuple[Plan, ...]:
        """Return Undo Plans that record one source Run, in creation order."""
        rows = _fetch_all(
            self._connection,
            PLAN_SELECT_FROM
            + """
            WHERE source_run_id = ? AND plan_type = 'undo'
            ORDER BY created_at, plan_id
            """,
            (str(source_run_id),),
        )
        return tuple(_plan_from_row(row) for row in rows)

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
        where_sql, where_params = _plan_filter_where(
            library_id,
            search,
            status,
            plan_type,
            blocked_only=blocked_only,
        )
        # SQL-injection safety note: where_sql is built only from static clause templates bound with `?`; never raw input.
        count_sql = f"SELECT COUNT(*) FROM plans{where_sql}"  # noqa: S608
        total = _scalar_int(self._connection, count_sql, tuple(where_params))

        cursor_sql, cursor_params = _plan_cursor_clause(where_sql, page.cursor_key)
        rows = _fetch_all(
            self._connection,
            PLAN_SELECT_FROM
            + f"""
            {where_sql}{cursor_sql}
            ORDER BY created_at DESC, plan_id DESC
            LIMIT ?
            """,
            (*where_params, *cursor_params, page.limit + 1),
        )

        plans = tuple(_plan_from_row(row) for row in rows)
        page_items = plans[: page.limit]
        has_more = len(plans) > page.limit
        next_cursor_key = (
            (_row_text(rows[page.limit - 1], "created_at"), str(page_items[-1].plan_id)) if has_more else None
        )
        return Page(items=page_items, next_cursor_key=next_cursor_key, total=total)

    def save(self, plan: Plan) -> None:
        """Persist a Plan header and summary."""
        _ = self._connection.execute(
            """
            INSERT INTO plans (
                plan_id,
                library_id,
                source_run_id,
                plan_type,
                status,
                created_at,
                config_hash,
                library_root_at_plan,
                summary_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(plan_id) DO UPDATE SET
                library_id = excluded.library_id,
                source_run_id = excluded.source_run_id,
                plan_type = excluded.plan_type,
                status = excluded.status,
                created_at = excluded.created_at,
                config_hash = excluded.config_hash,
                library_root_at_plan = excluded.library_root_at_plan,
                summary_json = excluded.summary_json
            """,
            (
                str(plan.plan_id),
                str(plan.library_id),
                None if plan.source_run_id is None else str(plan.source_run_id),
                plan.plan_type.value,
                plan.status.value,
                _timestamp_to_text(plan.created_at),
                plan.config_hash,
                plan.library_root_at_plan,
                _summary_to_json(plan.summary),
            ),
        )

    def compare_and_set_status(
        self,
        plan_id: PlanId,
        expected_status: PlanStatus,
        replacement_status: PlanStatus,
    ) -> bool:
        """Replace one Plan status only when the persisted state still matches."""
        cursor = self._connection.execute(
            """
            UPDATE plans
            SET status = ?
            WHERE plan_id = ? AND status = ?
            """,
            (replacement_status.value, str(plan_id), expected_status.value),
        )
        return cursor.rowcount == 1


class SQLitePlanActionRepository(_SQLiteRepository):
    """SQLite implementation of PlanActionRepository."""

    def get(self, action_id: ActionId) -> PlanAction | None:
        """Return one PlanAction by ID."""
        row = _fetch_one(
            self._connection,
            PLAN_ACTION_SELECT_FROM
            + """
            WHERE action_id = ?
            """,
            (str(action_id),),
        )
        return None if row is None else _plan_action_from_row(row)

    def list_by_plan(self, plan_id: PlanId) -> tuple[PlanAction, ...]:
        """Return the actions recorded for a Plan in apply order."""
        rows = _fetch_all(
            self._connection,
            PLAN_ACTION_SELECT_FROM
            + """
            WHERE plan_id = ?
            ORDER BY sort_order, action_id
            """,
            (str(plan_id),),
        )
        return tuple(_plan_action_from_row(row) for row in rows)

    def query_page(  # noqa: PLR0913  # PlanAction browse filters form one stable read contract.
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
        where_sql, where_params = _plan_action_filter_where(plan_id, search, status, action_type, reason)
        # SQL-injection safety note: where_sql is built only from static clause templates bound with `?`; never raw input.
        count_sql = f"SELECT COUNT(*) FROM plan_actions{where_sql}"  # noqa: S608
        total = _scalar_int(self._connection, count_sql, tuple(where_params))

        cursor_sql, cursor_params = _plan_action_cursor_clause(where_sql, page.cursor_key)
        rows = _fetch_all(
            self._connection,
            PLAN_ACTION_SELECT_FROM
            + f"""
            {where_sql}{cursor_sql}
            ORDER BY sort_order, action_id
            LIMIT ?
            """,
            (*where_params, *cursor_params, page.limit + 1),
        )

        actions = tuple(_plan_action_from_row(row) for row in rows)
        page_items = actions[: page.limit]
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
        where_sql, where_params = _plan_action_filter_where(plan_id, search, None, action_type, reason)
        rows = _fetch_all(
            self._connection,
            f"""
            SELECT status, COUNT(*) AS count
            FROM plan_actions
            {where_sql}
            GROUP BY status
            ORDER BY count DESC, status ASC
            """,  # noqa: S608  # filter SQL uses static clauses and bound values
            tuple(where_params),
        )
        return tuple(FacetValue(value=_row_text(row, "status"), count=_row_int(row, "count")) for row in rows)

    def action_type_facets(
        self,
        plan_id: PlanId,
        *,
        search: str | None = None,
        status: ActionStatus | None = None,
        reason: PlanActionReason | None = None,
    ) -> tuple[FacetValue, ...]:
        """Return PlanAction type facets for one Plan, ordered count DESC then value ASC."""
        where_sql, where_params = _plan_action_filter_where(plan_id, search, status, None, reason)
        rows = _fetch_all(
            self._connection,
            f"""
            SELECT action_type, COUNT(*) AS count
            FROM plan_actions
            {where_sql}
            GROUP BY action_type
            ORDER BY count DESC, action_type ASC
            """,  # noqa: S608  # filter SQL uses static clauses and bound values
            tuple(where_params),
        )
        return tuple(FacetValue(value=_row_text(row, "action_type"), count=_row_int(row, "count")) for row in rows)

    def reason_facets(
        self,
        plan_id: PlanId,
        *,
        search: str | None = None,
        status: ActionStatus | None = None,
        action_type: ActionType | None = None,
    ) -> tuple[FacetValue, ...]:
        """Return non-null PlanAction reason facets for one Plan, ordered count DESC then value ASC."""
        where_sql, where_params = _plan_action_filter_where(plan_id, search, status, action_type, None)
        reason_sql = f"{where_sql} AND reason IS NOT NULL"
        rows = _fetch_all(
            self._connection,
            f"""
            SELECT reason, COUNT(*) AS count
            FROM plan_actions
            {reason_sql}
            GROUP BY reason
            ORDER BY count DESC, reason ASC
            """,  # noqa: S608  # filter SQL uses static clauses and bound values
            tuple(where_params),
        )
        return tuple(FacetValue(value=_row_text(row, "reason"), count=_row_int(row, "count")) for row in rows)

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
        where_sql, where_params = _plan_action_filter_where(plan_id, search, status, action_type, reason)
        return _scalar_int(
            self._connection,
            f"SELECT COUNT(*) FROM plan_actions{where_sql}",  # noqa: S608
            tuple(where_params),
        )

    def count_target_collisions(self, plan_id: PlanId) -> int:
        """Return how many distinct non-null target_path values are recorded by 2+ of the Plan's actions."""
        return _scalar_int(
            self._connection,
            """
            SELECT COUNT(*)
            FROM (
                SELECT 1
                FROM plan_actions
                WHERE plan_id = ? AND target_path IS NOT NULL
                GROUP BY target_path
                HAVING COUNT(*) > 1
            )
            """,
            (str(plan_id),),
        )

    def action_counts_by_plan(
        self,
        plan_ids: Sequence[PlanId],
    ) -> dict[PlanId, dict[tuple[ActionStatus, ActionType], int]]:
        """Return current status/action-type counts for a bounded Plan page in one query."""
        counts_by_plan: dict[PlanId, dict[tuple[ActionStatus, ActionType], int]] = {plan_id: {} for plan_id in plan_ids}
        if not counts_by_plan:
            return {}
        placeholders = ", ".join("?" for _ in counts_by_plan)
        rows = _fetch_all(
            self._connection,
            f"""
            SELECT plan_id, status, action_type, COUNT(*) AS count
            FROM plan_actions
            WHERE plan_id IN ({placeholders})
            GROUP BY plan_id, status, action_type
            """,  # noqa: S608  # Placeholder text is generated solely from bound IDs.
            tuple(str(plan_id) for plan_id in counts_by_plan),
        )
        for row in rows:
            plan_id = PlanId(parse_uuid(_row_text(row, "plan_id")))
            counts = counts_by_plan[plan_id]
            key = (ActionStatus(_row_text(row, "status")), ActionType(_row_text(row, "action_type")))
            counts[key] = _row_int(row, "count")
        return counts_by_plan

    def list_by_ids(self, action_ids: Sequence[ActionId]) -> tuple[PlanAction, ...]:
        """Return the PlanActions with the given IDs, ordered (sort_order, action_id)."""
        if not action_ids:
            return ()
        placeholders = ", ".join("?" for _ in action_ids)
        # SQL-injection safety note: placeholders is only comma-joined `?` markers; values bind with `?`.
        rows = _fetch_all(
            self._connection,
            PLAN_ACTION_SELECT_FROM
            + f"""
            WHERE action_id IN ({placeholders})
            ORDER BY sort_order, action_id
            """,
            tuple(str(action_id) for action_id in action_ids),
        )
        return tuple(_plan_action_from_row(row) for row in rows)

    def list_group_rows(self, plan_id: PlanId) -> tuple[PlanActionGroupRow, ...]:
        """Return per-action group projections for one Plan, ordered (sort_order, action_id)."""
        rows = _fetch_all(
            self._connection,
            """
            SELECT action_id, track_id, sort_order, status, reason, action_type, source_path, target_path,
                   content_hash_at_plan, metadata_hash_at_plan
            FROM plan_actions
            WHERE plan_id = ?
            ORDER BY sort_order, action_id
            """,
            (str(plan_id),),
        )
        return tuple(_plan_action_group_row_from_row(row) for row in rows)

    def save(self, action: PlanAction) -> None:
        """Persist a PlanAction without recalculating target paths."""
        _ = self._connection.execute(
            """
            INSERT INTO plan_actions (
                action_id,
                plan_id,
                library_id,
                track_id,
                action_type,
                source_path,
                target_path,
                reverses_event_id,
                content_hash_at_plan,
                metadata_hash_at_plan,
                status,
                reason,
                sort_order
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(action_id) DO UPDATE SET
                plan_id = excluded.plan_id,
                library_id = excluded.library_id,
                track_id = excluded.track_id,
                action_type = excluded.action_type,
                source_path = excluded.source_path,
                target_path = excluded.target_path,
                reverses_event_id = excluded.reverses_event_id,
                content_hash_at_plan = excluded.content_hash_at_plan,
                metadata_hash_at_plan = excluded.metadata_hash_at_plan,
                status = excluded.status,
                reason = excluded.reason,
                sort_order = excluded.sort_order
            """,
            (
                str(action.action_id),
                str(action.plan_id),
                str(action.library_id),
                None if action.track_id is None else str(action.track_id),
                action.action_type.value,
                action.source_path,
                action.target_path,
                None if action.reverses_event_id is None else str(action.reverses_event_id),
                action.content_hash_at_plan,
                action.metadata_hash_at_plan,
                action.status.value,
                None if action.reason is None else action.reason.value,
                action.sort_order,
            ),
        )


class SQLiteOperationRepository(_SQLiteRepository):
    """SQLite implementation of OperationRepository."""

    def lookup(self, operation_id: OperationId) -> OperationLookup | None:
        """Return a full Operation or retained tombstone by stable ID."""
        row = _fetch_one(
            self._connection,
            OPERATION_SELECT_FROM
            + """
            WHERE operation_id = ?
            """,
            (str(operation_id),),
        )
        return None if row is None else _operation_lookup_from_row(row)

    def find_by_idempotency_key(self, idempotency_key: UUID) -> OperationLookup | None:
        """Return retained request identity for idempotent replay classification."""
        row = _fetch_one(
            self._connection,
            OPERATION_SELECT_FROM
            + """
            WHERE idempotency_key = ?
            """,
            (str(idempotency_key),),
        )
        return None if row is None else _operation_lookup_from_row(row)

    def list_reconciliation_candidates(self) -> tuple[Operation, ...]:
        """Return unfinished Operations in deterministic request order."""
        rows = _fetch_all(
            self._connection,
            OPERATION_SELECT_FROM  # noqa: S608  # Concatenates only static repository SQL fragments.
            + """
            WHERE operations.status IN ('queued', 'running')
               OR (
                    operations.status = 'interrupted'
                    AND operations.kind = 'apply_plan'
                    AND (
                        EXISTS (
                            SELECT 1
                            FROM plans
                            WHERE plans.plan_id = operations.plan_id
                              AND plans.status = 'applying'
                        )
                        OR EXISTS (
                            SELECT 1
                            FROM runs
                            WHERE runs.run_id = operations.run_id
                              AND runs.status = 'running'
                        )
                    )
               )
            ORDER BY operations.requested_at, operations.operation_id
            """,
        )
        return tuple(_operation_from_row(row) for row in rows)

    def find_active(self) -> Operation | None:
        """Return the single queued or running Operation, if one exists."""
        row = _fetch_one(
            self._connection,
            OPERATION_SELECT_FROM
            + """
            WHERE status IN ('queued', 'running')
            ORDER BY requested_at, operation_id
            LIMIT 1
            """,
        )
        return None if row is None else _operation_from_row(row)

    def save(self, operation: Operation) -> None:
        """Persist one full Operation without deciding lifecycle policy."""
        result_kind = None if operation.result is None else operation.result.kind.value
        result_json = None if operation.result is None else _operation_result_to_json(operation.result)
        error_code = None if operation.error is None else operation.error.code.value
        error_json = None if operation.error is None else _operation_error_to_json(operation.error)
        _ = self._connection.execute(
            """
            INSERT INTO operations (
                operation_id,
                library_id,
                plan_id,
                run_id,
                kind,
                status,
                idempotency_key,
                request_fingerprint,
                stage_code,
                completed_units,
                total_units,
                progress_message,
                result_kind,
                result_json,
                error_code,
                error_json,
                requested_at,
                started_at,
                updated_at,
                completed_at,
                result_expires_at,
                tombstone_expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(operation_id) DO UPDATE SET
                library_id = excluded.library_id,
                plan_id = excluded.plan_id,
                run_id = excluded.run_id,
                kind = excluded.kind,
                status = excluded.status,
                idempotency_key = excluded.idempotency_key,
                request_fingerprint = excluded.request_fingerprint,
                stage_code = excluded.stage_code,
                completed_units = excluded.completed_units,
                total_units = excluded.total_units,
                progress_message = excluded.progress_message,
                result_kind = excluded.result_kind,
                result_json = excluded.result_json,
                error_code = excluded.error_code,
                error_json = excluded.error_json,
                requested_at = excluded.requested_at,
                started_at = excluded.started_at,
                updated_at = excluded.updated_at,
                completed_at = excluded.completed_at,
                result_expires_at = excluded.result_expires_at,
                tombstone_expires_at = excluded.tombstone_expires_at
            """,
            (
                str(operation.operation_id),
                None if operation.library_id is None else str(operation.library_id),
                None if operation.plan_id is None else str(operation.plan_id),
                None if operation.run_id is None else str(operation.run_id),
                operation.kind.value,
                operation.status.value,
                str(operation.idempotency_key),
                operation.request_fingerprint,
                operation.progress.stage_code,
                operation.progress.completed_units,
                operation.progress.total_units,
                operation.progress.message,
                result_kind,
                result_json,
                error_code,
                error_json,
                _timestamp_to_text(operation.requested_at),
                _optional_timestamp_to_text(operation.started_at),
                _timestamp_to_text(operation.updated_at),
                _optional_timestamp_to_text(operation.completed_at),
                _optional_timestamp_to_text(operation.result_expires_at),
                _optional_timestamp_to_text(operation.tombstone_expires_at),
            ),
        )

    def expire_terminal_payloads(self, now: datetime) -> int:
        """Clear expired result/error payloads and return the affected row count."""
        cursor = self._connection.execute(
            """
            UPDATE operations
            SET result_kind = NULL, result_json = NULL, error_code = NULL, error_json = NULL
            WHERE status IN ('succeeded', 'failed', 'interrupted')
              AND result_expires_at <= ?
              AND (result_json IS NOT NULL OR error_json IS NOT NULL)
            """,
            (_timestamp_to_text(now),),
        )
        return cursor.rowcount

    def purge_expired_tombstones(self, now: datetime) -> int:
        """Delete expired terminal tombstones and return the affected row count."""
        cursor = self._connection.execute(
            """
            DELETE FROM operations
            WHERE status IN ('succeeded', 'failed', 'interrupted')
              AND tombstone_expires_at <= ?
            """,
            (_timestamp_to_text(now),),
        )
        return cursor.rowcount


class SQLiteRunRepository(_SQLiteRepository):
    """SQLite implementation of RunRepository."""

    def get(self, run_id: RunId) -> Run | None:
        """Return one Run by ID."""
        row = _fetch_one(
            self._connection,
            RUN_SELECT_FROM
            + """
            WHERE run_id = ?
            """,
            (str(run_id),),
        )
        return None if row is None else _run_from_row(row)

    def list_by_library(self, library_id: LibraryId) -> tuple[Run, ...]:
        """Return Runs owned by one Library."""
        rows = _fetch_all(
            self._connection,
            RUN_SELECT_FROM
            + """
            WHERE library_id = ?
            ORDER BY started_at, run_id
            """,
            (str(library_id),),
        )
        return tuple(_run_from_row(row) for row in rows)

    def list_by_plan(self, plan_id: PlanId) -> tuple[Run, ...]:
        """Return Runs created for one Plan."""
        rows = _fetch_all(
            self._connection,
            RUN_SELECT_FROM
            + """
            WHERE plan_id = ?
            ORDER BY started_at, run_id
            """,
            (str(plan_id),),
        )
        return tuple(_run_from_row(row) for row in rows)

    def save(self, run: Run) -> None:
        """Persist Run state transitions."""
        _ = self._connection.execute(
            """
            INSERT INTO runs (
                run_id,
                plan_id,
                library_id,
                status,
                started_at,
                completed_at,
                error_summary
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                plan_id = excluded.plan_id,
                library_id = excluded.library_id,
                status = excluded.status,
                started_at = excluded.started_at,
                completed_at = excluded.completed_at,
                error_summary = excluded.error_summary
            """,
            (
                str(run.run_id),
                str(run.plan_id),
                str(run.library_id),
                run.status.value,
                _timestamp_to_text(run.started_at),
                _optional_timestamp_to_text(run.completed_at),
                run.error_summary,
            ),
        )

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
        where_sql, where_params = _run_filter_where(library_id, search, plan_id, status)
        # SQL-injection safety note: where_sql is built only from static clause templates bound with `?`; never raw input.
        count_sql = f"SELECT COUNT(*) FROM runs{where_sql}"  # noqa: S608
        total = _scalar_int(self._connection, count_sql, tuple(where_params))

        cursor_sql, cursor_params = _run_cursor_clause(where_sql, page.cursor_key)
        rows = _fetch_all(
            self._connection,
            RUN_SELECT_FROM
            + f"""
            {where_sql}{cursor_sql}
            ORDER BY started_at DESC, run_id DESC
            LIMIT ?
            """,
            (*where_params, *cursor_params, page.limit + 1),
        )

        runs = tuple(_run_from_row(row) for row in rows)
        page_items = runs[: page.limit]
        has_more = len(runs) > page.limit
        next_cursor_key = (
            (_row_text(rows[page.limit - 1], "started_at"), str(page_items[-1].run_id)) if has_more else None
        )
        return Page(items=page_items, next_cursor_key=next_cursor_key, total=total)

    def status_facets(self, library_id: LibraryId | None) -> tuple[FacetValue, ...]:
        """Return Run status facet counts, ordered count DESC then value ASC."""
        where_sql, where_params = _optional_library_clause(library_id)
        rows = _fetch_all(
            self._connection,
            # SQL-injection safety note: where_sql is a static clause template bound with `?`; never raw input.
            f"""
            SELECT status, COUNT(*) AS count
            FROM runs
            {where_sql}
            GROUP BY status
            ORDER BY count DESC, status ASC
            """,  # noqa: S608
            tuple(where_params),
        )
        return tuple(FacetValue(value=_row_text(row, "status"), count=_row_int(row, "count")) for row in rows)


class SQLiteFileEventRepository(_SQLiteRepository):
    """SQLite implementation of FileEventRepository."""

    def get(self, event_id: EventId) -> FileEvent | None:
        """Return one FileEvent by ID."""
        row = _fetch_one(
            self._connection,
            FILE_EVENT_SELECT_FROM
            + """
            WHERE event_id = ?
            """,
            (str(event_id),),
        )
        return None if row is None else _file_event_from_row(row)

    def list_by_run(self, run_id: RunId) -> tuple[FileEvent, ...]:
        """Return FileEvents recorded for one Run in sequence order."""
        rows = _fetch_all(
            self._connection,
            FILE_EVENT_SELECT_FROM
            + """
            WHERE run_id = ?
            ORDER BY sequence_no, event_id
            """,
            (str(run_id),),
        )
        return tuple(_file_event_from_row(row) for row in rows)

    def list_by_library(self, library_id: LibraryId) -> tuple[FileEvent, ...]:
        """Return FileEvents recorded for one Library in durable order."""
        rows = _fetch_all(
            self._connection,
            FILE_EVENT_SELECT_FROM
            + """
            WHERE library_id = ?
            ORDER BY started_at, sequence_no, event_id
            """,
            (str(library_id),),
        )
        return tuple(_file_event_from_row(row) for row in rows)

    def list_pending_by_library(self, library_id: LibraryId) -> tuple[FileEvent, ...]:
        """Return PENDING FileEvents for one Library in sequence order."""
        rows = _fetch_all(
            self._connection,
            FILE_EVENT_SELECT_FROM
            + """
            WHERE library_id = ? AND status = ?
            ORDER BY sequence_no, event_id
            """,
            (str(library_id), FileEventStatus.PENDING.value),
        )
        return tuple(_file_event_from_row(row) for row in rows)

    def query_page(
        self,
        run_id: RunId,
        *,
        status: FileEventStatus | None,
        page: PageRequest,
    ) -> Page[FileEvent]:
        """Return one keyset page of a Run's FileEvents ordered (sequence_no, event_id)."""
        where_sql, where_params = _file_event_filter_where(run_id, status)
        # SQL-injection safety note: where_sql is built only from static clause templates bound with `?`; never raw input.
        count_sql = f"SELECT COUNT(*) FROM file_events{where_sql}"  # noqa: S608
        total = _scalar_int(self._connection, count_sql, tuple(where_params))

        cursor_sql, cursor_params = _file_event_cursor_clause(where_sql, page.cursor_key)
        rows = _fetch_all(
            self._connection,
            FILE_EVENT_SELECT_FROM
            + f"""
            {where_sql}{cursor_sql}
            ORDER BY sequence_no, event_id
            LIMIT ?
            """,
            (*where_params, *cursor_params, page.limit + 1),
        )

        events = tuple(_file_event_from_row(row) for row in rows)
        page_items = events[: page.limit]
        has_more = len(events) > page.limit
        next_cursor_key = (str(page_items[-1].sequence_no), str(page_items[-1].event_id)) if has_more else None
        return Page(items=page_items, next_cursor_key=next_cursor_key, total=total)

    def status_facets(self, run_id: RunId) -> tuple[FacetValue, ...]:
        """Return FileEvent status facets for one Run, ordered count DESC then value ASC."""
        rows = _fetch_all(
            self._connection,
            """
            SELECT status, COUNT(*) AS count
            FROM file_events
            WHERE run_id = ?
            GROUP BY status
            ORDER BY count DESC, status ASC
            """,
            (str(run_id),),
        )
        return tuple(FacetValue(value=_row_text(row, "status"), count=_row_int(row, "count")) for row in rows)

    def list_target_paths(self, run_id: RunId) -> tuple[str, ...]:
        """Return target_path values recorded for one Run's FileEvents."""
        rows = _fetch_all(
            self._connection,
            """
            SELECT target_path
            FROM file_events
            WHERE run_id = ?
            ORDER BY sequence_no, event_id
            """,
            (str(run_id),),
        )
        return tuple(_row_text(row, "target_path") for row in rows)

    def save(self, event: FileEvent) -> None:
        """Persist a FileEvent before or after a filesystem mutation."""
        _ = self._connection.execute(
            """
            INSERT INTO file_events (
                event_id,
                library_id,
                run_id,
                plan_action_id,
                event_type,
                source_path,
                target_path,
                status,
                started_at,
                completed_at,
                error_code,
                error_message,
                sequence_no
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
                library_id = excluded.library_id,
                run_id = excluded.run_id,
                plan_action_id = excluded.plan_action_id,
                event_type = excluded.event_type,
                source_path = excluded.source_path,
                target_path = excluded.target_path,
                status = excluded.status,
                started_at = excluded.started_at,
                completed_at = excluded.completed_at,
                error_code = excluded.error_code,
                error_message = excluded.error_message,
                sequence_no = excluded.sequence_no
            """,
            (
                str(event.event_id),
                str(event.library_id),
                str(event.run_id),
                str(event.plan_action_id),
                event.event_type.value,
                event.source_path,
                event.target_path,
                event.status.value,
                _timestamp_to_text(event.started_at),
                _optional_timestamp_to_text(event.completed_at),
                event.error_code,
                event.error_message,
                event.sequence_no,
            ),
        )


def _library_from_row(row: sqlite3.Row) -> Library:
    return Library(
        library_id=LibraryId(parse_uuid(_row_text(row, "library_id"))),
        root_path=_row_text(row, "root_path"),
        path_policy_hash=_row_text(row, "path_policy_hash"),
        registered_at=_optional_timestamp_from_text(_row_optional_text(row, "registered_at")),
        status=LibraryStatus(_row_text(row, "status")),
        created_at=_timestamp_from_text(_row_text(row, "created_at")),
        updated_at=_timestamp_from_text(_row_text(row, "updated_at")),
    )


def _track_from_row(row: sqlite3.Row) -> Track:
    return Track(
        track_id=TrackId(parse_uuid(_row_text(row, "track_id"))),
        library_id=LibraryId(parse_uuid(_row_text(row, "library_id"))),
        current_path=_row_text(row, "current_path"),
        canonical_path=_row_text(row, "canonical_path"),
        content_hash=_row_text(row, "content_hash"),
        metadata_hash=_row_text(row, "metadata_hash"),
        size=_row_optional_int(row, "size"),
        mtime=_optional_timestamp_from_text(_row_optional_text(row, "mtime")),
        metadata=_metadata_from_json(_row_text(row, "metadata_json")),
        status=TrackStatus(_row_text(row, "status")),
        first_seen_at=_timestamp_from_text(_row_text(row, "first_seen_at")),
        last_seen_at=_timestamp_from_text(_row_text(row, "last_seen_at")),
        updated_at=_timestamp_from_text(_row_text(row, "updated_at")),
    )


def _check_run_from_row(row: sqlite3.Row) -> CheckRun:
    return CheckRun(
        check_run_id=CheckRunId(parse_uuid(_row_text(row, "check_run_id"))),
        library_id=LibraryId(parse_uuid(_row_text(row, "library_id"))),
        checked_at=_timestamp_from_text(_row_text(row, "checked_at")),
        total_count=_row_int(row, "total_count"),
    )


def _check_issue_from_row(row: sqlite3.Row) -> CheckIssue:
    track_id = _row_optional_text(row, "track_id")
    plan_id = _row_optional_text(row, "plan_id")
    return CheckIssue(
        issue_type=CheckIssueType(_row_text(row, "issue_type")),
        library_id=LibraryId(parse_uuid(_row_text(row, "library_id"))),
        path=_row_optional_text(row, "path"),
        track_id=None if track_id is None else TrackId(parse_uuid(track_id)),
        plan_id=None if plan_id is None else PlanId(parse_uuid(plan_id)),
        detail=_row_optional_text(row, "detail"),
    )


def _plan_from_row(row: sqlite3.Row) -> Plan:
    source_run_id = _row_optional_text(row, "source_run_id")
    return Plan(
        plan_id=PlanId(parse_uuid(_row_text(row, "plan_id"))),
        library_id=LibraryId(parse_uuid(_row_text(row, "library_id"))),
        plan_type=PlanType(_row_text(row, "plan_type")),
        status=PlanStatus(_row_text(row, "status")),
        created_at=_timestamp_from_text(_row_text(row, "created_at")),
        config_hash=_row_text(row, "config_hash"),
        library_root_at_plan=_row_text(row, "library_root_at_plan"),
        source_run_id=None if source_run_id is None else RunId(parse_uuid(source_run_id)),
        summary=_summary_from_json(_row_text(row, "summary_json")),
    )


def _plan_action_from_row(row: sqlite3.Row) -> PlanAction:
    track_id = _row_optional_text(row, "track_id")
    reverses_event_id = _row_optional_text(row, "reverses_event_id")
    reason = _row_optional_text(row, "reason")
    return PlanAction(
        action_id=ActionId(parse_uuid(_row_text(row, "action_id"))),
        plan_id=PlanId(parse_uuid(_row_text(row, "plan_id"))),
        library_id=LibraryId(parse_uuid(_row_text(row, "library_id"))),
        track_id=None if track_id is None else TrackId(parse_uuid(track_id)),
        action_type=ActionType(_row_text(row, "action_type")),
        source_path=_row_optional_text(row, "source_path"),
        target_path=_row_optional_text(row, "target_path"),
        content_hash_at_plan=_row_optional_text(row, "content_hash_at_plan"),
        metadata_hash_at_plan=_row_optional_text(row, "metadata_hash_at_plan"),
        status=ActionStatus(_row_text(row, "status")),
        reason=None if reason is None else PlanActionReason(reason),
        sort_order=_row_int(row, "sort_order"),
        reverses_event_id=None if reverses_event_id is None else EventId(parse_uuid(reverses_event_id)),
    )


def _plan_action_group_row_from_row(row: sqlite3.Row) -> PlanActionGroupRow:
    track_id = _row_optional_text(row, "track_id")
    reason = _row_optional_text(row, "reason")
    return PlanActionGroupRow(
        action_id=ActionId(parse_uuid(_row_text(row, "action_id"))),
        track_id=None if track_id is None else TrackId(parse_uuid(track_id)),
        sort_order=_row_int(row, "sort_order"),
        status=ActionStatus(_row_text(row, "status")),
        reason=None if reason is None else PlanActionReason(reason),
        action_type=ActionType(_row_text(row, "action_type")),
        source_path=_row_optional_text(row, "source_path"),
        target_path=_row_optional_text(row, "target_path"),
        content_hash_at_plan=_row_optional_text(row, "content_hash_at_plan"),
        metadata_hash_at_plan=_row_optional_text(row, "metadata_hash_at_plan"),
    )


def _run_from_row(row: sqlite3.Row) -> Run:
    return Run(
        run_id=RunId(parse_uuid(_row_text(row, "run_id"))),
        plan_id=PlanId(parse_uuid(_row_text(row, "plan_id"))),
        library_id=LibraryId(parse_uuid(_row_text(row, "library_id"))),
        status=RunStatus(_row_text(row, "status")),
        started_at=_timestamp_from_text(_row_text(row, "started_at")),
        completed_at=_optional_timestamp_from_text(_row_optional_text(row, "completed_at")),
        error_summary=_row_optional_text(row, "error_summary"),
    )


def _file_event_from_row(row: sqlite3.Row) -> FileEvent:
    return FileEvent(
        event_id=EventId(parse_uuid(_row_text(row, "event_id"))),
        library_id=LibraryId(parse_uuid(_row_text(row, "library_id"))),
        run_id=RunId(parse_uuid(_row_text(row, "run_id"))),
        plan_action_id=ActionId(parse_uuid(_row_text(row, "plan_action_id"))),
        event_type=FileEventType(_row_text(row, "event_type")),
        source_path=_row_text(row, "source_path"),
        target_path=_row_text(row, "target_path"),
        status=FileEventStatus(_row_text(row, "status")),
        started_at=_timestamp_from_text(_row_text(row, "started_at")),
        completed_at=_optional_timestamp_from_text(_row_optional_text(row, "completed_at")),
        error_code=_row_optional_text(row, "error_code"),
        error_message=_row_optional_text(row, "error_message"),
        sequence_no=_row_int(row, "sequence_no"),
    )


def _operation_lookup_from_row(row: sqlite3.Row) -> OperationLookup:
    status = OperationStatus(_row_text(row, "status"))
    payload_is_expired = (status is OperationStatus.SUCCEEDED and _row_optional_text(row, "result_json") is None) or (
        status in {OperationStatus.FAILED, OperationStatus.INTERRUPTED}
        and _row_optional_text(row, "error_json") is None
    )
    if payload_is_expired:
        return OperationTombstone(
            operation_id=OperationId(parse_uuid(_row_text(row, "operation_id"))),
            idempotency_key=UUID(_row_text(row, "idempotency_key")),
            kind=OperationKind(_row_text(row, "kind")),
            request_fingerprint=_row_text(row, "request_fingerprint"),
            tombstone_expires_at=_timestamp_from_text(_row_text(row, "tombstone_expires_at")),
        )
    return _operation_from_row(row)


def _operation_from_row(row: sqlite3.Row) -> Operation:
    library_id = _row_optional_text(row, "library_id")
    plan_id = _row_optional_text(row, "plan_id")
    run_id = _row_optional_text(row, "run_id")
    return Operation(
        operation_id=OperationId(parse_uuid(_row_text(row, "operation_id"))),
        library_id=None if library_id is None else LibraryId(parse_uuid(library_id)),
        plan_id=None if plan_id is None else PlanId(parse_uuid(plan_id)),
        run_id=None if run_id is None else RunId(parse_uuid(run_id)),
        kind=OperationKind(_row_text(row, "kind")),
        status=OperationStatus(_row_text(row, "status")),
        idempotency_key=UUID(_row_text(row, "idempotency_key")),
        request_fingerprint=_row_text(row, "request_fingerprint"),
        progress=OperationProgress(
            stage_code=_row_optional_text(row, "stage_code"),
            completed_units=_row_optional_int(row, "completed_units"),
            total_units=_row_optional_int(row, "total_units"),
            message=_row_optional_text(row, "progress_message"),
        ),
        result=_operation_result_from_row(row),
        error=_operation_error_from_row(row),
        requested_at=_timestamp_from_text(_row_text(row, "requested_at")),
        started_at=_optional_timestamp_from_text(_row_optional_text(row, "started_at")),
        updated_at=_timestamp_from_text(_row_text(row, "updated_at")),
        completed_at=_optional_timestamp_from_text(_row_optional_text(row, "completed_at")),
        result_expires_at=_optional_timestamp_from_text(_row_optional_text(row, "result_expires_at")),
        tombstone_expires_at=_optional_timestamp_from_text(_row_optional_text(row, "tombstone_expires_at")),
    )


def _operation_result_from_row(row: sqlite3.Row) -> OperationResult | None:
    raw_kind = _row_optional_text(row, "result_kind")
    if raw_kind is None:
        return None
    payload = _json_object(_row_text(row, "result_json"))
    kind = OperationResultKind(raw_kind)
    if kind is OperationResultKind.PLAN_CREATED:
        return PlanCreatedResult(plan_id=PlanId(parse_uuid(_operation_text(payload, "plan_id"))))
    if kind is OperationResultKind.REGISTERED_WITHOUT_PLAN:
        return RegisteredWithoutPlanResult(
            library_id=LibraryId(parse_uuid(_operation_text(payload, "library_id"))),
            track_count=_operation_integer(payload, "track_count"),
        )
    if kind is OperationResultKind.CHECK_COMPLETED:
        return CheckCompletedResult(
            check_run_ids=tuple(
                CheckRunId(parse_uuid(raw_id)) for raw_id in _operation_text_list(payload, "check_run_ids")
            ),
            issue_count=_operation_integer(payload, "issue_count"),
        )
    return RunCompletedResult(run_id=RunId(parse_uuid(_operation_text(payload, "run_id"))))


def _operation_error_from_row(row: sqlite3.Row) -> OperationError | None:
    raw_code = _row_optional_text(row, "error_code")
    if raw_code is None:
        return None
    payload = _json_object(_row_text(row, "error_json"))
    remediation_payload = payload.get("remediation")
    remediation: OperationRemediation | None = None
    if remediation_payload is not None:
        if not isinstance(remediation_payload, dict):
            raise TypeError(INVALID_OPERATION_PAYLOAD_MESSAGE)
        remediation_mapping = cast("dict[str, object]", remediation_payload)
        remediation = OperationRemediation(
            label=_operation_text(remediation_mapping, "label"),
            route=_operation_optional_text(remediation_mapping, "route"),
            command=_operation_optional_text(remediation_mapping, "command"),
        )
    return OperationError(
        code=OperationErrorCode(raw_code),
        message=_operation_text(payload, "message"),
        retryable=_operation_boolean(payload, "retryable"),
        field=_operation_optional_text(payload, "field"),
        remediation=remediation,
    )


def _fetch_one(
    connection: sqlite3.Connection,
    sql: str,
    parameters: tuple[object, ...] = (),
) -> sqlite3.Row | None:
    row = cast("object | None", connection.execute(sql, parameters).fetchone())
    return None if row is None else cast("sqlite3.Row", row)


def _fetch_all(
    connection: sqlite3.Connection,
    sql: str,
    parameters: tuple[object, ...] = (),
) -> tuple[sqlite3.Row, ...]:
    rows = cast("list[object]", connection.execute(sql, parameters).fetchall())
    return tuple(cast("sqlite3.Row", row) for row in rows)


def _scalar_int(connection: sqlite3.Connection, sql: str, parameters: tuple[object, ...] = ()) -> int:
    row = cast("tuple[object, ...] | None", connection.execute(sql, parameters).fetchone())
    if row is None:
        return 0
    value = row[0]
    if isinstance(value, int):
        return value
    raise TypeError(INVALID_ROW_INTEGER_MESSAGE)


def _optional_library_clause(library_id: LibraryId | None) -> tuple[str, list[object]]:
    if library_id is None:
        return "", []
    return " WHERE library_id = ?", [str(library_id)]


def _like_pattern(term: str) -> str:
    """Escape LIKE wildcards in user input and wrap for substring match."""
    escaped = (
        term.replace(LIKE_ESCAPE_CHAR, LIKE_ESCAPE_CHAR * 2)
        .replace("%", f"{LIKE_ESCAPE_CHAR}%")
        .replace("_", f"{LIKE_ESCAPE_CHAR}_")
    )
    return f"%{escaped}%"


def _track_filter_where(
    library_id: LibraryId | None,
    track_id: TrackId | None,
    status: TrackStatus | None,
    search: str | None,
) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if library_id is not None:
        clauses.append("library_id = ?")
        params.append(str(library_id))
    if track_id is not None:
        clauses.append("track_id = ?")
        params.append(str(track_id))
    if status is not None:
        clauses.append("status = ?")
        params.append(status.value)
    if search:
        clauses.append(TRACK_SEARCH_WHERE_CLAUSE)
        params.extend([_like_pattern(search)] * 5)
    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


def _track_cursor_clause(where_sql: str, cursor_key: tuple[str, ...] | None) -> tuple[str, list[object]]:
    if cursor_key is None:
        return "", []
    if len(cursor_key) != KEYSET_CURSOR_KEY_LENGTH:
        raise CursorDecodeError(INVALID_CURSOR_MESSAGE)
    prefix = " AND " if where_sql else " WHERE "
    return f"{prefix}(current_path, track_id) > (?, ?)", list(cursor_key)


def _track_group_member_source_sql(
    grouping: TrackGrouping,
    where_sql: str,
    where_params: list[object],
) -> tuple[str, list[object]]:
    """Return a static source CTE for one exact Track group's members."""
    if grouping is TrackGrouping.ARTIST_ALBUM:
        return _legacy_artist_album_member_source_sql(where_sql, where_params)
    return _track_hierarchy_source_sql(
        grouping,
        where_sql,
        where_params,
        parent_key=None,
        apply_parent_scope=False,
    )


def _legacy_artist_album_member_source_sql(
    where_sql: str,
    where_params: list[object],
) -> tuple[str, list[object]]:
    """Return the existing artist_album key derivation plus grouped-member ordering columns."""
    source_sql = f"""
            WITH base AS (
                SELECT
                    tracks.*,
                    COALESCE(
                        json_extract(metadata_json, '$.album_artist'),
                        json_extract(metadata_json, '$.artist'),
                        ?
                    ) AS group_artist,
                    COALESCE(json_extract(metadata_json, '$.album'), ?) AS group_album,
                    CASE
                        WHEN json_extract(metadata_json, '$.track_number') >= ? THEN ?
                        ELSE ?
                    END AS track_number_rank,
                    CASE
                        WHEN json_extract(metadata_json, '$.track_number') >= ?
                            THEN json_extract(metadata_json, '$.track_number')
                        ELSE ?
                    END AS track_number_value,
                    COALESCE(json_extract(metadata_json, '$.title'), '') AS track_title
                FROM tracks
                {where_sql}
            ), source AS (
                SELECT
                    base.*,
                    group_artist || char(31) || group_album AS group_key
                FROM base
            )
    """  # noqa: S608  # where_sql is built only from static clauses and bound values
    params = [
        TRACK_GROUP_UNKNOWN_KEY,
        TRACK_GROUP_UNKNOWN_KEY,
        *_track_group_member_order_params(),
        *where_params,
    ]
    return source_sql, params


def _track_hierarchy_source_sql(
    grouping: TrackGrouping,
    where_sql: str,
    where_params: list[object],
    *,
    parent_key: str | None,
    apply_parent_scope: bool,
) -> tuple[str, list[object]]:
    """Return a static source CTE for a Track hierarchy level or its members."""
    group_key_sql, group_label_sql, group_label_params = _track_hierarchy_group_expressions(grouping)
    parent_where, parent_params = (
        _track_hierarchy_parent_clause(grouping, parent_key) if apply_parent_scope else ("", [])
    )
    source_sql = f"""
            WITH base AS (
                SELECT
                    tracks.*,
                    CASE
                        WHEN NULLIF(TRIM(json_extract(metadata_json, '$.album_artist'), ?), '') IS NOT NULL
                            THEN json_extract(metadata_json, '$.album_artist')
                        WHEN NULLIF(TRIM(json_extract(metadata_json, '$.artist'), ?), '') IS NOT NULL
                            THEN json_extract(metadata_json, '$.artist')
                        ELSE ?
                    END AS hierarchy_artist,
                    COALESCE(NULLIF(TRIM(json_extract(metadata_json, '$.album'), ?), ''), ?) AS hierarchy_album,
                    json_extract(metadata_json, '$.year') AS hierarchy_year,
                    CASE
                        WHEN json_extract(metadata_json, '$.disc_number') >= ?
                            THEN json_extract(metadata_json, '$.disc_number')
                        ELSE ?
                    END AS hierarchy_disc_key,
                    CASE
                        WHEN json_extract(metadata_json, '$.track_number') >= ? THEN ?
                        ELSE ?
                    END AS track_number_rank,
                    CASE
                        WHEN json_extract(metadata_json, '$.track_number') >= ?
                            THEN json_extract(metadata_json, '$.track_number')
                        ELSE ?
                    END AS track_number_value,
                    COALESCE(json_extract(metadata_json, '$.title'), '') AS track_title
                FROM tracks
                {where_sql}
            ), derived AS (
                SELECT
                    base.*,
                    json_array(hierarchy_artist) AS artist_key,
                    json_array(hierarchy_artist, hierarchy_album, hierarchy_year) AS album_key
                FROM base
            ), source AS (
                SELECT
                    derived.*,
                    {group_key_sql} AS group_key,
                    {group_label_sql} AS group_label
                FROM derived
                {parent_where}
            )
    """  # noqa: S608  # SQL fragments come only from static TrackGrouping branches
    params = [
        TRACK_GROUP_METADATA_WHITESPACE,
        TRACK_GROUP_METADATA_WHITESPACE,
        TRACK_GROUP_UNKNOWN_KEY,
        TRACK_GROUP_METADATA_WHITESPACE,
        TRACK_GROUP_UNKNOWN_KEY,
        MIN_POSITIVE_METADATA_NUMBER,
        TRACK_GROUP_UNKNOWN_KEY,
        *_track_group_member_order_params(),
        *where_params,
        *group_label_params,
        *parent_params,
    ]
    return source_sql, params


def _track_group_member_order_params() -> tuple[object, ...]:
    """Return the bound constants used by every grouped Track member ordering projection."""
    return (
        MIN_POSITIVE_METADATA_NUMBER,
        NUMBERED_TRACK_ORDER_RANK,
        UNNUMBERED_TRACK_ORDER_RANK,
        MIN_POSITIVE_METADATA_NUMBER,
        UNNUMBERED_TRACK_ORDER_VALUE,
    )


def _track_hierarchy_group_expressions(grouping: TrackGrouping) -> tuple[str, str, tuple[object, ...]]:
    """Return static key/label expressions and bound label literals for one hierarchy level."""
    if grouping is TrackGrouping.ARTIST:
        return "artist_key", "hierarchy_artist", ()
    if grouping is TrackGrouping.ALBUM:
        return (
            "album_key",
            """
                CASE
                    WHEN hierarchy_year IS NULL THEN hierarchy_album
                    ELSE hierarchy_album || ? || hierarchy_year
                END
            """,
            (TRACK_GROUP_LABEL_SEPARATOR,),
        )
    if grouping is TrackGrouping.DISC:
        return (
            "json_array(hierarchy_artist, hierarchy_album, hierarchy_year, hierarchy_disc_key)",
            """
                CASE
                    WHEN hierarchy_disc_key = ? THEN ?
                    ELSE ? || hierarchy_disc_key
                END
            """,
            (
                TRACK_GROUP_UNKNOWN_KEY,
                TRACK_GROUP_UNNUMBERED_DISC_LABEL,
                TRACK_GROUP_DISC_LABEL_PREFIX,
            ),
        )
    unsupported_grouping_message = f"{UNSUPPORTED_TRACK_GROUPING_MESSAGE}: {grouping}"
    raise ValueError(unsupported_grouping_message)


def _track_hierarchy_parent_clause(
    grouping: TrackGrouping,
    parent_key: str | None,
) -> tuple[str, list[object]]:
    """Return the static parent-scope predicate for an artist, album, or disc level."""
    if grouping is TrackGrouping.ARTIST:
        return "", []
    if grouping is TrackGrouping.ALBUM:
        return " WHERE artist_key = ?", [parent_key]
    if grouping is TrackGrouping.DISC:
        return " WHERE album_key = ?", [parent_key]
    unsupported_grouping_message = f"{UNSUPPORTED_TRACK_GROUPING_MESSAGE}: {grouping}"
    raise ValueError(unsupported_grouping_message)


def _track_group_member_cursor_clause(cursor_key: tuple[str, ...] | None) -> tuple[str, list[object]]:
    """Build the fixed music-order keyset predicate for one exact Track group."""
    if cursor_key is None:
        return "", []
    if len(cursor_key) != TRACK_GROUP_MEMBER_CURSOR_KEY_LENGTH:
        raise CursorDecodeError(INVALID_CURSOR_MESSAGE)
    rank_text, number_text, title, track_id = cursor_key
    try:
        rank = int(rank_text)
        number = int(number_text)
    except ValueError as error:
        raise CursorDecodeError(INVALID_CURSOR_MESSAGE) from error
    return (
        " AND (track_number_rank, track_number_value, track_title, track_id) > (?, ?, ?, ?)",
        [rank, number, title, track_id],
    )


def _track_group_member_cursor_key(track: Track) -> tuple[str, str, str, str]:
    """Return the cursor key matching the grouped Track member SQL ordering exactly."""
    track_number = track.metadata.track_number
    title = track.metadata.title or ""
    if track_number is not None and track_number >= MIN_POSITIVE_METADATA_NUMBER:
        return (str(NUMBERED_TRACK_ORDER_RANK), str(track_number), title, str(track.track_id))
    return (str(UNNUMBERED_TRACK_ORDER_RANK), str(UNNUMBERED_TRACK_ORDER_VALUE), title, str(track.track_id))


def _check_issue_filter_where(
    library_id: LibraryId | None,
    search: str | None,
    issue_type: CheckIssueType | None,
) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if library_id is not None:
        clauses.append("library_id = ?")
        params.append(str(library_id))
    if issue_type is not None:
        clauses.append("issue_type = ?")
        params.append(issue_type.value)
    if search:
        clauses.append(_like_search_clause(CHECK_ISSUE_SEARCH_COLUMN_NAMES))
        params.extend([_like_pattern(search)] * len(CHECK_ISSUE_SEARCH_COLUMN_NAMES))
    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


def _check_issue_group_filter_where(
    library_id: LibraryId | None,
    search: str | None,
    issue_type: CheckIssueType | None,
) -> tuple[str, list[object]]:
    """Build static, aliased SQL filters for a CheckIssue group source CTE."""
    clauses: list[str] = []
    params: list[object] = []
    if library_id is not None:
        clauses.append("ci.library_id = ?")
        params.append(str(library_id))
    if issue_type is not None:
        clauses.append("ci.issue_type = ?")
        params.append(issue_type.value)
    if search:
        clauses.append(_like_search_clause(CHECK_ISSUE_SEARCH_COLUMN_NAMES, alias="ci."))
        params.extend([_like_pattern(search)] * len(CHECK_ISSUE_SEARCH_COLUMN_NAMES))
    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


def _like_search_clause(column_names: tuple[str, ...], *, alias: str = "") -> str:
    """Return a static substring-search clause over trusted column names and table alias."""
    comparisons = [f"LOWER({alias}{column}) LIKE LOWER(?) ESCAPE '{LIKE_ESCAPE_CHAR}'" for column in column_names]
    return "(" + " OR ".join(comparisons) + ")"


def _check_issue_group_source_sql(grouping: CheckIssueGrouping, where_sql: str) -> str:
    """Return a static CTE that projects one requested CheckIssue grouping and path root."""
    group_key_sql, group_label_sql = _check_issue_group_expressions(grouping)
    return f"""
            WITH base AS (
                SELECT
                    ci.issue_seq,
                    ci.check_run_id,
                    ci.library_id,
                    ci.issue_type,
                    ci.path,
                    ci.track_id,
                    ci.plan_id,
                    ci.detail,
                    {CHECK_ISSUE_PATH_ROOT_SELECT} AS path_root,
                    {CHECK_ISSUE_ARTIST_SEGMENT_SELECT} AS group_artist,
                    {CHECK_ISSUE_ALBUM_SEGMENT_SELECT} AS group_album,
                    {CHECK_ISSUE_SEVERITY_SELECT} AS issue_severity,
                    {CHECK_ISSUE_COMMAND_KEY_SELECT} AS suggested_command_key,
                    {CHECK_ISSUE_COMMAND_LABEL_SELECT} AS suggested_command_label
                FROM check_issues AS ci
                {where_sql}
            ), source AS (
                SELECT
                    issue_seq,
                    check_run_id,
                    library_id,
                    issue_type,
                    path,
                    track_id,
                    plan_id,
                    detail,
                    path_root,
                    {group_key_sql} AS group_key,
                    {group_label_sql} AS group_label
                FROM base
            )
    """  # noqa: S608  # interpolated fragments are selected only from static grouping SQL templates


def _check_issue_group_expressions(grouping: CheckIssueGrouping) -> tuple[str, str]:
    """Return static SQL expressions for the CheckIssue group key and display label."""
    if grouping is CheckIssueGrouping.ISSUE_TYPE:
        return "issue_type", "issue_type"
    if grouping is CheckIssueGrouping.SEVERITY:
        return "issue_severity", "issue_severity"
    if grouping is CheckIssueGrouping.PATH_ROOT:
        path_root = f"COALESCE(path_root, '{CHECK_ISSUE_GROUP_UNKNOWN_KEY}')"
        return path_root, path_root
    if grouping is CheckIssueGrouping.ARTIST_ALBUM:
        return (
            f"""
                CASE
                    WHEN group_artist IS NULL THEN '{CHECK_ISSUE_GROUP_UNKNOWN_KEY}'
                    WHEN group_artist IN ('{CHECK_ISSUE_GROUP_ROOT_KEY}', '{CHECK_ISSUE_GROUP_EXTERNAL_KEY}') THEN group_artist
                    ELSE group_artist || char(31) || group_album -- char(31) is CHECK_ISSUE_GROUP_ARTIST_ALBUM_SEPARATOR
                END
            """,
            f"""
                CASE
                    WHEN group_artist IS NULL THEN '{CHECK_ISSUE_GROUP_UNKNOWN_ARTIST_ALBUM_LABEL}'
                    WHEN group_artist IN ('{CHECK_ISSUE_GROUP_ROOT_KEY}', '{CHECK_ISSUE_GROUP_EXTERNAL_KEY}') THEN group_artist
                    ELSE group_artist || '{CHECK_ISSUE_GROUP_ARTIST_ALBUM_LABEL_SEPARATOR}' || group_album
                END
            """,
        )
    if grouping is CheckIssueGrouping.SUGGESTED_COMMAND:
        return "suggested_command_key", "suggested_command_label"
    return "library_id", "library_id"


def _check_issue_cursor_clause(where_sql: str, cursor_key: tuple[str, ...] | None) -> tuple[str, list[object]]:
    if cursor_key is None:
        return "", []
    if len(cursor_key) != CHECK_ISSUE_CURSOR_KEY_LENGTH:
        raise CursorDecodeError(INVALID_CURSOR_MESSAGE)
    (issue_seq_text,) = cursor_key
    try:
        issue_seq_value = int(issue_seq_text)
    except ValueError as error:
        raise CursorDecodeError(INVALID_CURSOR_MESSAGE) from error
    prefix = " AND " if where_sql else " WHERE "
    return f"{prefix}issue_seq > ?", [issue_seq_value]


def _plan_filter_where(
    library_id: LibraryId | None,
    search: str | None,
    status: PlanStatus | None,
    plan_type: PlanType | None,
    *,
    blocked_only: bool,
) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if library_id is not None:
        clauses.append("library_id = ?")
        params.append(str(library_id))
    if search:
        clauses.append(_like_search_clause(PLAN_SEARCH_COLUMN_NAMES))
        params.extend([_like_pattern(search)] * len(PLAN_SEARCH_COLUMN_NAMES))
    if status is not None:
        clauses.append("status = ?")
        params.append(status.value)
    if plan_type is not None:
        clauses.append("plan_type = ?")
        params.append(plan_type.value)
    if blocked_only:
        clauses.append("EXISTS (SELECT 1 FROM plan_actions WHERE plan_actions.plan_id = plans.plan_id AND status = ?)")
        params.append(ActionStatus.BLOCKED.value)
    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


def _plan_cursor_clause(where_sql: str, cursor_key: tuple[str, ...] | None) -> tuple[str, list[object]]:
    if cursor_key is None:
        return "", []
    if len(cursor_key) != KEYSET_CURSOR_KEY_LENGTH:
        raise CursorDecodeError(INVALID_CURSOR_MESSAGE)
    prefix = " AND " if where_sql else " WHERE "
    # DESC ordering: rows strictly "after" the cursor in (created_at DESC, plan_id DESC) order compare `<`.
    return f"{prefix}(created_at, plan_id) < (?, ?)", list(cursor_key)


def _plan_action_filter_where(
    plan_id: PlanId,
    search: str | None,
    status: ActionStatus | None,
    action_type: ActionType | None,
    reason: PlanActionReason | None,
) -> tuple[str, list[object]]:
    clauses: list[str] = ["plan_id = ?"]
    params: list[object] = [str(plan_id)]
    if status is not None:
        clauses.append("status = ?")
        params.append(status.value)
    if action_type is not None:
        clauses.append("action_type = ?")
        params.append(action_type.value)
    if reason is not None:
        clauses.append("reason = ?")
        params.append(reason.value)
    if search:
        clauses.append(_like_search_clause(PLAN_ACTION_SEARCH_COLUMN_NAMES))
        params.extend([_like_pattern(search)] * len(PLAN_ACTION_SEARCH_COLUMN_NAMES))
    return " WHERE " + " AND ".join(clauses), params


def _plan_action_cursor_clause(where_sql: str, cursor_key: tuple[str, ...] | None) -> tuple[str, list[object]]:
    if cursor_key is None:
        return "", []
    if len(cursor_key) != KEYSET_CURSOR_KEY_LENGTH:
        raise CursorDecodeError(INVALID_CURSOR_MESSAGE)
    sort_order_text, action_id_text = cursor_key
    try:
        sort_order_value = int(sort_order_text)
    except ValueError as error:
        raise CursorDecodeError(INVALID_CURSOR_MESSAGE) from error
    prefix = " AND " if where_sql else " WHERE "
    return f"{prefix}(sort_order, action_id) > (?, ?)", [sort_order_value, action_id_text]


def _run_filter_where(
    library_id: LibraryId | None,
    search: str | None,
    plan_id: PlanId | None,
    status: RunStatus | None,
) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if library_id is not None:
        clauses.append("library_id = ?")
        params.append(str(library_id))
    if search:
        clauses.append(_like_search_clause(RUN_SEARCH_COLUMN_NAMES))
        params.extend([_like_pattern(search)] * len(RUN_SEARCH_COLUMN_NAMES))
    if plan_id is not None:
        clauses.append("plan_id = ?")
        params.append(str(plan_id))
    if status is not None:
        clauses.append("status = ?")
        params.append(status.value)
    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


def _run_cursor_clause(where_sql: str, cursor_key: tuple[str, ...] | None) -> tuple[str, list[object]]:
    if cursor_key is None:
        return "", []
    if len(cursor_key) != KEYSET_CURSOR_KEY_LENGTH:
        raise CursorDecodeError(INVALID_CURSOR_MESSAGE)
    prefix = " AND " if where_sql else " WHERE "
    # DESC ordering: rows strictly "after" the cursor in (started_at DESC, run_id DESC) order compare `<`.
    return f"{prefix}(started_at, run_id) < (?, ?)", list(cursor_key)


def _file_event_filter_where(run_id: RunId, status: FileEventStatus | None) -> tuple[str, list[object]]:
    clauses: list[str] = ["run_id = ?"]
    params: list[object] = [str(run_id)]
    if status is not None:
        clauses.append("status = ?")
        params.append(status.value)
    return " WHERE " + " AND ".join(clauses), params


def _file_event_cursor_clause(where_sql: str, cursor_key: tuple[str, ...] | None) -> tuple[str, list[object]]:
    if cursor_key is None:
        return "", []
    if len(cursor_key) != KEYSET_CURSOR_KEY_LENGTH:
        raise CursorDecodeError(INVALID_CURSOR_MESSAGE)
    sequence_no_text, event_id_text = cursor_key
    try:
        sequence_no_value = int(sequence_no_text)
    except ValueError as error:
        raise CursorDecodeError(INVALID_CURSOR_MESSAGE) from error
    prefix = " AND " if where_sql else " WHERE "
    return f"{prefix}(sequence_no, event_id) > (?, ?)", [sequence_no_value, event_id_text]


def _track_group_cursor_clause(cursor_key: tuple[str, ...] | None) -> tuple[str, list[object]]:
    if cursor_key is None:
        return "", []
    if len(cursor_key) != KEYSET_CURSOR_KEY_LENGTH:
        raise CursorDecodeError(INVALID_CURSOR_MESSAGE)
    cursor_count_text, cursor_key_text = cursor_key
    try:
        cursor_count = int(cursor_count_text)
    except ValueError as error:
        raise CursorDecodeError(INVALID_CURSOR_MESSAGE) from error
    return " WHERE (count < ?) OR (count = ? AND key > ?)", [cursor_count, cursor_count, cursor_key_text]


def _row_text(row: sqlite3.Row, key: str) -> str:
    value = cast("object", row[key])
    if isinstance(value, str):
        return value
    raise TypeError(INVALID_ROW_TEXT_MESSAGE)


def _row_optional_text(row: sqlite3.Row, key: str) -> str | None:
    value = cast("object", row[key])
    if value is None or isinstance(value, str):
        return value
    raise TypeError(INVALID_ROW_TEXT_MESSAGE)


def _row_int(row: sqlite3.Row, key: str) -> int:
    value = cast("object", row[key])
    if isinstance(value, int):
        return value
    raise TypeError(INVALID_ROW_INTEGER_MESSAGE)


def _row_optional_int(row: sqlite3.Row, key: str) -> int | None:
    value = cast("object", row[key])
    if value is None or isinstance(value, int):
        return value
    raise TypeError(INVALID_ROW_INTEGER_MESSAGE)


def _timestamp_to_text(value: datetime) -> str:
    return as_utc(value).isoformat()


def _optional_timestamp_to_text(value: datetime | None) -> str | None:
    return None if value is None else _timestamp_to_text(value)


def _timestamp_from_text(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _optional_timestamp_from_text(value: str | None) -> datetime | None:
    return None if value is None else _timestamp_from_text(value)


def _metadata_to_json(metadata: TrackMetadata) -> str:
    return _json_to_text(metadata.fingerprint_payload())


def _metadata_from_json(raw_value: str) -> TrackMetadata:
    payload = _json_object(raw_value)
    return TrackMetadata(
        title=_optional_str(payload, "title"),
        artist=_optional_str(payload, "artist"),
        album=_optional_str(payload, "album"),
        album_artist=_optional_str(payload, "album_artist"),
        genre=_optional_str(payload, "genre"),
        year=_optional_int(payload, "year"),
        track_number=_optional_int(payload, "track_number"),
        track_total=_optional_int(payload, "track_total"),
        disc_number=_optional_int(payload, "disc_number"),
        disc_total=_optional_int(payload, "disc_total"),
    )


def _summary_to_json(summary: Mapping[str, str]) -> str:
    return _json_to_text(summary)


def _summary_from_json(raw_value: str) -> dict[str, str]:
    payload = _json_object(raw_value)
    summary: dict[str, str] = {}
    for key, value in payload.items():
        if not isinstance(value, str):
            raise TypeError(INVALID_SUMMARY_VALUE_MESSAGE)
        summary[key] = value
    return summary


def _operation_result_to_json(result: OperationResult) -> str:
    if isinstance(result, PlanCreatedResult):
        payload: dict[str, object] = {"plan_id": str(result.plan_id)}
    elif isinstance(result, RegisteredWithoutPlanResult):
        payload = {"library_id": str(result.library_id), "track_count": result.track_count}
    elif isinstance(result, CheckCompletedResult):
        payload = {
            "check_run_ids": [str(check_run_id) for check_run_id in result.check_run_ids],
            "issue_count": result.issue_count,
        }
    else:
        payload = {"run_id": str(result.run_id)}
    return _json_to_text(payload)


def _operation_error_to_json(error: OperationError) -> str:
    payload: dict[str, object] = {
        "message": error.message,
        "retryable": error.retryable,
    }
    if error.field is not None:
        payload["field"] = error.field
    if error.remediation is not None:
        remediation: dict[str, object] = {"label": error.remediation.label}
        if error.remediation.route is not None:
            remediation["route"] = error.remediation.route
        if error.remediation.command is not None:
            remediation["command"] = error.remediation.command
        payload["remediation"] = remediation
    return _json_to_text(payload)


def _json_to_text(payload: Mapping[str, object]) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(PERSISTED_JSON_ITEM_SEPARATOR, PERSISTED_JSON_KEY_SEPARATOR),
    )


def _json_object(raw_value: str) -> dict[str, object]:
    payload = cast("object", json.loads(raw_value))
    if not isinstance(payload, dict):
        raise TypeError(INVALID_JSON_OBJECT_MESSAGE)
    return cast("dict[str, object]", payload)


def _optional_str(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None or isinstance(value, str):
        return value
    raise TypeError(INVALID_METADATA_VALUE_MESSAGE)


def _optional_int(payload: Mapping[str, object], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise TypeError(INVALID_METADATA_VALUE_MESSAGE)


def _operation_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, str):
        return value
    raise TypeError(INVALID_OPERATION_PAYLOAD_MESSAGE)


def _operation_optional_text(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None or isinstance(value, str):
        return value
    raise TypeError(INVALID_OPERATION_PAYLOAD_MESSAGE)


def _operation_integer(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise TypeError(INVALID_OPERATION_PAYLOAD_MESSAGE)


def _operation_boolean(payload: Mapping[str, object], key: str) -> bool:
    value = payload.get(key)
    if isinstance(value, bool):
        return value
    raise TypeError(INVALID_OPERATION_PAYLOAD_MESSAGE)


def _operation_text_list(payload: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise TypeError(INVALID_OPERATION_PAYLOAD_MESSAGE)
    items = cast("list[object]", value)
    if not all(isinstance(item, str) for item in items):
        raise TypeError(INVALID_OPERATION_PAYLOAD_MESSAGE)
    return tuple(cast("list[str]", items))
