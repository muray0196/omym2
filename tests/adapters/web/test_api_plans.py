"""
Summary: Tests Web Plan review JSON API routes.
Why: Verifies browser Plan creation plus paged Plan/action browsing, facets, and groups.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast
from uuid import UUID

from fastapi.testclient import TestClient

from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.config.toml_config_store import TomlConfigStore
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.adapters.metadata.mutagen_reader import MutagenMetadataReader
from omym2.config import (
    ALBUM_YEAR_RESOLUTION_OLDEST,
    CONFIG_FILE_ENCODING,
    WEB_API_PLAN_ADD_ROUTE,
    WEB_API_PLAN_ORGANIZE_ROUTE,
    WEB_API_PLAN_REFRESH_ROUTE,
    WEB_API_PLANS_ROUTE,
    WEB_API_SETTINGS_ROUTE,
    WEB_CSRF_HEADER_NAME,
)
from omym2.domain.models.app_config import AppConfig, MetadataConfig, PathsConfig
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction, PlanActionReason
from omym2.domain.models.track import Track, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.config_fingerprint import calculate_config_fingerprint, calculate_path_policy_fingerprint
from omym2.domain.services.content_fingerprint import calculate_content_fingerprint
from omym2.domain.services.metadata_fingerprint import calculate_metadata_fingerprint
from omym2.platform.web_composition import build_web_app as create_web_app
from omym2.shared.ids import ActionId, LibraryId, PlanId, TrackId
from omym2.shared.pagination import MAX_PAGE_LIMIT

if TYPE_CHECKING:
    import pytest

    from omym2.features.common_ports import FileSystemPath

ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567b"))
AUDIO_CONTENT = b"fake audio bytes"
BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
BLOCKED_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567c"))
CONTENT_HASH = calculate_content_fingerprint(AUDIO_CONTENT)
ERROR_STATUS_CODE = 400
FORBIDDEN_STATUS_CODE = 403
INVALID_PLAN_ID_TEXT = "not-a-uuid"
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
MISSING_PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345699"))
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567a"))
SECOND_PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567d"))
THIRD_PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567e"))
THIRD_ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def01234567f"))
SUCCESS_STATUS_CODE = 200
NOT_FOUND_STATUS_CODE = 404
SEEDED_ACTION_COUNT = 2
SEEDED_PLAN_COUNT = 3
TARGET_PATH = "Artist/2026_Album/1-02_Title.flac"
TARGET_DIRECTORY = "Artist/2026_Album"
ROOT_GROUP_LABEL = "(root)"
TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345679"))
ONE_ITEM_LIMIT = 1
CLAMPED_LIMIT_REQUEST = 1000

ADD_OLD_TARGET = "Artist/1998_Album/1-01_Old-Title.flac"
ADD_NEW_TARGET = "Artist/1998_Album/1-02_New-Title.flac"
ORGANIZE_TARGET = "Artist/2026_Album/1-03_Loose-Title.flac"
REFRESH_OLD_PATH = "Artist/2026_Album/1-04_Old-Title.flac"
REFRESH_NEW_PATH = "Artist/2026_Album/1-04_New-Title.flac"

METADATA = TrackMetadata(title="Title", artist="Artist", album="Album", year=2026, track_number=2, disc_number=1)
ADD_OLD_METADATA = TrackMetadata(
    title="Old Title",
    artist="Artist",
    album="Album",
    year=1998,
    track_number=1,
    disc_number=1,
)
ADD_NEW_METADATA = TrackMetadata(
    title="New Title",
    artist="Artist",
    album="Album",
    year=2004,
    track_number=2,
    disc_number=1,
)
ORGANIZE_METADATA = TrackMetadata(
    title="Loose Title",
    artist="Artist",
    album="Album",
    year=2026,
    track_number=3,
    disc_number=1,
)
REFRESH_OLD_METADATA = TrackMetadata(
    title="Old Title",
    artist="Artist",
    album="Album",
    year=2026,
    track_number=4,
    disc_number=1,
)
REFRESH_NEW_METADATA = TrackMetadata(
    title="New Title",
    artist="Artist",
    album="Album",
    year=2026,
    track_number=4,
    disc_number=1,
)


class _JsonResponse(Protocol):
    def json(self) -> object: ...


def test_plans_api_paginates_newest_first_with_keyset_cursor_and_terminates(tmp_path: Path) -> None:
    """A limit=1 walk over 3 Plans visits every Plan once, newest first, then next_cursor is null."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _seed_plan_pages(app_paths.database_file, str(library_root))
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    visited: list[str] = []
    cursor: str | None = None
    last_page: dict[str, object] | None = None
    for _ in range(SEEDED_PLAN_COUNT + 1):
        params = {"limit": str(ONE_ITEM_LIMIT)} | ({"cursor": cursor} if cursor else {})
        response = client.get(WEB_API_PLANS_ROUTE, params=params)
        assert response.status_code == SUCCESS_STATUS_CODE
        payload = _json_payload(response)
        items = _object_list_payload(payload, "items")
        page = _object_payload(payload, "page")
        visited.extend(cast("str", item["plan_id"]) for item in items)
        assert page["total"] == SEEDED_PLAN_COUNT
        assert page["limit"] == ONE_ITEM_LIMIT
        last_page = page
        next_cursor = page["next_cursor"]
        if next_cursor is None:
            break
        cursor = cast("str", next_cursor)

    assert visited == [str(THIRD_PLAN_ID), str(SECOND_PLAN_ID), str(PLAN_ID)]
    assert len(visited) == len(set(visited))
    assert last_page is not None
    assert last_page["next_cursor"] is None


