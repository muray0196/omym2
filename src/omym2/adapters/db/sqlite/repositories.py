"""
Summary: Implements SQLite-backed domain repositories.
Why: Persists OMYM2 state without moving business rules into the DB adapter.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, cast

from omym2.config import PERSISTED_JSON_ITEM_SEPARATOR, PERSISTED_JSON_KEY_SEPARATOR
from omym2.domain.models.file_event import FileEvent, FileEventStatus, FileEventType
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction, PlanActionReason
from omym2.domain.models.run import Run, RunStatus
from omym2.domain.models.track import Track, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.shared.ids import ActionId, EventId, LibraryId, PlanId, RunId, TrackId, parse_uuid
from omym2.shared.time import as_utc

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Mapping

INVALID_JSON_OBJECT_MESSAGE = "Persisted JSON payload must be an object."
INVALID_METADATA_VALUE_MESSAGE = "Persisted metadata JSON contains an unsupported value."
INVALID_ROW_TEXT_MESSAGE = "Expected SQLite text value."
INVALID_ROW_INTEGER_MESSAGE = "Expected SQLite integer value."
INVALID_SUMMARY_VALUE_MESSAGE = "Persisted summary JSON must contain string values."

TRACK_SELECT_FROM = """
            SELECT
                track_id,
                library_id,
                current_path,
                canonical_path,
                content_hash,
                metadata_hash,
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

    def find_by_content_hash(self, library_id: LibraryId, content_hash: str) -> tuple[Track, ...]:
        """Return Tracks with a matching content hash in one Library."""
        rows = _fetch_all(
            self._connection,
            TRACK_SELECT_FROM
            + """
            WHERE library_id = ? AND content_hash = ?
            ORDER BY current_path, track_id
            """,
            (str(library_id), content_hash),
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
                metadata_json,
                status,
                first_seen_at,
                last_seen_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(track_id) DO UPDATE SET
                library_id = excluded.library_id,
                current_path = excluded.current_path,
                canonical_path = excluded.canonical_path,
                content_hash = excluded.content_hash,
                metadata_hash = excluded.metadata_hash,
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
                _metadata_to_json(track.metadata),
                track.status.value,
                _timestamp_to_text(track.first_seen_at),
                _timestamp_to_text(track.last_seen_at),
                _timestamp_to_text(track.updated_at),
            ),
        )


class SQLitePlanRepository(_SQLiteRepository):
    """SQLite implementation of PlanRepository."""

    def get(self, plan_id: PlanId) -> Plan | None:
        """Return one Plan by ID."""
        row = _fetch_one(
            self._connection,
            """
            SELECT plan_id, library_id, plan_type, status, created_at, config_hash, library_root_at_plan, summary_json
            FROM plans
            WHERE plan_id = ?
            """,
            (str(plan_id),),
        )
        return None if row is None else _plan_from_row(row)

    def list_by_library(self, library_id: LibraryId) -> tuple[Plan, ...]:
        """Return Plans owned by one Library."""
        rows = _fetch_all(
            self._connection,
            """
            SELECT plan_id, library_id, plan_type, status, created_at, config_hash, library_root_at_plan, summary_json
            FROM plans
            WHERE library_id = ?
            ORDER BY created_at, plan_id
            """,
            (str(library_id),),
        )
        return tuple(_plan_from_row(row) for row in rows)

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
            """
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
            WHERE action_id = ?
            """,
            (str(action_id),),
        )
        return None if row is None else _plan_action_from_row(row)

    def list_by_plan(self, plan_id: PlanId) -> tuple[PlanAction, ...]:
        """Return the actions recorded for a Plan in apply order."""
        rows = _fetch_all(
            self._connection,
            """
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
            WHERE plan_id = ?
            ORDER BY sort_order, action_id
            """,
            (str(plan_id),),
        )
        return tuple(_plan_action_from_row(row) for row in rows)

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


class SQLiteFileEventRepository(_SQLiteRepository):
    """SQLite implementation of FileEventRepository."""

    def get(self, event_id: EventId) -> FileEvent | None:
        """Return one FileEvent by ID."""
        row = _fetch_one(
            self._connection,
            """
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
            WHERE event_id = ?
            """,
            (str(event_id),),
        )
        return None if row is None else _file_event_from_row(row)

    def list_by_run(self, run_id: RunId) -> tuple[FileEvent, ...]:
        """Return FileEvents recorded for one Run in sequence order."""
        rows = _fetch_all(
            self._connection,
            """
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
            """
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
            WHERE library_id = ?
            ORDER BY started_at, sequence_no, event_id
            """,
            (str(library_id),),
        )
        return tuple(_file_event_from_row(row) for row in rows)

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
        metadata=_metadata_from_json(_row_text(row, "metadata_json")),
        status=TrackStatus(_row_text(row, "status")),
        first_seen_at=_timestamp_from_text(_row_text(row, "first_seen_at")),
        last_seen_at=_timestamp_from_text(_row_text(row, "last_seen_at")),
        updated_at=_timestamp_from_text(_row_text(row, "updated_at")),
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
