"""
Summary: Tests typed Plan inspection and ready-Plan cancellation Web APIs.
Why: Verifies Plan browsing plus lock-protected synchronous Cancel behavior.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast
from uuid import UUID

from fastapi.testclient import TestClient

from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.config import (
    HTTP_CONFLICT_STATUS,
    HTTP_FORBIDDEN_STATUS,
    HTTP_NOT_FOUND_STATUS,
    HTTP_OK_STATUS,
    HTTP_UNPROCESSABLE_CONTENT_STATUS,
    WEB_API_BOOTSTRAP_ROUTE,
    WEB_API_CANCEL_PLAN_ROUTE,
    WEB_API_PLAN_ACTIONS_ROUTE,
    WEB_API_PLAN_DETAIL_ROUTE,
    WEB_API_PLAN_FACETS_ROUTE,
    WEB_API_PLAN_GROUPS_ROUTE,
    WEB_API_PLANS_ROUTE,
    WEB_CSRF_HEADER_NAME,
)
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction, PlanActionReason
from omym2.platform.web_composition import build_web_app
from omym2.shared.ids import ActionId, LibraryId, PlanId
from omym2.shared.pagination import MAX_PAGE_LIMIT

if TYPE_CHECKING:
    from pathlib import Path

    from httpx2 import Response

NOW = datetime(2026, 7, 13, tzinfo=UTC)
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345670"))
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345671"))
SECOND_PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345672"))
MISSING_PLAN_ID = "018f6a4f-3c2d-7b8a-9abc-def012345679"
ACTION_ID_1 = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345673"))
ACTION_ID_2 = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345674"))
ACTION_ID_3 = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345675"))
ONE_ITEM_LIMIT = 1
PLAN_ACTION_TOTAL = 3
GROUPED_ACTION_TOTAL = 2


def test_list_plans_uses_current_typed_action_summaries_and_blocked_actions(tmp_path: Path) -> None:
    """List rows replace opaque summaries and blocked filtering uses recorded action state."""
    client = _seeded_client(tmp_path)

    response = client.get(WEB_API_PLANS_ROUTE, params={"blocked": "true"})

    assert response.status_code == HTTP_OK_STATUS
    data = _data(response)
    items = _items(data)
    page = _object(data, "page")
    assert [item["plan_id"] for item in items] == [str(PLAN_ID)]
    assert page == {"limit": 100, "next_cursor": None, "total": 1}
    summary = _object(items[0], "summary")
    assert summary == {
        "total": PLAN_ACTION_TOTAL,
        "counts": {
            "planned": {"move": 1, "skip": 0, "refresh_metadata": 0},
            "blocked": {"move": 0, "skip": 1, "refresh_metadata": 0},
            "applied": {"move": 0, "skip": 0, "refresh_metadata": 1},
            "failed": {"move": 0, "skip": 0, "refresh_metadata": 0},
        },
    }


def test_list_plans_paginates_with_an_opaque_cursor_and_clamps_limit(tmp_path: Path) -> None:
    """Plan list pagination uses the returned cursor and applies the shared maximum limit."""
    client = _seeded_client(tmp_path)

    first = client.get(WEB_API_PLANS_ROUTE, params={"limit": ONE_ITEM_LIMIT})
    first_data = _data(first)
    first_page = _object(first_data, "page")
    cursor = first_page["next_cursor"]
    assert isinstance(cursor, str)
    second = client.get(WEB_API_PLANS_ROUTE, params={"limit": ONE_ITEM_LIMIT, "cursor": cursor})
    clamped = client.get(WEB_API_PLANS_ROUTE, params={"limit": MAX_PAGE_LIMIT + 1})

    assert first.status_code == HTTP_OK_STATUS
    assert [item["plan_id"] for item in _items(first_data)] == [str(SECOND_PLAN_ID)]
    assert second.status_code == HTTP_OK_STATUS
    assert [item["plan_id"] for item in _items(_data(second))] == [str(PLAN_ID)]
    assert _object(_data(second), "page")["next_cursor"] is None
    assert clamped.status_code == HTTP_OK_STATUS
    assert _object(_data(clamped), "page")["limit"] == MAX_PAGE_LIMIT


def test_plan_actions_facets_and_groups_apply_filters_without_storage_access_in_routes(tmp_path: Path) -> None:
    """Child inspection routes project stored actions through their feature query handlers."""
    client = _seeded_client(tmp_path)

    actions = client.get(
        WEB_API_PLAN_ACTIONS_ROUTE.format(plan_id=PLAN_ID),
        params={"group_by": "target_directory", "group_key": "Artist/Album"},
    )
    facets = client.get(WEB_API_PLAN_FACETS_ROUTE.format(plan_id=PLAN_ID))
    groups = client.get(
        WEB_API_PLAN_GROUPS_ROUTE.format(plan_id=PLAN_ID),
        params={"group_by": "target_directory"},
    )

    assert actions.status_code == HTTP_OK_STATUS
    assert [item["action_id"] for item in _items(_data(actions))] == [str(ACTION_ID_1), str(ACTION_ID_2)]
    assert _object(_data(actions), "page")["total"] == GROUPED_ACTION_TOTAL
    assert facets.status_code == HTTP_OK_STATUS
    facet_data = _data(facets)
    assert _object(facet_data, "facets") == {
        "status": [
            {"value": "applied", "count": 1},
            {"value": "blocked", "count": 1},
            {"value": "planned", "count": 1},
        ],
        "action_type": [
            {"value": "move", "count": 1},
            {"value": "refresh_metadata", "count": 1},
            {"value": "skip", "count": 1},
        ],
        "reason": [{"value": "target_exists", "count": 1}],
    }
    assert facet_data["target_collisions"] == 1
    assert groups.status_code == HTTP_OK_STATUS
    group_items = _items(_data(groups))
    assert group_items[0] == {
        "key": "Artist/Album",
        "label": "Artist/Album",
        "count": 2,
        "blocked_count": 1,
        "top_reason": "target_exists",
    }


def test_plan_inspection_rejects_invalid_queries_and_returns_plan_specific_not_found(tmp_path: Path) -> None:
    """Malformed cursors, unpaired drill-down filters, and missing Plans keep typed error envelopes."""
    client = _seeded_client(tmp_path)

    invalid_cursor = client.get(WEB_API_PLANS_ROUTE, params={"cursor": "eyJhIl0"})
    documented_reason = client.get(
        WEB_API_PLAN_ACTIONS_ROUTE.format(plan_id=PLAN_ID),
        params={"reason": "operation_interrupted"},
    )
    unpaired_group = client.get(
        WEB_API_PLAN_ACTIONS_ROUTE.format(plan_id=PLAN_ID),
        params={"group_by": "status"},
    )
    missing_plan = client.get(WEB_API_PLAN_FACETS_ROUTE.format(plan_id=MISSING_PLAN_ID))

    assert invalid_cursor.status_code == HTTP_UNPROCESSABLE_CONTENT_STATUS
    assert _error(invalid_cursor)["field"] == "query.cursor"
    assert documented_reason.status_code == HTTP_OK_STATUS
    assert _items(_data(documented_reason)) == []
    assert unpaired_group.status_code == HTTP_UNPROCESSABLE_CONTENT_STATUS
    assert _error(unpaired_group)["field"] == "query.group_key"
    assert missing_plan.status_code == HTTP_NOT_FOUND_STATUS
    error = _error(missing_plan)
    assert error["code"] == "plan_not_found"
    assert error["field"] == "path.plan_id"


def test_ready_plan_cancel_requires_csrf_and_returns_terminal_detail(tmp_path: Path) -> None:
    """Cancel rejects missing CSRF before one lock-protected ready-to-cancelled transition."""
    client = _seeded_client(tmp_path)
    route = WEB_API_CANCEL_PLAN_ROUTE.format(plan_id=PLAN_ID)

    forbidden = client.post(route)
    before = client.get(WEB_API_PLAN_DETAIL_ROUTE.format(plan_id=PLAN_ID))
    csrf_token = _data(client.get(WEB_API_BOOTSTRAP_ROUTE))["csrf_token"]
    assert isinstance(csrf_token, str)
    cancelled = client.post(route, headers={WEB_CSRF_HEADER_NAME: csrf_token})
    repeated = client.post(route, headers={WEB_CSRF_HEADER_NAME: csrf_token})

    assert forbidden.status_code == HTTP_FORBIDDEN_STATUS
    assert _error(forbidden)["code"] == "csrf_invalid"
    assert _object(_data(before), "plan")["status"] == "ready"
    assert cancelled.status_code == HTTP_OK_STATUS
    cancelled_data = _data(cancelled)
    assert _object(cancelled_data, "plan")["status"] == "cancelled"
    assert _object(cancelled_data, "capabilities")["can_cancel"] is False
    assert cancelled_data["active_operation_id"] is None
    assert repeated.status_code == HTTP_CONFLICT_STATUS
    assert _error(repeated)["code"] == "plan_not_ready"


def _seeded_client(tmp_path: Path) -> TestClient:
    """Build a Web app with two Plans and recorded current action evidence."""
    database_path = tmp_path / "state.sqlite3"
    with SQLiteUnitOfWork(database_path) as uow:
        uow.libraries.save(
            Library(
                library_id=LIBRARY_ID,
                root_path="/music/library",
                path_policy_hash="path-policy-hash",
                registered_at=NOW,
                status=LibraryStatus.REGISTERED,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        uow.plans.save(
            Plan(
                plan_id=PLAN_ID,
                library_id=LIBRARY_ID,
                plan_type=PlanType.ADD,
                status=PlanStatus.READY,
                created_at=NOW,
                config_hash="config-hash",
                library_root_at_plan="/music/library",
                summary={"blocked_actions": "0"},
            )
        )
        uow.plans.save(
            Plan(
                plan_id=SECOND_PLAN_ID,
                library_id=LIBRARY_ID,
                plan_type=PlanType.ORGANIZE,
                status=PlanStatus.READY,
                created_at=NOW + timedelta(seconds=1),
                config_hash="config-hash",
                library_root_at_plan="/music/library",
                summary={"blocked_actions": "1"},
            )
        )
        uow.plan_actions.save(
            _action(
                ACTION_ID_1,
                action_type=ActionType.MOVE,
                status=ActionStatus.PLANNED,
                source_path="/incoming/one.flac",
                target_path="Artist/Album/Same.flac",
                sort_order=1,
            )
        )
        uow.plan_actions.save(
            _action(
                ACTION_ID_2,
                action_type=ActionType.SKIP,
                status=ActionStatus.BLOCKED,
                source_path="Artist/Album/two.flac",
                target_path="Artist/Album/Same.flac",
                reason=PlanActionReason.TARGET_EXISTS,
                sort_order=2,
            )
        )
        uow.plan_actions.save(
            _action(
                ACTION_ID_3,
                action_type=ActionType.REFRESH_METADATA,
                status=ActionStatus.APPLIED,
                source_path="Other/Album/three.flac",
                target_path="Other/Album/three.flac",
                sort_order=3,
            )
        )
        uow.commit()
    return TestClient(build_web_app(tmp_path / "config.toml", database_path), base_url="http://localhost")


def _action(  # noqa: PLR0913  # The fixture names every stored PlanAction field relevant to API projection.
    action_id: ActionId,
    *,
    action_type: ActionType,
    status: ActionStatus,
    source_path: str,
    target_path: str,
    sort_order: int,
    reason: PlanActionReason | None = None,
) -> PlanAction:
    """Build one stored action for the seeded Plan."""
    return PlanAction(
        action_id=action_id,
        plan_id=PLAN_ID,
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


def _data(response: Response) -> dict[str, object]:
    """Return a normal API envelope's typed data object."""
    payload = cast("dict[str, object]", response.json())
    assert payload["errors"] == []
    data = payload["data"]
    assert isinstance(data, dict)
    return cast("dict[str, object]", data)


def _items(data: dict[str, object]) -> list[dict[str, object]]:
    """Return one typed list response's JSON item objects."""
    value = data["items"]
    assert isinstance(value, list)
    items = cast("list[object]", value)
    assert all(isinstance(item, dict) for item in items)
    return [cast("dict[str, object]", item) for item in items]


def _object(data: dict[str, object], key: str) -> dict[str, object]:
    """Return a required JSON object field."""
    value = data[key]
    assert isinstance(value, dict)
    return cast("dict[str, object]", value)


def _error(response: Response) -> dict[str, object]:
    """Return the first typed failure envelope error."""
    payload = cast("dict[str, object]", response.json())
    errors = payload["errors"]
    assert isinstance(errors, list)
    typed_errors = cast("list[object]", errors)
    assert typed_errors
    error = typed_errors[0]
    assert isinstance(error, dict)
    return cast("dict[str, object]", error)