def test_plans_api_filters_by_status_and_type(tmp_path: Path) -> None:
    """The status and type filters combine as AND; page.total counts the filtered rows."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _seed_plan_pages(app_paths.database_file, str(library_root))
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_API_PLANS_ROUTE, params={"status": "ready", "type": "add"})

    assert response.status_code == SUCCESS_STATUS_CODE
    payload = _json_payload(response)
    items = _object_list_payload(payload, "items")
    page = _object_payload(payload, "page")
    assert payload["errors"] == []
    assert [item["plan_id"] for item in items] == [str(PLAN_ID)]
    assert items[0]["plan_type"] == PlanType.ADD.value
    assert items[0]["status"] == PlanStatus.READY.value
    assert items[0]["summary"] == {"action_count": "2"}
    assert page["total"] == 1


def test_plans_api_rejects_invalid_cursor_status_and_low_limit(tmp_path: Path) -> None:
    """Malformed cursors, unknown statuses, and limit=0 return the documented 400 envelope."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    cursor_response = client.get(WEB_API_PLANS_ROUTE, params={"cursor": "not-valid-base64url!!"})
    status_response = client.get(WEB_API_PLANS_ROUTE, params={"status": "not-a-status"})
    limit_response = client.get(WEB_API_PLANS_ROUTE, params={"limit": "0"})

    assert cursor_response.status_code == ERROR_STATUS_CODE
    assert cursor_response.json() == {"items": [], "page": None, "errors": ["Invalid cursor."]}
    assert status_response.status_code == ERROR_STATUS_CODE
    assert status_response.json() == {
        "items": [],
        "page": None,
        "errors": ["Invalid plan status filter: not-a-status"],
    }
    assert limit_response.status_code == ERROR_STATUS_CODE
    assert limit_response.json()["page"] is None


def test_plans_api_clamps_limit_above_maximum(tmp_path: Path) -> None:
    """A limit above 500 is clamped down to 500, not rejected."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_API_PLANS_ROUTE, params={"limit": str(CLAMPED_LIMIT_REQUEST)})

    assert response.status_code == SUCCESS_STATUS_CODE
    page = _object_payload(_json_payload(response), "page")
    assert page["limit"] == MAX_PAGE_LIMIT


def test_plan_detail_api_returns_header_only(tmp_path: Path) -> None:
    """Plan detail returns the header without an embedded actions array or total_action_count."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _seed_plan_detail(app_paths.database_file, str(library_root))
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(f"{WEB_API_PLANS_ROUTE}/{PLAN_ID}")

    assert response.status_code == SUCCESS_STATUS_CODE
    payload = _json_payload(response)
    detail = _object_payload(payload, "detail")
    plan = _object_payload(detail, "plan")
    assert payload["errors"] == []
    assert set(detail) == {"plan"}
    assert plan["plan_id"] == str(PLAN_ID)
    assert plan["config_hash"] == calculate_config_fingerprint(AppConfig())
    assert plan["library_root_at_plan"] == str(library_root)


