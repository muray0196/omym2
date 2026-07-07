"""
Summary: Tests plans CLI list/detail flags, summary tallies, and diff rendering.
Why: Protects the pre-apply review command surface, exit codes, and text output.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from io import StringIO
from typing import TYPE_CHECKING, cast
from uuid import UUID

import pytest

from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction, PlanActionReason
from omym2.platform.cli_entry_point import run_cli as main
from omym2.shared.ids import ActionId, LibraryId, PlanId

if TYPE_CHECKING:
    from pathlib import Path

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CONFIG_HASH = "config-hash"
ERROR_EXIT_CODE = 1
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456a0"))
LIBRARY_ROOT = "/music/library"
SUCCESS_EXIT_CODE = 0
USAGE_EXIT_CODE = 2

PLAN_ID_1 = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456a1"))
PLAN_ID_2 = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456a2"))
PLAN_ID_3 = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456a3"))
UNKNOWN_PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456a4"))

ACTION_ID_1 = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456b1"))
ACTION_ID_2 = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456b2"))
ACTION_ID_3 = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456b3"))
ACTION_ID_4 = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def0123456b4"))


def test_plans_list_filters_by_status(tmp_path: Path) -> None:
    """--status only lists Plans with the requested status."""
    database_file = _database_file(tmp_path)
    _seed(
        database_file,
        plans=(
            _plan(PLAN_ID_1, status=PlanStatus.READY, created_at=BASE_TIME),
            _plan(PLAN_ID_2, status=PlanStatus.FAILED, created_at=BASE_TIME + timedelta(days=1)),
        ),
    )
    stdout, stderr = StringIO(), StringIO()

    exit_code = main(["plans", "--status", "ready"], stdout=stdout, stderr=stderr, database_path=database_file)

    assert exit_code == SUCCESS_EXIT_CODE
    assert str(PLAN_ID_1) in stdout.getvalue()
    assert str(PLAN_ID_2) not in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_plans_list_filters_by_type(tmp_path: Path) -> None:
    """--type only lists Plans with the requested plan type."""
    database_file = _database_file(tmp_path)
    _seed(
        database_file,
        plans=(
            _plan(PLAN_ID_1, plan_type=PlanType.ADD, created_at=BASE_TIME),
            _plan(PLAN_ID_2, plan_type=PlanType.ORGANIZE, created_at=BASE_TIME + timedelta(days=1)),
        ),
    )
    stdout, stderr = StringIO(), StringIO()

    exit_code = main(["plans", "--type", "organize"], stdout=stdout, stderr=stderr, database_path=database_file)

    assert exit_code == SUCCESS_EXIT_CODE
    assert str(PLAN_ID_2) in stdout.getvalue()
    assert str(PLAN_ID_1) not in stdout.getvalue()


def test_plans_list_combined_status_and_type_filters(tmp_path: Path) -> None:
    """--status and --type combine as an AND filter."""
    database_file = _database_file(tmp_path)
    _seed(
        database_file,
        plans=(
            _plan(PLAN_ID_1, status=PlanStatus.READY, plan_type=PlanType.ADD, created_at=BASE_TIME),
            _plan(
                PLAN_ID_2,
                status=PlanStatus.READY,
                plan_type=PlanType.ORGANIZE,
                created_at=BASE_TIME + timedelta(days=1),
            ),
            _plan(
                PLAN_ID_3,
                status=PlanStatus.FAILED,
                plan_type=PlanType.ORGANIZE,
                created_at=BASE_TIME + timedelta(days=2),
            ),
        ),
    )
    stdout, stderr = StringIO(), StringIO()

    exit_code = main(
        ["plans", "--status", "ready", "--type", "organize"],
        stdout=stdout,
        stderr=stderr,
        database_path=database_file,
    )

    assert exit_code == SUCCESS_EXIT_CODE
    assert str(PLAN_ID_2) in stdout.getvalue()
    assert str(PLAN_ID_1) not in stdout.getvalue()
    assert str(PLAN_ID_3) not in stdout.getvalue()


def test_plans_list_limit_returns_newest_plans(tmp_path: Path) -> None:
    """--limit keeps only the newest Plans after sorting."""
    database_file = _database_file(tmp_path)
    _seed(
        database_file,
        plans=(
            _plan(PLAN_ID_1, created_at=BASE_TIME),
            _plan(PLAN_ID_2, created_at=BASE_TIME + timedelta(days=1)),
            _plan(PLAN_ID_3, created_at=BASE_TIME + timedelta(days=2)),
        ),
    )
    stdout, stderr = StringIO(), StringIO()

    exit_code = main(["plans", "--limit", "2"], stdout=stdout, stderr=stderr, database_path=database_file)

    assert exit_code == SUCCESS_EXIT_CODE
    assert str(PLAN_ID_3) in stdout.getvalue()
    assert str(PLAN_ID_2) in stdout.getvalue()
    assert str(PLAN_ID_1) not in stdout.getvalue()


def test_plans_list_orders_newest_first(tmp_path: Path) -> None:
    """List output shows the newest Plan on the first row."""
    database_file = _database_file(tmp_path)
    _seed(
        database_file,
        plans=(
            _plan(PLAN_ID_1, created_at=BASE_TIME),
            _plan(PLAN_ID_2, created_at=BASE_TIME + timedelta(days=1)),
        ),
    )
    stdout, stderr = StringIO(), StringIO()

    exit_code = main(["plans"], stdout=stdout, stderr=stderr, database_path=database_file)

    assert exit_code == SUCCESS_EXIT_CODE
    output = stdout.getvalue()
    assert output.index(str(PLAN_ID_2)) < output.index(str(PLAN_ID_1))


def test_plans_list_empty_database_reports_no_plans(tmp_path: Path) -> None:
    """An unfiltered empty listing prints the plain empty message."""
    database_file = _database_file(tmp_path)
    stdout, stderr = StringIO(), StringIO()

    exit_code = main(["plans"], stdout=stdout, stderr=stderr, database_path=database_file)

    assert exit_code == SUCCESS_EXIT_CODE
    assert stdout.getvalue() == "No plans.\n"
    assert stderr.getvalue() == ""


def test_plans_list_filtered_to_empty_reports_no_matching_plans(tmp_path: Path) -> None:
    """A filtered listing with zero matches prints the filter empty message."""
    database_file = _database_file(tmp_path)
    _seed(database_file, plans=(_plan(PLAN_ID_1, status=PlanStatus.READY, created_at=BASE_TIME),))
    stdout, stderr = StringIO(), StringIO()

    exit_code = main(["plans", "--status", "failed"], stdout=stdout, stderr=stderr, database_path=database_file)

    assert exit_code == SUCCESS_EXIT_CODE
    assert stdout.getvalue() == "No plans match filter.\n"


@pytest.mark.parametrize(
    "args",
    [
        ["plans", "--status", "nonsense"],
        ["plans", "--type", "nonsense"],
        ["plans", "--limit", "abc"],
        ["plans", "--limit", "0"],
        ["plans", "--limit", "-1"],
        ["plans", "--status", "ready", "--status", "failed"],
        ["plans", "--status"],
        ["plans", "--frobnicate"],
        ["plans", "--json", "stray-positional"],
    ],
)
def test_plans_list_usage_errors(args: list[str]) -> None:
    """Invalid list flags fail with the list usage message and exit 2."""
    stdout, stderr = StringIO(), StringIO()

    exit_code = main(args, stdout=stdout, stderr=stderr)

    assert exit_code == USAGE_EXIT_CODE
    assert stdout.getvalue() == ""
    assert "Usage: omym2 plans [--status STATUS]" in stderr.getvalue()


def test_plans_detail_invalid_plan_id_reports_error() -> None:
    """A malformed Plan ID fails with exit 1 on stderr, not a usage error."""
    stdout, stderr = StringIO(), StringIO()

    exit_code = main(["plans", "not-a-plan"], stdout=stdout, stderr=stderr)

    assert exit_code == ERROR_EXIT_CODE
    assert stdout.getvalue() == ""
    assert "Invalid Plan ID." in stderr.getvalue()


def test_plans_detail_unknown_plan_id_reports_not_found(tmp_path: Path) -> None:
    """A well-formed but unknown Plan ID fails with exit 1 on stderr."""
    database_file = _database_file(tmp_path)
    stdout, stderr = StringIO(), StringIO()

    exit_code = main(["plans", str(UNKNOWN_PLAN_ID)], stdout=stdout, stderr=stderr, database_path=database_file)

    assert exit_code == ERROR_EXIT_CODE
    assert stdout.getvalue() == ""
    assert "Plan was not found." in stderr.getvalue()


def test_plans_detail_blocked_only_shows_only_blocked_actions(tmp_path: Path) -> None:
    """--blocked-only lists blocked actions and hides other statuses."""
    database_file = _database_file(tmp_path)
    _seed_mixed_action_plan(database_file)
    stdout, stderr = StringIO(), StringIO()

    exit_code = main(
        ["plans", str(PLAN_ID_1), "--blocked-only"],
        stdout=stdout,
        stderr=stderr,
        database_path=database_file,
    )

    assert exit_code == SUCCESS_EXIT_CODE
    output = stdout.getvalue()
    assert str(ACTION_ID_2) in output
    assert str(ACTION_ID_1) not in output
    assert str(ACTION_ID_3) not in output


def test_plans_detail_actions_failed_shows_only_failed_actions(tmp_path: Path) -> None:
    """--actions failed lists failed actions and hides other statuses."""
    database_file = _database_file(tmp_path)
    _seed_mixed_action_plan(database_file)
    stdout, stderr = StringIO(), StringIO()

    exit_code = main(
        ["plans", str(PLAN_ID_1), "--actions", "failed"],
        stdout=stdout,
        stderr=stderr,
        database_path=database_file,
    )

    assert exit_code == SUCCESS_EXIT_CODE
    output = stdout.getvalue()
    assert str(ACTION_ID_3) in output
    assert str(ACTION_ID_1) not in output
    assert str(ACTION_ID_2) not in output


def test_plans_detail_filter_to_empty_reports_no_matching_actions(tmp_path: Path) -> None:
    """A filter matching zero actions replaces the actions block with a message."""
    database_file = _database_file(tmp_path)
    _seed(
        database_file,
        plans=(_plan(PLAN_ID_1, created_at=BASE_TIME),),
        actions=(_action(ACTION_ID_1, status=ActionStatus.PLANNED, sort_order=0),),
    )
    stdout, stderr = StringIO(), StringIO()

    exit_code = main(
        ["plans", str(PLAN_ID_1), "--actions", "applied"],
        stdout=stdout,
        stderr=stderr,
        database_path=database_file,
    )

    assert exit_code == SUCCESS_EXIT_CODE
    output = stdout.getvalue()
    assert "No actions match filter." in output
    assert "actions:" not in output
    assert f"plan_id: {PLAN_ID_1}" in output


@pytest.mark.parametrize(
    "extra_args",
    [
        ["--actions", "blocked", "--blocked-only"],
        ["--summary", "--actions", "planned"],
        ["--summary", "--blocked-only"],
        ["--summary", "--diff"],
        ["--actions"],
        ["--actions", "nonsense"],
        ["--frobnicate"],
        ["stray-positional"],
        ["--json", "--summary"],
        ["--json", "--diff"],
    ],
)
def test_plans_detail_usage_errors(extra_args: list[str]) -> None:
    """Invalid detail flag combinations fail with the detail usage message."""
    stdout, stderr = StringIO(), StringIO()

    exit_code = main(["plans", str(PLAN_ID_1), *extra_args], stdout=stdout, stderr=stderr)

    assert exit_code == USAGE_EXIT_CODE
    assert stdout.getvalue() == ""
    assert "Usage: omym2 plans <PLAN_ID>" in stderr.getvalue()


def test_plans_detail_summary_tallies_live_action_counts(tmp_path: Path) -> None:
    """--summary tallies live action statuses and types with zero rows included."""
    database_file = _database_file(tmp_path)
    _seed(
        database_file,
        plans=(_plan(PLAN_ID_1, created_at=BASE_TIME, summary={"action_count": "3"}),),
        actions=(
            _action(ACTION_ID_1, status=ActionStatus.PLANNED, sort_order=0),
            _action(
                ACTION_ID_2,
                status=ActionStatus.BLOCKED,
                sort_order=1,
                reason=PlanActionReason.TARGET_EXISTS,
            ),
            _action(ACTION_ID_3, status=ActionStatus.PLANNED, sort_order=2, action_type=ActionType.SKIP),
        ),
    )
    stdout, stderr = StringIO(), StringIO()

    exit_code = main(
        ["plans", str(PLAN_ID_1), "--summary"],
        stdout=stdout,
        stderr=stderr,
        database_path=database_file,
    )

    assert exit_code == SUCCESS_EXIT_CODE
    output = stdout.getvalue()
    expected_status_block = "action_status_counts:\n  planned: 2\n  blocked: 1\n  applied: 0\n  failed: 0\n"
    expected_type_block = "action_type_counts:\n  move: 2\n  skip: 1\n  refresh_metadata: 0\n"
    assert expected_status_block in output
    assert expected_type_block in output
    assert "summary:\n  action_count: 3\n" in output
    assert "action_id" not in output


def test_plans_detail_diff_renders_path_shape_matrix(tmp_path: Path) -> None:
    """--diff renders arrow lines, reason markers, dash paths, and no-change lines."""
    database_file = _database_file(tmp_path)
    _seed(
        database_file,
        plans=(_plan(PLAN_ID_1, created_at=BASE_TIME),),
        actions=(
            _action(
                ACTION_ID_1,
                status=ActionStatus.PLANNED,
                sort_order=0,
                source_path="/music/incoming/a.flac",
                target_path="Artist/A.flac",
            ),
            _action(
                ACTION_ID_2,
                status=ActionStatus.BLOCKED,
                sort_order=1,
                reason=PlanActionReason.TARGET_EXISTS,
                source_path="/music/incoming/b.flac",
                target_path="Artist/B.flac",
            ),
            _action(
                ACTION_ID_3,
                status=ActionStatus.PLANNED,
                sort_order=2,
                action_type=ActionType.SKIP,
                reason=PlanActionReason.DUPLICATE_HASH,
                source_path=None,
                target_path=None,
            ),
            _action(
                ACTION_ID_4,
                status=ActionStatus.PLANNED,
                sort_order=3,
                action_type=ActionType.REFRESH_METADATA,
                source_path="Artist/C.flac",
                target_path="Artist/C.flac",
            ),
        ),
    )
    stdout, stderr = StringIO(), StringIO()

    exit_code = main(
        ["plans", str(PLAN_ID_1), "--diff"],
        stdout=stdout,
        stderr=stderr,
        database_path=database_file,
    )

    assert exit_code == SUCCESS_EXIT_CODE
    output = stdout.getvalue()
    expected_diff_block = (
        "diff:\n"
        "  [move|planned] /music/incoming/a.flac -> Artist/A.flac\n"
        "  [move|blocked:target_exists] /music/incoming/b.flac -> Artist/B.flac\n"
        "  [skip|planned:duplicate_hash] - -> -\n"
        "  [refresh_metadata|planned] Artist/C.flac (no path change)\n"
    )
    assert expected_diff_block in output
    assert f"plan_id: {PLAN_ID_1}" in output


def test_plans_detail_diff_with_blocked_only_shows_only_blocked_lines(tmp_path: Path) -> None:
    """--diff --blocked-only renders diff lines only for blocked actions."""
    database_file = _database_file(tmp_path)
    _seed(
        database_file,
        plans=(_plan(PLAN_ID_1, created_at=BASE_TIME),),
        actions=(
            _action(
                ACTION_ID_1,
                status=ActionStatus.PLANNED,
                sort_order=0,
                source_path="/music/incoming/a.flac",
                target_path="Artist/A.flac",
            ),
            _action(
                ACTION_ID_2,
                status=ActionStatus.BLOCKED,
                sort_order=1,
                reason=PlanActionReason.TARGET_EXISTS,
                source_path="/music/incoming/b.flac",
                target_path="Artist/B.flac",
            ),
        ),
    )
    stdout, stderr = StringIO(), StringIO()

    exit_code = main(
        ["plans", str(PLAN_ID_1), "--diff", "--blocked-only"],
        stdout=stdout,
        stderr=stderr,
        database_path=database_file,
    )

    assert exit_code == SUCCESS_EXIT_CODE
    output = stdout.getvalue()
    assert "[move|blocked:target_exists] /music/incoming/b.flac -> Artist/B.flac" in output
    assert "a.flac" not in output


def test_plans_list_json_empty_database_emits_empty_plans_array(tmp_path: Path) -> None:
    """--json on an empty database emits a parseable empty payload, not text."""
    database_file = _database_file(tmp_path)
    stdout, stderr = StringIO(), StringIO()

    exit_code = main(["plans", "--json"], stdout=stdout, stderr=stderr, database_path=database_file)

    assert exit_code == SUCCESS_EXIT_CODE
    assert _json_payload(stdout.getvalue()) == {"plans": []}
    assert stderr.getvalue() == ""


def test_plans_list_json_with_status_filter_emits_matching_rows(tmp_path: Path) -> None:
    """--status --json emits exactly the filtered Plan rows."""
    database_file = _database_file(tmp_path)
    _seed(
        database_file,
        plans=(
            _plan(PLAN_ID_1, status=PlanStatus.READY, created_at=BASE_TIME, summary={"action_count": "1"}),
            _plan(PLAN_ID_2, status=PlanStatus.FAILED, created_at=BASE_TIME + timedelta(days=1)),
        ),
    )
    stdout, stderr = StringIO(), StringIO()

    exit_code = main(
        ["plans", "--status", "ready", "--json"],
        stdout=stdout,
        stderr=stderr,
        database_path=database_file,
    )

    assert exit_code == SUCCESS_EXIT_CODE
    assert _json_payload(stdout.getvalue()) == {
        "plans": [
            {
                "plan_id": str(PLAN_ID_1),
                "library_id": str(LIBRARY_ID),
                "plan_type": "add",
                "status": "ready",
                "created_at": BASE_TIME.isoformat(),
                "summary": {"action_count": "1"},
            }
        ]
    }


def test_plans_list_json_combines_with_limit(tmp_path: Path) -> None:
    """--limit --json emits only the newest rows as JSON."""
    database_file = _database_file(tmp_path)
    _seed(
        database_file,
        plans=(
            _plan(PLAN_ID_1, created_at=BASE_TIME),
            _plan(PLAN_ID_2, created_at=BASE_TIME + timedelta(days=1)),
        ),
    )
    stdout, stderr = StringIO(), StringIO()

    exit_code = main(
        ["plans", "--limit", "1", "--json"],
        stdout=stdout,
        stderr=stderr,
        database_path=database_file,
    )

    assert exit_code == SUCCESS_EXIT_CODE
    assert _json_payload(stdout.getvalue()) == {
        "plans": [
            {
                "plan_id": str(PLAN_ID_2),
                "library_id": str(LIBRARY_ID),
                "plan_type": "add",
                "status": "ready",
                "created_at": (BASE_TIME + timedelta(days=1)).isoformat(),
                "summary": {},
            }
        ]
    }


def test_plans_detail_json_emits_full_payload_with_null_fields(tmp_path: Path) -> None:
    """Detail --json emits header, actions with real nulls, and the total count."""
    database_file = _database_file(tmp_path)
    _seed(
        database_file,
        plans=(_plan(PLAN_ID_1, created_at=BASE_TIME, summary={"action_count": "2"}),),
        actions=(
            _action(
                ACTION_ID_1,
                status=ActionStatus.PLANNED,
                sort_order=0,
                source_path="/music/incoming/a.flac",
                target_path="Artist/A.flac",
            ),
            _action(
                ACTION_ID_2,
                status=ActionStatus.PLANNED,
                sort_order=1,
                action_type=ActionType.SKIP,
                source_path=None,
                target_path=None,
            ),
        ),
    )
    stdout, stderr = StringIO(), StringIO()

    exit_code = main(
        ["plans", str(PLAN_ID_1), "--json"],
        stdout=stdout,
        stderr=stderr,
        database_path=database_file,
    )

    assert exit_code == SUCCESS_EXIT_CODE
    assert _json_payload(stdout.getvalue()) == {
        "plan": {
            "plan_id": str(PLAN_ID_1),
            "library_id": str(LIBRARY_ID),
            "plan_type": "add",
            "status": "ready",
            "created_at": BASE_TIME.isoformat(),
            "summary": {"action_count": "2"},
            "config_hash": CONFIG_HASH,
            "library_root_at_plan": LIBRARY_ROOT,
        },
        "actions": [
            {
                "action_id": str(ACTION_ID_1),
                "plan_id": str(PLAN_ID_1),
                "library_id": str(LIBRARY_ID),
                "track_id": None,
                "action_type": "move",
                "source_path": "/music/incoming/a.flac",
                "target_path": "Artist/A.flac",
                "content_hash_at_plan": None,
                "metadata_hash_at_plan": None,
                "status": "planned",
                "reason": None,
                "sort_order": 0,
            },
            {
                "action_id": str(ACTION_ID_2),
                "plan_id": str(PLAN_ID_1),
                "library_id": str(LIBRARY_ID),
                "track_id": None,
                "action_type": "skip",
                "source_path": None,
                "target_path": None,
                "content_hash_at_plan": None,
                "metadata_hash_at_plan": None,
                "status": "planned",
                "reason": None,
                "sort_order": 1,
            },
        ],
        "total_action_count": 2,
    }


def test_plans_detail_json_blocked_only_filters_actions_and_keeps_total(tmp_path: Path) -> None:
    """--blocked-only --json filters the actions array but not total_action_count."""
    database_file = _database_file(tmp_path)
    _seed_mixed_action_plan(database_file)
    stdout, stderr = StringIO(), StringIO()

    exit_code = main(
        ["plans", str(PLAN_ID_1), "--blocked-only", "--json"],
        stdout=stdout,
        stderr=stderr,
        database_path=database_file,
    )

    assert exit_code == SUCCESS_EXIT_CODE
    assert _json_payload(stdout.getvalue()) == {
        "plan": {
            "plan_id": str(PLAN_ID_1),
            "library_id": str(LIBRARY_ID),
            "plan_type": "add",
            "status": "ready",
            "created_at": BASE_TIME.isoformat(),
            "summary": {},
            "config_hash": CONFIG_HASH,
            "library_root_at_plan": LIBRARY_ROOT,
        },
        "actions": [
            {
                "action_id": str(ACTION_ID_2),
                "plan_id": str(PLAN_ID_1),
                "library_id": str(LIBRARY_ID),
                "track_id": None,
                "action_type": "move",
                "source_path": "Source/Track.flac",
                "target_path": "Target/Track.flac",
                "content_hash_at_plan": None,
                "metadata_hash_at_plan": None,
                "status": "blocked",
                "reason": "target_exists",
                "sort_order": 1,
            }
        ],
        "total_action_count": 3,
    }


def test_plans_detail_json_invalid_plan_id_keeps_stdout_empty() -> None:
    """--json never redirects errors to stdout: invalid IDs stay on stderr."""
    stdout, stderr = StringIO(), StringIO()

    exit_code = main(["plans", "not-a-plan", "--json"], stdout=stdout, stderr=stderr)

    assert exit_code == ERROR_EXIT_CODE
    assert stdout.getvalue() == ""
    assert "Invalid Plan ID." in stderr.getvalue()


def test_plans_detail_json_unknown_plan_id_keeps_stdout_empty(tmp_path: Path) -> None:
    """--json never redirects errors to stdout: unknown IDs stay on stderr."""
    database_file = _database_file(tmp_path)
    stdout, stderr = StringIO(), StringIO()

    exit_code = main(
        ["plans", str(UNKNOWN_PLAN_ID), "--json"],
        stdout=stdout,
        stderr=stderr,
        database_path=database_file,
    )

    assert exit_code == ERROR_EXIT_CODE
    assert stdout.getvalue() == ""
    assert "Plan was not found." in stderr.getvalue()


def _json_payload(raw_text: str) -> dict[str, object]:
    return cast("dict[str, object]", json.loads(raw_text))


def _database_file(tmp_path: Path) -> Path:
    return default_application_paths(tmp_path).database_file


def _seed(
    database_file: Path,
    *,
    plans: tuple[Plan, ...] = (),
    actions: tuple[PlanAction, ...] = (),
) -> None:
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library())
        for plan in plans:
            uow.plans.save(plan)
        for action in actions:
            uow.plan_actions.save(action)
        uow.commit()


def _seed_mixed_action_plan(database_file: Path) -> None:
    _seed(
        database_file,
        plans=(_plan(PLAN_ID_1, created_at=BASE_TIME),),
        actions=(
            _action(ACTION_ID_1, status=ActionStatus.PLANNED, sort_order=0),
            _action(
                ACTION_ID_2,
                status=ActionStatus.BLOCKED,
                sort_order=1,
                reason=PlanActionReason.TARGET_EXISTS,
            ),
            _action(ACTION_ID_3, status=ActionStatus.FAILED, sort_order=2),
        ),
    )


def _library() -> Library:
    return Library(
        library_id=LIBRARY_ID,
        root_path=LIBRARY_ROOT,
        path_policy_hash="path-policy",
        registered_at=BASE_TIME,
        status=LibraryStatus.REGISTERED,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _plan(
    plan_id: PlanId,
    *,
    created_at: datetime,
    status: PlanStatus = PlanStatus.READY,
    plan_type: PlanType = PlanType.ADD,
    summary: dict[str, str] | None = None,
) -> Plan:
    return Plan(
        plan_id=plan_id,
        library_id=LIBRARY_ID,
        plan_type=plan_type,
        status=status,
        created_at=created_at,
        config_hash=CONFIG_HASH,
        library_root_at_plan=LIBRARY_ROOT,
        summary={} if summary is None else summary,
    )


def _action(  # noqa: PLR0913 - test fixture spans the full diff/summary action variation matrix.
    action_id: ActionId,
    *,
    status: ActionStatus,
    sort_order: int,
    action_type: ActionType = ActionType.MOVE,
    reason: PlanActionReason | None = None,
    source_path: str | None = "Source/Track.flac",
    target_path: str | None = "Target/Track.flac",
) -> PlanAction:
    return PlanAction(
        action_id=action_id,
        plan_id=PLAN_ID_1,
        library_id=LIBRARY_ID,
        track_id=None,
        action_type=action_type,
        source_path=source_path,
        target_path=target_path,
        content_hash_at_plan=None,
        metadata_hash_at_plan=None,
        status=status,
        reason=reason,
        sort_order=sort_order,
    )
