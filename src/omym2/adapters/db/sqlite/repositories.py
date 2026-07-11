"""
Summary: Implements SQLite-backed domain repositories.
Why: Persists OMYM2 state without moving business rules into the DB adapter.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, cast

from omym2.config import PERSISTED_JSON_ITEM_SEPARATOR, PERSISTED_JSON_KEY_SEPARATOR
from omym2.domain.models.check_issue import CheckIssue, CheckIssueType
from omym2.domain.models.check_run import CheckRun
from omym2.domain.models.file_event import FileEvent, FileEventStatus, FileEventType
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction, PlanActionReason
from omym2.domain.models.run import Run, RunStatus
from omym2.domain.models.track import Track, TrackGrouping, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.shared.ids import ActionId, CheckRunId, EventId, LibraryId, PlanId, RunId, TrackId, parse_uuid
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
LIKE_ESCAPE_CHAR = "\\"  # escape character used for LIKE search patterns
UNSUPPORTED_TRACK_GROUPING_MESSAGE = "Unsupported Track grouping"
UNKNOWN_TRACK_GROUP_LABEL = "(unknown)"
TRACK_GROUP_LABEL_SEPARATOR = " — "  # em dash joiner between group artist and group album labels
KEYSET_CURSOR_KEY_LENGTH = 2  # every keyset cursor key in this module is a 2-tuple
CHECK_ISSUE_CURSOR_KEY_LENGTH = 1  # a CheckIssue cursor key is a single issue_seq value

TRACK_SEARCH_WHERE_CLAUSE = f"""(
                LOWER(json_extract(metadata_json, '$.title')) LIKE LOWER(?) ESCAPE '{LIKE_ESCAPE_CHAR}' OR
                LOWER(json_extract(metadata_json, '$.artist')) LIKE LOWER(?) ESCAPE '{LIKE_ESCAPE_CHAR}' OR
                LOWER(json_extract(metadata_json, '$.album')) LIKE LOWER(?) ESCAPE '{LIKE_ESCAPE_CHAR}' OR
                LOWER(current_path) LIKE LOWER(?) ESCAPE '{LIKE_ESCAPE_CHAR}' OR
                LOWER(track_id) LIKE LOWER(?) ESCAPE '{LIKE_ESCAPE_CHAR}'
            )"""
TRACK_GROUP_SOURCE_SELECT = """
            SELECT
                COALESCE(json_extract(metadata_json, '$.album_artist'), json_extract(metadata_json, '$.artist'), ?)
                    AS group_artist,
                COALESCE(json_extract(metadata_json, '$.album'), ?) AS group_album
            FROM tracks
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
            SELECT plan_id, library_id, plan_type, status, created_at, config_hash, library_root_at_plan, summary_json
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

    def query_page(
        self,
        library_id: LibraryId | None,
        *,
        issue_type: CheckIssueType | None,
        page: PageRequest,
    ) -> Page[CheckIssue]:
        """Return one keyset page of CheckIssues ordered issue_seq ASC."""
        where_sql, where_params = _check_issue_filter_where(library_id, issue_type)
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

    def issue_type_facets(self, library_id: LibraryId | None) -> tuple[FacetValue, ...]:
        """Return CheckIssue issue_type facets, ordered count DESC then value ASC."""
        where_sql, where_params = _optional_library_clause(library_id)
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

    def group_page(self, library_id: LibraryId | None, page: PageRequest) -> Page[GroupCount]:
        """Return one keyset page of CheckIssue groups by issue_type ordered count DESC then key ASC."""
        library_where, library_params = _optional_library_clause(library_id)

        # SQL-injection safety note: library_where is a static clause template bound with `?`; never raw input.
        total = _scalar_int(
            self._connection,
            f"""
            SELECT COUNT(*) FROM (
                SELECT 1
                FROM check_issues
                {library_where}
                GROUP BY issue_type
            )
            """,  # noqa: S608
            tuple(library_params),
        )

        cursor_sql, cursor_params = _track_group_cursor_clause(page.cursor_key)
        # SQL-injection safety note: library_where and cursor_sql are static templates bound with `?`; never raw input.
        rows = _fetch_all(
            self._connection,
            f"""
            SELECT key, label, count
            FROM (
                SELECT issue_type AS key, issue_type AS label, COUNT(*) AS count
                FROM check_issues
                {library_where}
                GROUP BY issue_type
            )
            {cursor_sql}
            ORDER BY count DESC, key ASC
            LIMIT ?
            """,  # noqa: S608
            (*library_params, *cursor_params, page.limit + 1),
        )

        groups = tuple(
            GroupCount(key=_row_text(row, "key"), label=_row_text(row, "label"), count=_row_int(row, "count"))
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

    def query_page(
        self,
        library_id: LibraryId | None,
        *,
        track_id: TrackId | None,
        search: str | None,
        status: TrackStatus | None,
        page: PageRequest,
    ) -> Page[Track]:
        """Return one keyset page of Tracks ordered (current_path, track_id)."""
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

    def status_facets(self, library_id: LibraryId | None) -> tuple[FacetValue, ...]:
        """Return Track status facet counts, ordered count DESC then value ASC."""
        where_sql, where_params = _optional_library_clause(library_id)
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

    def group_page(
        self,
        library_id: LibraryId | None,
        grouping: TrackGrouping,
        page: PageRequest,
    ) -> Page[GroupCount]:
        """Return one keyset page of Track groups ordered count DESC then key ASC."""
        if grouping is not TrackGrouping.ARTIST_ALBUM:
            unsupported_grouping_message = f"{UNSUPPORTED_TRACK_GROUPING_MESSAGE}: {grouping}"
            raise ValueError(unsupported_grouping_message)  # pyright: ignore[reportUnreachable]

        library_where, library_params = _optional_library_clause(library_id)
        source_params = [UNKNOWN_TRACK_GROUP_LABEL, UNKNOWN_TRACK_GROUP_LABEL, *library_params]

        # SQL-injection safety note: TRACK_GROUP_SOURCE_SELECT and library_where are static templates bound with `?`.
        total = _scalar_int(
            self._connection,
            f"""
            SELECT COUNT(*) FROM (
                SELECT 1
                FROM (
                    {TRACK_GROUP_SOURCE_SELECT}
                    {library_where}
                )
                GROUP BY group_artist, group_album
            )
            """,  # noqa: S608
            tuple(source_params),
        )

        cursor_sql, cursor_params = _track_group_cursor_clause(page.cursor_key)
        # SQL-injection safety note: TRACK_GROUP_SOURCE_SELECT, library_where, and cursor_sql are static templates
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
                    {library_where}
                )
                GROUP BY group_artist, group_album
            )
            {cursor_sql}
            ORDER BY count DESC, key ASC
            LIMIT ?
            """,  # noqa: S608
            (
                TRACK_GROUP_LABEL_SEPARATOR,
                UNKNOWN_TRACK_GROUP_LABEL,
                UNKNOWN_TRACK_GROUP_LABEL,
                *library_params,
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

    def query_page(
        self,
        library_id: LibraryId | None,
        *,
        status: PlanStatus | None,
        plan_type: PlanType | None,
        page: PageRequest,
    ) -> Page[Plan]:
        """Return one keyset page of Plans ordered (created_at DESC, plan_id DESC)."""
        where_sql, where_params = _plan_filter_where(library_id, status, plan_type)
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
                plan_type,
                status,
                created_at,
                config_hash,
                library_root_at_plan,
                summary_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(plan_id) DO UPDATE SET
                library_id = excluded.library_id,
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
                plan.plan_type.value,
                plan.status.value,
                _timestamp_to_text(plan.created_at),
                plan.config_hash,
                plan.library_root_at_plan,
                _summary_to_json(plan.summary),
            ),
        )


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

    def query_page(
        self,
        plan_id: PlanId,
        *,
        status: ActionStatus | None,
        page: PageRequest,
    ) -> Page[PlanAction]:
        """Return one keyset page of a Plan's actions ordered (sort_order, action_id)."""
        where_sql, where_params = _plan_action_filter_where(plan_id, status)
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

    def status_facets(self, plan_id: PlanId) -> tuple[FacetValue, ...]:
        """Return PlanAction status facets for one Plan, ordered count DESC then value ASC."""
        rows = _fetch_all(
            self._connection,
            """
            SELECT status, COUNT(*) AS count
            FROM plan_actions
            WHERE plan_id = ?
            GROUP BY status
            ORDER BY count DESC, status ASC
            """,
            (str(plan_id),),
        )
        return tuple(FacetValue(value=_row_text(row, "status"), count=_row_int(row, "count")) for row in rows)

    def action_type_facets(self, plan_id: PlanId) -> tuple[FacetValue, ...]:
        """Return PlanAction type facets for one Plan, ordered count DESC then value ASC."""
        rows = _fetch_all(
            self._connection,
            """
            SELECT action_type, COUNT(*) AS count
            FROM plan_actions
            WHERE plan_id = ?
            GROUP BY action_type
            ORDER BY count DESC, action_type ASC
            """,
            (str(plan_id),),
        )
        return tuple(FacetValue(value=_row_text(row, "action_type"), count=_row_int(row, "count")) for row in rows)

    def list_target_paths(self, plan_id: PlanId) -> tuple[str, ...]:
        """Return the non-null target_path values recorded for one Plan's actions."""
        rows = _fetch_all(
            self._connection,
            """
            SELECT target_path
            FROM plan_actions
            WHERE plan_id = ? AND target_path IS NOT NULL
            ORDER BY sort_order, action_id
            """,
            (str(plan_id),),
        )
        return tuple(_row_text(row, "target_path") for row in rows)

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
                content_hash_at_plan,
                metadata_hash_at_plan,
                status,
                reason,
                sort_order
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(action_id) DO UPDATE SET
                plan_id = excluded.plan_id,
                library_id = excluded.library_id,
                track_id = excluded.track_id,
                action_type = excluded.action_type,
                source_path = excluded.source_path,
                target_path = excluded.target_path,
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
                action.content_hash_at_plan,
                action.metadata_hash_at_plan,
                action.status.value,
                None if action.reason is None else action.reason.value,
                action.sort_order,
            ),
        )


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
        plan_id: PlanId | None,
        status: RunStatus | None,
        page: PageRequest,
    ) -> Page[Run]:
        """Return one keyset page of Runs ordered (started_at DESC, run_id DESC)."""
        where_sql, where_params = _run_filter_where(library_id, plan_id, status)
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
    return Plan(
        plan_id=PlanId(parse_uuid(_row_text(row, "plan_id"))),
        library_id=LibraryId(parse_uuid(_row_text(row, "library_id"))),
        plan_type=PlanType(_row_text(row, "plan_type")),
        status=PlanStatus(_row_text(row, "status")),
        created_at=_timestamp_from_text(_row_text(row, "created_at")),
        config_hash=_row_text(row, "config_hash"),
        library_root_at_plan=_row_text(row, "library_root_at_plan"),
        summary=_summary_from_json(_row_text(row, "summary_json")),
    )


def _plan_action_from_row(row: sqlite3.Row) -> PlanAction:
    track_id = _row_optional_text(row, "track_id")
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


def _check_issue_filter_where(
    library_id: LibraryId | None,
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
    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


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
    status: PlanStatus | None,
    plan_type: PlanType | None,
) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if library_id is not None:
        clauses.append("library_id = ?")
        params.append(str(library_id))
    if status is not None:
        clauses.append("status = ?")
        params.append(status.value)
    if plan_type is not None:
        clauses.append("plan_type = ?")
        params.append(plan_type.value)
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


def _plan_action_filter_where(plan_id: PlanId, status: ActionStatus | None) -> tuple[str, list[object]]:
    clauses: list[str] = ["plan_id = ?"]
    params: list[object] = [str(plan_id)]
    if status is not None:
        clauses.append("status = ?")
        params.append(status.value)
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
    plan_id: PlanId | None,
    status: RunStatus | None,
) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if library_id is not None:
        clauses.append("library_id = ?")
        params.append(str(library_id))
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