def test_plan_detail_api_returns_not_found_for_missing_or_invalid_plan(tmp_path: Path) -> None:
    """Plan detail reports missing and malformed Plan IDs as not found."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    missing_response = client.get(f"{WEB_API_PLANS_ROUTE}/{MISSING_PLAN_ID}")
    invalid_response = client.get(f"{WEB_API_PLANS_ROUTE}/{INVALID_PLAN_ID_TEXT}")

    assert missing_response.status_code == NOT_FOUND_STATUS_CODE
    assert missing_response.json() == {"detail": None, "errors": ["Plan was not found."]}
    assert invalid_response.status_code == NOT_FOUND_STATUS_CODE
    assert invalid_response.json() == {"detail": None, "errors": ["Plan was not found."]}


def test_plan_actions_api_paginates_with_keyset_cursor_and_terminates(tmp_path: Path) -> None:
    """A limit=1 walk over a Plan's actions visits every action once, in review order."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _seed_plan_detail(app_paths.database_file, str(library_root))
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    visited: list[str] = []
    cursor: str | None = None
    for _ in range(SEEDED_ACTION_COUNT + 1):
        params = {"limit": str(ONE_ITEM_LIMIT)} | ({"cursor": cursor} if cursor else {})
        response = client.get(f"{WEB_API_PLANS_ROUTE}/{PLAN_ID}/actions", params=params)
        assert response.status_code == SUCCESS_STATUS_CODE
        payload = _json_payload(response)
        items = _object_list_payload(payload, "items")
        page = _object_payload(payload, "page")
        visited.extend(cast("str", item["action_id"]) for item in items)
        assert page["total"] == SEEDED_ACTION_COUNT
        next_cursor = page["next_cursor"]
        if next_cursor is None:
            break
        cursor = cast("str", next_cursor)

    assert visited == [str(ACTION_ID), str(BLOCKED_ACTION_ID)]


def test_plan_actions_api_filters_by_status(tmp_path: Path) -> None:
    """The status filter only returns actions with a matching status; total matches the filter."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _seed_plan_detail(app_paths.database_file, str(library_root))
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(f"{WEB_API_PLANS_ROUTE}/{PLAN_ID}/actions", params={"status": "blocked"})

    assert response.status_code == SUCCESS_STATUS_CODE
    payload = _json_payload(response)
    items = _object_list_payload(payload, "items")
    page = _object_payload(payload, "page")
    assert [item["action_id"] for item in items] == [str(BLOCKED_ACTION_ID)]
    assert items[0]["status"] == ActionStatus.BLOCKED.value
    assert items[0]["reason"] == PlanActionReason.TARGET_EXISTS.value
    assert items[0]["target_path"] == TARGET_PATH
    assert page["total"] == 1


def test_plan_actions_api_drills_into_group_and_rejects_unpaired_group_filters(tmp_path: Path) -> None:
    """group_by/group_key select one group together and are rejected when only one is present."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _seed_plan_groups(app_paths.database_file, str(library_root))
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(
        f"{WEB_API_PLANS_ROUTE}/{PLAN_ID}/actions",
        params={"group_by": "artist_album", "group_key": "Artist/2026_Album"},
    )
    group_by_only = client.get(
        f"{WEB_API_PLANS_ROUTE}/{PLAN_ID}/actions",
        params={"group_by": "artist_album"},
    )
    group_key_only = client.get(
        f"{WEB_API_PLANS_ROUTE}/{PLAN_ID}/actions",
        params={"group_key": "Artist/2026_Album"},
    )

    assert response.status_code == SUCCESS_STATUS_CODE
    payload = _json_payload(response)
    assert [item["action_id"] for item in _object_list_payload(payload, "items")] == [
        str(ACTION_ID),
        str(BLOCKED_ACTION_ID),
    ]
    assert _object_payload(payload, "page")["total"] == SEEDED_ACTION_COUNT
    expected_error = ["Query parameters group_by and group_key must be provided together."]
    assert group_by_only.status_code == ERROR_STATUS_CODE
    assert group_by_only.json() == {"items": [], "page": None, "errors": expected_error}
    assert group_key_only.status_code == ERROR_STATUS_CODE
    assert group_key_only.json() == {"items": [], "page": None, "errors": expected_error}


def test_plan_actions_api_group_drill_down_applies_query_with_ascii_case_folding(tmp_path: Path) -> None:
    """The in-process drill-down search matches ASCII case-insensitively, like the SQL list search."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _seed_plan_groups(app_paths.database_file, str(library_root))
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(
        f"{WEB_API_PLANS_ROUTE}/{PLAN_ID}/actions",
        params={
            "group_by": "artist_album",
            "group_key": "Artist/2026_Album",
            "query": "1-03_TITLE",
        },
    )

    assert response.status_code == SUCCESS_STATUS_CODE
    payload = _json_payload(response)
    assert [item["action_id"] for item in _object_list_payload(payload, "items")] == [str(BLOCKED_ACTION_ID)]
    assert _object_payload(payload, "page")["total"] == 1


def test_plan_actions_api_rejects_invalid_status_and_cursor(tmp_path: Path) -> None:
    """Unknown status filters and malformed cursors return the documented 400 envelope."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _seed_plan_detail(app_paths.database_file, str(library_root))
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    status_response = client.get(f"{WEB_API_PLANS_ROUTE}/{PLAN_ID}/actions", params={"status": "moved"})
    cursor_response = client.get(
        f"{WEB_API_PLANS_ROUTE}/{PLAN_ID}/actions",
        params={"cursor": "not-valid-base64url!!"},
    )

    assert status_response.status_code == ERROR_STATUS_CODE
    assert status_response.json() == {
        "items": [],
        "page": None,
        "errors": ["Invalid action status filter: moved"],
    }
    assert cursor_response.status_code == ERROR_STATUS_CODE
    assert cursor_response.json() == {"items": [], "page": None, "errors": ["Invalid cursor."]}


