"""
Summary: Implements the history CLI command.
Why: Exposes Run history without coupling CLI output to persistence details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from omym2.adapters.cli.commands.output import write_line, write_usage
from omym2.features.history.dto import GetRunDetailRequest, ListRunEventsRequest, ListRunsRequest
from omym2.features.history.usecases.get_run_detail import GetRunDetailUseCase, RunNotFoundError
from omym2.features.history.usecases.list_run_events import ListRunEventsUseCase
from omym2.features.history.usecases.list_runs import ListRunsUseCase
from omym2.shared.ids import RunId, parse_uuid
from omym2.shared.pagination import MAX_PAGE_LIMIT, PageRequest

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime
    from typing import TextIO

    from omym2.domain.models.file_event import FileEvent
    from omym2.domain.models.run import Run
    from omym2.features.history.ports import HistoryPorts

ERROR_EXIT_CODE = 1
HISTORY_USAGE_MESSAGE = "Usage: omym2 history [RUN_ID]"
INVALID_RUN_ID_MESSAGE = "Invalid Run ID."
NO_RUNS_MESSAGE = "No runs."
SUCCESS_EXIT_CODE = 0
USAGE_EXIT_CODE = 2


def run_history_command(
    args: Sequence[str],
    stdout: TextIO,
    stderr: TextIO,
    ports: HistoryPorts,
) -> int:
    """Run history and return a process exit code."""
    if len(args) > 1 or (len(args) == 1 and args[0].startswith("-")):
        write_usage(stderr, HISTORY_USAGE_MESSAGE)
        return USAGE_EXIT_CODE
    if len(args) == 1:
        return _run_history_detail(args[0], stdout, stderr, ports)

    runs = _fetch_runs(ports)

    if len(runs) == 0:
        write_line(stdout, NO_RUNS_MESSAGE)
        return SUCCESS_EXIT_CODE

    for run in runs:
        _write_run_row(stdout, run)
    return SUCCESS_EXIT_CODE


def _fetch_runs(ports: HistoryPorts) -> tuple[Run, ...]:
    """Return every Run with no filter, walking all keyset pages.

    `history` has no `--limit` option, so every page is walked at
    `MAX_PAGE_LIMIT` to keep the CLI's unlimited-by-default output from
    being silently truncated at the Web API's per-page cap.
    """
    usecase = ListRunsUseCase(ports)
    runs: list[Run] = []
    cursor: tuple[str, ...] | None = None
    while True:
        page = usecase.execute(ListRunsRequest(page=PageRequest(limit=MAX_PAGE_LIMIT, cursor_key=cursor)))
        runs.extend(page.items)
        if page.next_cursor_key is None:
            return tuple(runs)
        cursor = page.next_cursor_key


def _run_history_detail(
    raw_run_id: str,
    stdout: TextIO,
    stderr: TextIO,
    ports: HistoryPorts,
) -> int:
    """Write one Run and all of its durable FileEvents."""
    try:
        run_id = RunId(parse_uuid(raw_run_id))
    except ValueError:
        write_line(stderr, INVALID_RUN_ID_MESSAGE)
        return ERROR_EXIT_CODE

    try:
        run = GetRunDetailUseCase(ports).execute(GetRunDetailRequest(run_id)).run
        events = _fetch_run_events(ports, run_id)
    except RunNotFoundError as exc:
        write_line(stderr, str(exc))
        return ERROR_EXIT_CODE

    _write_run_detail(stdout, run, events)
    return SUCCESS_EXIT_CODE


def _fetch_run_events(ports: HistoryPorts, run_id: RunId) -> tuple[FileEvent, ...]:
    """Return every FileEvent for one Run, walking all keyset pages."""
    usecase = ListRunEventsUseCase(ports)
    events: list[FileEvent] = []
    cursor: tuple[str, ...] | None = None
    while True:
        page = usecase.execute(
            ListRunEventsRequest(
                run_id=run_id,
                page=PageRequest(limit=MAX_PAGE_LIMIT, cursor_key=cursor),
            ),
        )
        events.extend(page.items)
        if page.next_cursor_key is None:
            return tuple(events)
        cursor = page.next_cursor_key


def _write_run_row(stdout: TextIO, run: Run) -> None:
    completed_at = "-" if run.completed_at is None else run.completed_at.isoformat()
    row = (
        f"{run.run_id} plan={run.plan_id} library={run.library_id} status={run.status.value} "
        f"started_at={run.started_at.isoformat()} completed_at={completed_at}\n"
    )
    _ = stdout.write(row)


def _write_run_detail(stdout: TextIO, run: Run, events: tuple[FileEvent, ...]) -> None:
    """Write one Run header followed by its recorded mutation evidence."""
    _ = stdout.write(f"run_id: {run.run_id}\n")
    _ = stdout.write(f"plan_id: {run.plan_id}\n")
    _ = stdout.write(f"library_id: {run.library_id}\n")
    _ = stdout.write(f"status: {run.status.value}\n")
    _ = stdout.write(f"started_at: {run.started_at.isoformat()}\n")
    _ = stdout.write(f"completed_at: {_optional_timestamp(run.completed_at)}\n")
    _ = stdout.write(f"error_summary: {_optional(run.error_summary)}\n")
    _ = stdout.write(f"file_events: {len(events)}\n")
    for event in events:
        _write_file_event(stdout, event)


def _write_file_event(stdout: TextIO, event: FileEvent) -> None:
    """Write one durable FileEvent without deriving a recovery outcome."""
    _ = stdout.write(f"  - event_id: {event.event_id}\n")
    _ = stdout.write(f"    library_id: {event.library_id}\n")
    _ = stdout.write(f"    run_id: {event.run_id}\n")
    _ = stdout.write(f"    sequence_no: {event.sequence_no}\n")
    _ = stdout.write(f"    plan_action_id: {event.plan_action_id}\n")
    _ = stdout.write(f"    event_type: {event.event_type.value}\n")
    _ = stdout.write(f"    status: {event.status.value}\n")
    _ = stdout.write(f"    companion_asset_id: {_optional_id(event.companion_asset_id)}\n")
    _ = stdout.write(f"    source_path: {event.source_path}\n")
    _ = stdout.write(f"    target_path: {event.target_path}\n")
    _ = stdout.write(f"    started_at: {event.started_at.isoformat()}\n")
    _ = stdout.write(f"    completed_at: {_optional_timestamp(event.completed_at)}\n")
    _ = stdout.write(f"    error_code: {_optional(event.error_code)}\n")
    _ = stdout.write(f"    error_message: {_optional(event.error_message)}\n")


def _optional(value: str | None) -> str:
    return "-" if value is None else value


def _optional_id(value: object | None) -> str:
    return "-" if value is None else str(value)


def _optional_timestamp(value: datetime | None) -> str:
    return "-" if value is None else value.isoformat()