def test_plan_actions_api_returns_not_found_for_unknown_plan(tmp_path: Path) -> None:
    """An unknown Plan ID returns a 404 list envelope."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(f"{WEB_API_PLANS_ROUTE}/{MISSING_PLAN_ID}/actions")

    assert response.status_code == NOT_FOUND_STATUS_CODE
    assert response.json() == {"items": [], "page": None, "errors": ["Plan was not found."]}


def test_plan_facets_api_returns_risk_summary_counts(tmp_path: Path) -> None:
    """Plan facets expose status/type/reason breakdowns, total actions, and target collisions."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _seed_plan_detail(app_paths.database_file, str(library_root))
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(f"{WEB_API_PLANS_ROUTE}/{PLAN_ID}/facets")

    assert response.status_code == SUCCESS_STATUS_CODE
    payload = _json_payload(response)
    facets = _object_payload(payload, "facets")
    assert facets["status"] == [
        {"value": ActionStatus.BLOCKED.value, "count": 1},
        {"value": ActionStatus.PLANNED.value, "count": 1},
    ]
    assert facets["action_type"] == [{"value": ActionType.MOVE.value, "count": 2}]
    assert facets["reason"] == [{"value": PlanActionReason.TARGET_EXISTS.value, "count": 1}]
    assert payload["total"] == SEEDED_ACTION_COUNT
    assert payload["target_collisions"] == 1
    assert payload["errors"] == []


def test_plan_action_search_and_facets_combine_catalog_filters(tmp_path: Path) -> None:
    """Action list/facet/group routes share query, status, type, and reason filtering."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _seed_plan_detail(app_paths.database_file, str(library_root))
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))
    params = {
        "query": str(BLOCKED_ACTION_ID),
        "status": ActionStatus.BLOCKED.value,
        "action_type": ActionType.MOVE.value,
        "reason": PlanActionReason.TARGET_EXISTS.value,
    }

    list_response = client.get(f"{WEB_API_PLANS_ROUTE}/{PLAN_ID}/actions", params=params)
    facets_response = client.get(f"{WEB_API_PLANS_ROUTE}/{PLAN_ID}/facets", params=params)
    groups_response = client.get(
        f"{WEB_API_PLANS_ROUTE}/{PLAN_ID}/groups",
        params={**params, "group_by": "status"},
    )

    assert list_response.status_code == SUCCESS_STATUS_CODE
    assert [item["action_id"] for item in _object_list_payload(_json_payload(list_response), "items")] == [
        str(BLOCKED_ACTION_ID)
    ]
    assert facets_response.status_code == SUCCESS_STATUS_CODE
    facets_payload = _json_payload(facets_response)
    assert facets_payload["total"] == 1
    assert _object_payload(facets_payload, "facets")["status"] == [{"value": ActionStatus.BLOCKED.value, "count": 1}]
    assert groups_response.status_code == SUCCESS_STATUS_CODE
    assert _object_list_payload(_json_payload(groups_response), "items") == [
        {
            "key": ActionStatus.BLOCKED.value,
            "label": ActionStatus.BLOCKED.value,
            "count": 1,
            "blocked_count": 1,
            "top_reason": PlanActionReason.TARGET_EXISTS.value,
        }
    ]


def test_plan_facets_api_rejects_invalid_action_type_and_reason(tmp_path: Path) -> None:
    """Unknown catalog facet filters return the documented 400 facet envelope."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(
        f"{WEB_API_PLANS_ROUTE}/{PLAN_ID}/facets",
        params={"action_type": "copy", "reason": "unknown"},
    )

    assert response.status_code == ERROR_STATUS_CODE
    assert response.json() == {
        "facets": {},
        "total": None,
        "errors": ["Invalid action type filter: copy", "Invalid action reason filter: unknown"],
    }


def test_plan_facets_api_returns_not_found_for_unknown_plan(tmp_path: Path) -> None:
    """An unknown Plan ID returns a 404 facet envelope with total null."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(f"{WEB_API_PLANS_ROUTE}/{MISSING_PLAN_ID}/facets")

    assert response.status_code == NOT_FOUND_STATUS_CODE
    assert response.json() == {"facets": {}, "total": None, "errors": ["Plan was not found."]}


def test_plan_groups_api_returns_target_directory_groups_with_root_label(tmp_path: Path) -> None:
    """Groups map each target path to its parent directory; root-level targets become '(root)'."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _seed_plan_groups(app_paths.database_file, str(library_root))
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(f"{WEB_API_PLANS_ROUTE}/{PLAN_ID}/groups", params={"group_by": "target_directory"})

    assert response.status_code == SUCCESS_STATUS_CODE
    payload = _json_payload(response)
    assert payload["group_by"] == "target_directory"
    items = _object_list_payload(payload, "items")
    assert items == [
        {
            "key": TARGET_DIRECTORY,
            "label": TARGET_DIRECTORY,
            "count": 2,
            "blocked_count": 1,
            "top_reason": PlanActionReason.TARGET_EXISTS.value,
        },
        {
            "key": ROOT_GROUP_LABEL,
            "label": ROOT_GROUP_LABEL,
            "count": 1,
            "blocked_count": 0,
            "top_reason": None,
        },
    ]
    page = _object_payload(payload, "page")
    assert page["total"] == SEEDED_ACTION_COUNT
    assert page["next_cursor"] is None


def test_plan_groups_api_paginates_with_count_then_key_keyset(tmp_path: Path) -> None:
    """A limit=1 keyset walk over target-directory groups visits every group exactly once."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _seed_plan_groups(app_paths.database_file, str(library_root))
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    first_response = client.get(
        f"{WEB_API_PLANS_ROUTE}/{PLAN_ID}/groups",
        params={"group_by": "target_directory", "limit": str(ONE_ITEM_LIMIT)},
    )
    first_payload = _json_payload(first_response)
    first_page = _object_payload(first_payload, "page")
    next_cursor = first_page["next_cursor"]
    assert next_cursor is not None
    second_response = client.get(
        f"{WEB_API_PLANS_ROUTE}/{PLAN_ID}/groups",
        params={"group_by": "target_directory", "limit": str(ONE_ITEM_LIMIT), "cursor": cast("str", next_cursor)},
    )

    assert first_response.status_code == SUCCESS_STATUS_CODE
    assert _object_list_payload(first_payload, "items") == [
        {
            "key": TARGET_DIRECTORY,
            "label": TARGET_DIRECTORY,
            "count": 2,
            "blocked_count": 1,
            "top_reason": PlanActionReason.TARGET_EXISTS.value,
        }
    ]
    assert second_response.status_code == SUCCESS_STATUS_CODE
    second_payload = _json_payload(second_response)
    assert _object_list_payload(second_payload, "items") == [
        {
            "key": ROOT_GROUP_LABEL,
            "label": ROOT_GROUP_LABEL,
            "count": 1,
            "blocked_count": 0,
            "top_reason": None,
        }
    ]
    assert _object_payload(second_payload, "page")["next_cursor"] is None


def test_plan_groups_api_rejects_missing_or_invalid_group_by(tmp_path: Path) -> None:
    """A missing or unknown group_by value returns the documented 400 group envelope."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _seed_plan_detail(app_paths.database_file, str(library_root))
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    missing_response = client.get(f"{WEB_API_PLANS_ROUTE}/{PLAN_ID}/groups")
    invalid_response = client.get(
        f"{WEB_API_PLANS_ROUTE}/{PLAN_ID}/groups",
        params={"group_by": "not-a-grouping"},
    )

    assert missing_response.status_code == ERROR_STATUS_CODE
    assert missing_response.json() == {
        "group_by": None,
        "items": [],
        "page": None,
        "errors": ["Query parameter group_by is required."],
    }
    assert invalid_response.status_code == ERROR_STATUS_CODE
    assert invalid_response.json() == {
        "group_by": None,
        "items": [],
        "page": None,
        "errors": ["Invalid group_by filter: not-a-grouping"],
    }


def test_plan_groups_api_returns_not_found_for_unknown_plan(tmp_path: Path) -> None:
    """An unknown Plan ID returns a 404 group envelope."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(
        f"{WEB_API_PLANS_ROUTE}/{MISSING_PLAN_ID}/groups",
        params={"group_by": "target_directory"},
    )

    assert response.status_code == NOT_FOUND_STATUS_CODE
    assert response.json() == {
        "group_by": None,
        "items": [],
        "page": None,
        "errors": ["Plan was not found."],
    }


def test_create_add_plan_uses_persisted_album_year_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Add Plan creation records target paths resolved from saved album-year settings."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    incoming_root = tmp_path / "incoming"
    old_file = _write_audio_file(incoming_root, "Old.flac", content=b"old")
    new_file = _write_audio_file(incoming_root, "New.flac", content=b"new")
    config = AppConfig(
        paths=PathsConfig(library=str(library_root), incoming=str(incoming_root)),
        metadata=MetadataConfig(album_year_resolution=ALBUM_YEAR_RESOLUTION_OLDEST),
    )
    library_root.mkdir()
    TomlConfigStore(app_paths.config_file).save(config)
    _register_library(app_paths.database_file, str(library_root), config=config)
    _patch_metadata_reader(
        monkeypatch,
        {
            old_file: ADD_OLD_METADATA,
            new_file: ADD_NEW_METADATA,
        },
    )
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.post(
        WEB_API_PLAN_ADD_ROUTE,
        json={"source_path": str(incoming_root)},
        headers={WEB_CSRF_HEADER_NAME: _csrf_token(client)},
    )

    assert response.status_code == SUCCESS_STATUS_CODE
    payload = _json_payload(response)
    detail = _object_payload(payload, "detail")
    plan = _object_payload(detail, "plan")
    assert payload["created"] is True
    assert payload["errors"] == []
    assert set(detail) == {"plan"}
    assert plan["plan_type"] == PlanType.ADD.value

    actions_response = client.get(f"{WEB_API_PLANS_ROUTE}/{plan['plan_id']}/actions")
    assert actions_response.status_code == SUCCESS_STATUS_CODE
    actions = _object_list_payload(_json_payload(actions_response), "items")
    assert {action["target_path"] for action in actions} == {ADD_OLD_TARGET, ADD_NEW_TARGET}


def test_create_add_plan_reports_missing_source_as_request_error(tmp_path: Path) -> None:
    """Add Plan creation reports missing user-supplied roots as request errors."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    missing_source = tmp_path / "missing-incoming"
    config = AppConfig(paths=PathsConfig(library=str(library_root)))
    library_root.mkdir()
    TomlConfigStore(app_paths.config_file).save(config)
    _register_library(app_paths.database_file, str(library_root), config=config)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.post(
        WEB_API_PLAN_ADD_ROUTE,
        json={"source_path": str(missing_source)},
        headers={WEB_CSRF_HEADER_NAME: _csrf_token(client)},
    )

    assert response.status_code == ERROR_STATUS_CODE
    payload = _json_payload(response)
    errors = _string_list_payload(payload, "errors")
    assert payload["created"] is False
    assert payload["detail"] is None
    assert errors[0].startswith("Plan path was not found:")
    assert str(missing_source) in errors[0]


def test_create_organize_plan_via_web_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Organize Plan creation returns a header and exposes reviewable actions separately."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    loose_file = _write_audio_file(library_root, "Loose.flac")
    TomlConfigStore(app_paths.config_file).save(AppConfig(paths=PathsConfig(library=str(library_root))))
    _patch_metadata_reader(monkeypatch, {loose_file: ORGANIZE_METADATA})
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.post(
        WEB_API_PLAN_ORGANIZE_ROUTE,
        json={"library_root": str(library_root)},
        headers={WEB_CSRF_HEADER_NAME: _csrf_token(client)},
    )

    assert response.status_code == SUCCESS_STATUS_CODE
    payload = _json_payload(response)
    detail = _object_payload(payload, "detail")
    plan = _object_payload(detail, "plan")
    assert payload["created"] is True
    assert payload["errors"] == []
    assert set(detail) == {"plan"}
    assert _object_payload(payload, "registration")["track_count"] == 1
    assert plan["plan_type"] == PlanType.ORGANIZE.value

    actions_response = client.get(f"{WEB_API_PLANS_ROUTE}/{plan['plan_id']}/actions")
    assert actions_response.status_code == SUCCESS_STATUS_CODE
    actions = _object_list_payload(_json_payload(actions_response), "items")
    assert actions[0]["source_path"] == "Loose.flac"
    assert actions[0]["target_path"] == ORGANIZE_TARGET


def test_create_organize_plan_reports_file_root_as_request_error(tmp_path: Path) -> None:
    """Organize Plan creation reports file roots as request errors."""
    app_paths = default_application_paths(tmp_path)
    file_root = tmp_path / "library-file"
    _ = file_root.write_text("not a directory", encoding=CONFIG_FILE_ENCODING)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.post(
        WEB_API_PLAN_ORGANIZE_ROUTE,
        json={"library_root": str(file_root)},
        headers={WEB_CSRF_HEADER_NAME: _csrf_token(client)},
    )

    assert response.status_code == ERROR_STATUS_CODE
    payload = _json_payload(response)
    errors = _string_list_payload(payload, "errors")
    assert payload["created"] is False
    assert payload["detail"] is None
    assert errors[0].startswith("Plan path must be a directory:")
    assert str(file_root) in errors[0]


def test_create_refresh_plan_via_web_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refresh Plan creation returns a header and records separately browsable actions."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    old_file = _write_audio_file(library_root, REFRESH_OLD_PATH)
    config = AppConfig(paths=PathsConfig(library=str(library_root)))
    TomlConfigStore(app_paths.config_file).save(config)
    _register_library_and_tracks(
        app_paths.database_file,
        str(library_root),
        _track(current_path=REFRESH_OLD_PATH),
        config=config,
    )
    _patch_metadata_reader(monkeypatch, {old_file: REFRESH_NEW_METADATA})
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.post(
        WEB_API_PLAN_REFRESH_ROUTE,
        json={"include_all": True},
        headers={WEB_CSRF_HEADER_NAME: _csrf_token(client)},
    )

    assert response.status_code == SUCCESS_STATUS_CODE
    payload = _json_payload(response)
    detail = _object_payload(payload, "detail")
    plan = _object_payload(detail, "plan")
    assert payload["created"] is True
    assert payload["errors"] == []
    assert set(detail) == {"plan"}
    assert plan["plan_type"] == PlanType.REFRESH.value

    actions_response = client.get(f"{WEB_API_PLANS_ROUTE}/{plan['plan_id']}/actions")
    assert actions_response.status_code == SUCCESS_STATUS_CODE
    actions = _object_list_payload(_json_payload(actions_response), "items")
    assert actions[0]["source_path"] == REFRESH_OLD_PATH
    assert actions[0]["target_path"] == REFRESH_NEW_PATH


def test_create_plan_requires_csrf_token(tmp_path: Path) -> None:
    """Plan creation POSTs reject requests without the Web CSRF header."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.post(WEB_API_PLAN_ADD_ROUTE, json={"source_path": None})

    assert response.status_code == FORBIDDEN_STATUS_CODE
    assert response.json() == {
        "created": False,
        "detail": None,
        "registration": None,
        "errors": ["Plan creation request failed CSRF validation."],
    }


def _seed_plan_detail(database_file: Path, library_root: str) -> None:
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(library_root))
        uow.plans.save(_plan(library_root))
        uow.plan_actions.save(_action(action_id=ACTION_ID, status=ActionStatus.PLANNED, reason=None))
        uow.plan_actions.save(
            _action(
                action_id=BLOCKED_ACTION_ID,
                status=ActionStatus.BLOCKED,
                reason=PlanActionReason.TARGET_EXISTS,
                sort_order=2,
            )
        )
        uow.commit()


def _seed_plan_pages(database_file: Path, library_root: str) -> None:
    """Seed three Plans with distinct statuses/types/timestamps for paging and filter tests."""
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(library_root))
        uow.plans.save(_plan(library_root, plan_type=PlanType.ADD, status=PlanStatus.READY))
        uow.plans.save(
            _plan(
                library_root,
                plan_id=SECOND_PLAN_ID,
                plan_type=PlanType.REFRESH,
                status=PlanStatus.APPLIED,
                created_at=datetime(2026, 1, 2, tzinfo=UTC),
            )
        )
        uow.plans.save(
            _plan(
                library_root,
                plan_id=THIRD_PLAN_ID,
                plan_type=PlanType.ORGANIZE,
                status=PlanStatus.READY,
                created_at=datetime(2026, 1, 3, tzinfo=UTC),
            )
        )
        uow.commit()


def _seed_plan_groups(database_file: Path, library_root: str) -> None:
    """Seed one Plan with two same-directory targets, one root-level target, and one null target."""
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(library_root))
        uow.plans.save(_plan(library_root))
        uow.plan_actions.save(_action(action_id=ACTION_ID, status=ActionStatus.PLANNED, reason=None))
        uow.plan_actions.save(
            _action(
                action_id=BLOCKED_ACTION_ID,
                status=ActionStatus.BLOCKED,
                reason=PlanActionReason.TARGET_EXISTS,
                sort_order=2,
                target_path="Artist/2026_Album/1-03_Title.flac",
            )
        )
        uow.plan_actions.save(
            _action(
                action_id=THIRD_ACTION_ID,
                status=ActionStatus.PLANNED,
                reason=None,
                sort_order=3,
                target_path="Loose.flac",
            )
        )
        uow.plan_actions.save(
            _action(
                action_id=ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345680")),
                status=ActionStatus.PLANNED,
                reason=None,
                sort_order=4,
                action_type=ActionType.SKIP,
                target_path=None,
            )
        )
        uow.commit()


def _json_payload(response: _JsonResponse) -> dict[str, object]:
    return cast("dict[str, object]", response.json())


def _object_payload(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload[key]
    assert isinstance(value, dict)
    return cast("dict[str, object]", value)


def _object_list_payload(payload: dict[str, object], key: str) -> list[dict[str, object]]:
    value = payload[key]
    assert isinstance(value, list)
    return cast("list[dict[str, object]]", value)


def _string_list_payload(payload: dict[str, object], key: str) -> list[str]:
    value = payload[key]
    assert isinstance(value, list)
    items = cast("list[object]", value)
    assert all(isinstance(item, str) for item in items)
    return cast("list[str]", items)


def _csrf_token(client: TestClient) -> str:
    response = client.get(WEB_API_SETTINGS_ROUTE)
    assert response.status_code == SUCCESS_STATUS_CODE
    token = _json_payload(response)["csrf_token"]
    assert isinstance(token, str)
    return token


def _patch_metadata_reader(
    monkeypatch: pytest.MonkeyPatch,
    metadata_by_path: dict[Path, TrackMetadata],
) -> None:
    normalized_metadata = {path.resolve(): metadata for path, metadata in metadata_by_path.items()}

    def read(self: MutagenMetadataReader, path: FileSystemPath) -> TrackMetadata:
        del self
        path_key = Path(path).resolve()
        assert path_key in normalized_metadata
        return normalized_metadata[path_key]

    monkeypatch.setattr(MutagenMetadataReader, "read", read)


def _write_audio_file(root: Path, relative_path: str, *, content: bytes = AUDIO_CONTENT) -> Path:
    audio_path = root.joinpath(*relative_path.split("/"))
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    _ = audio_path.write_bytes(content)
    return audio_path


def _register_library(database_file: Path, library_root: str, *, config: AppConfig | None = None) -> None:
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(library_root, config=config))
        uow.commit()


def _register_library_and_tracks(
    database_file: Path,
    library_root: str,
    *tracks: Track,
    config: AppConfig | None = None,
) -> None:
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(library_root, config=config))
        for track in tracks:
            uow.tracks.save(track)
        uow.commit()


def _library(
    library_root: str,
    *,
    config: AppConfig | None = None,
    status: LibraryStatus = LibraryStatus.REGISTERED,
) -> Library:
    current_config = AppConfig() if config is None else config
    return Library(
        library_id=LIBRARY_ID,
        root_path=library_root,
        path_policy_hash=calculate_path_policy_fingerprint(
            current_config.path_policy,
            current_config.artist_ids,
            current_config.metadata.album_year_resolution,
        ),
        registered_at=BASE_TIME,
        status=status,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _track(current_path: str = TARGET_PATH, *, metadata: TrackMetadata = REFRESH_OLD_METADATA) -> Track:
    return Track(
        track_id=TRACK_ID,
        library_id=LIBRARY_ID,
        current_path=current_path,
        canonical_path=current_path,
        content_hash=CONTENT_HASH,
        metadata_hash=calculate_metadata_fingerprint(metadata),
        size=None,
        mtime=None,
        metadata=metadata,
        status=TrackStatus.ACTIVE,
        first_seen_at=BASE_TIME,
        last_seen_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _plan(
    library_root: str,
    *,
    plan_id: PlanId = PLAN_ID,
    plan_type: PlanType = PlanType.ADD,
    status: PlanStatus = PlanStatus.READY,
    created_at: datetime = BASE_TIME,
) -> Plan:
    return Plan(
        plan_id=plan_id,
        library_id=LIBRARY_ID,
        plan_type=plan_type,
        status=status,
        created_at=created_at,
        config_hash=calculate_config_fingerprint(AppConfig()),
        library_root_at_plan=library_root,
        summary={"action_count": "2"},
    )


def _action(  # noqa: PLR0913 - test fixture spans the paging/facet/grouping action variation matrix.
    *,
    action_id: ActionId,
    status: ActionStatus,
    reason: PlanActionReason | None,
    sort_order: int = 1,
    action_type: ActionType = ActionType.MOVE,
    target_path: str | None = TARGET_PATH,
) -> PlanAction:
    return PlanAction(
        action_id=action_id,
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        track_id=None,
        action_type=action_type,
        source_path="/incoming/Title.flac",
        target_path=target_path,
        content_hash_at_plan=CONTENT_HASH,
        metadata_hash_at_plan=calculate_metadata_fingerprint(METADATA),
        status=status,
        reason=reason,
        sort_order=sort_order,
    )
