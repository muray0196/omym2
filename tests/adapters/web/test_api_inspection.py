"""
Summary: Tests the renewed read-only Plan and Track Web API slices.
Why: Locks list, detail, capability, facet, group, and error envelope shapes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import UUID

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from omym2.adapters.web.routes.plans import PlanRouteHandlers, create_plans_router, get_plan_route_handlers
from omym2.adapters.web.routes.tracks import TrackRouteHandlers, create_tracks_router, get_track_route_handlers
from omym2.config import HTTP_NOT_FOUND_STATUS
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction
from omym2.domain.models.track import Track, TrackGrouping, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.features.plans.dto import (
    PlanActionFacetsResult,
    PlanActionGroup,
    plan_action_summary_from_counts,
)
from omym2.features.plans.usecases.get_plan_capabilities import PlanCapabilitiesResult
from omym2.features.plans.usecases.get_plan_header import PlanNotFoundError
from omym2.features.tracks.dto import TrackStatusFacetsResult
from omym2.features.tracks.usecases.get_track import TrackNotFoundError
from omym2.shared.ids import ActionId, LibraryId, PlanId, TrackId
from omym2.shared.pagination import FacetValue, GroupCount, Page

if TYPE_CHECKING:
    from collections.abc import Callable

NOW = datetime(2026, 7, 13, tzinfo=UTC)
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345670"))
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345671"))
TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345672"))
ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345673"))
PLAN_NOT_FOUND_MESSAGE = "Plan was not found."
TRACK_NOT_FOUND_MESSAGE = "Track was not found."


def test_plan_routes_return_typed_browse_and_detail_resources() -> None:
    """Plan inspection exposes current summaries, recorded actions, groups, and capabilities."""
    client = _plan_client()

    list_payload = _payload(cast("object", client.get("/api/plans").json()))
    detail_payload = _payload(cast("object", client.get(f"/api/plans/{PLAN_ID}").json()))
    actions_payload = _payload(cast("object", client.get(f"/api/plans/{PLAN_ID}/actions").json()))
    facets_payload = _payload(cast("object", client.get(f"/api/plans/{PLAN_ID}/facets").json()))
    groups_payload = _payload(
        cast("object", client.get(f"/api/plans/{PLAN_ID}/groups", params={"group_by": "status"}).json())
    )
    list_data = _object(list_payload, "data")
    list_items = _objects(list_data, "items")
    detail_data = _object(detail_payload, "data")
    actions_data = _object(actions_payload, "data")
    facets_data = _object(facets_payload, "data")
    groups_data = _object(groups_payload, "data")

    assert list_payload["errors"] == []
    assert list_data["page"] == {"limit": 100, "next_cursor": None, "total": 1}
    assert _object(_object(_object(list_items[0], "summary"), "counts"), "planned")["move"] == 1
    assert detail_data["capabilities"] == {
        "can_apply": True,
        "can_cancel": True,
        "can_recreate": True,
        "disabled_reasons": [],
    }
    assert detail_data["active_operation_id"] is None
    assert _objects(actions_data, "items")[0]["source_path"] == "Artist/old.flac"
    assert _object(facets_data, "facets")["status"] == [{"value": "planned", "count": 1}]
    assert _objects(groups_data, "items")[0]["blocked_count"] == 0


def test_plan_detail_returns_typed_not_found_envelope() -> None:
    """An unknown Plan ID maps to the closed plan_not_found error."""
    handlers = _plan_handlers()

    def missing_plan(_request: object) -> Plan:
        raise PlanNotFoundError(PLAN_NOT_FOUND_MESSAGE)

    client = _client(
        create_plans_router(),
        get_plan_route_handlers,
        PlanRouteHandlers(
            list_plans=handlers.list_plans,
            get_plan_header=missing_plan,
            get_plan_action_summaries=handlers.get_plan_action_summaries,
            get_plan_capabilities=handlers.get_plan_capabilities,
            list_plan_actions=handlers.list_plan_actions,
            get_plan_action_facets=handlers.get_plan_action_facets,
            group_plan_actions=handlers.group_plan_actions,
        ),
    )

    response = client.get(f"/api/plans/{PLAN_ID}")

    assert response.status_code == HTTP_NOT_FOUND_STATUS
    assert response.json()["errors"][0]["code"] == "plan_not_found"
    assert response.json()["errors"][0]["field"] == "path.plan_id"


def test_track_routes_return_persisted_browse_detail_facets_and_groups() -> None:
    """Track inspection serializes persisted metadata without filesystem-derived values."""
    client = _track_client()

    list_payload = _payload(cast("object", client.get("/api/tracks").json()))
    detail_payload = _payload(cast("object", client.get(f"/api/tracks/{TRACK_ID}").json()))
    facets_payload = _payload(cast("object", client.get("/api/tracks/facets").json()))
    groups_payload = _payload(cast("object", client.get("/api/tracks/groups", params={"group_by": "artist"}).json()))
    list_data = _object(list_payload, "data")
    list_items = _objects(list_data, "items")
    detail_data = _object(detail_payload, "data")
    groups_data = _object(groups_payload, "data")

    assert list_data["page"] == {"limit": 100, "next_cursor": None, "total": 1}
    assert list_items[0]["current_path"] == "Artist/Album/01 Title.flac"
    assert _object(detail_data, "metadata")["title"] == "Title"
    assert detail_data["content_hash"] == "content"
    assert _object(facets_payload, "data") == {
        "facets": {"status": [{"value": "active", "count": 1}]},
        "total": 1,
    }
    assert groups_data["group_by"] == "artist"
    assert groups_data["items"] == [{"key": '["Artist"]', "label": "Artist", "count": 1}]


def test_track_detail_returns_typed_not_found_envelope() -> None:
    """An unknown Track ID maps to the closed track_not_found error."""
    handlers = _track_handlers()

    def missing_track(_request: object) -> Track:
        raise TrackNotFoundError(TRACK_NOT_FOUND_MESSAGE)

    client = _client(
        create_tracks_router(),
        get_track_route_handlers,
        TrackRouteHandlers(
            list_tracks=handlers.list_tracks,
            get_track=missing_track,
            get_track_status_facets=handlers.get_track_status_facets,
            group_tracks=handlers.group_tracks,
        ),
    )

    response = client.get(f"/api/tracks/{TRACK_ID}")

    assert response.status_code == HTTP_NOT_FOUND_STATUS
    assert response.json()["errors"][0]["code"] == "track_not_found"
    assert response.json()["errors"][0]["field"] == "path.track_id"


def _client(router: APIRouter, dependency: Callable[..., object], handlers: object) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[dependency] = lambda: handlers
    return TestClient(app)


def _plan_client() -> TestClient:
    return _client(create_plans_router(), get_plan_route_handlers, _plan_handlers())


def _plan_handlers() -> PlanRouteHandlers:
    plan = _plan()
    action = _action()
    summary = plan_action_summary_from_counts({(ActionStatus.PLANNED, ActionType.MOVE): 1})
    return PlanRouteHandlers(
        list_plans=lambda _request: Page(items=(plan,), next_cursor_key=None, total=1),
        get_plan_header=lambda _request: plan,
        get_plan_action_summaries=lambda _request: {PLAN_ID: summary},
        get_plan_capabilities=lambda _request: PlanCapabilitiesResult(
            can_apply=True,
            can_cancel=True,
            can_recreate=True,
            disabled_reasons=(),
        ),
        list_plan_actions=lambda _request: Page(items=(action,), next_cursor_key=None, total=1),
        get_plan_action_facets=lambda _request: PlanActionFacetsResult(
            status_facets=(FacetValue(ActionStatus.PLANNED.value, 1),),
            action_type_facets=(FacetValue(ActionType.MOVE.value, 1),),
            reason_facets=(),
            total=1,
            target_collisions=0,
        ),
        group_plan_actions=lambda _request: Page(
            items=(PlanActionGroup("planned", "planned", 1, 0, None),),
            next_cursor_key=None,
            total=1,
        ),
    )


def _track_client() -> TestClient:
    return _client(create_tracks_router(), get_track_route_handlers, _track_handlers())


def _track_handlers() -> TrackRouteHandlers:
    track = _track()
    return TrackRouteHandlers(
        list_tracks=lambda _request: Page(items=(track,), next_cursor_key=None, total=1),
        get_track=lambda _request: track,
        get_track_status_facets=lambda _request: TrackStatusFacetsResult(
            facets=(FacetValue(TrackStatus.ACTIVE.value, 1),),
            total=1,
        ),
        group_tracks=lambda request: (
            Page(
                items=(GroupCount('["Artist"]', "Artist", 1),),
                next_cursor_key=None,
                total=1,
            )
            if request.grouping is TrackGrouping.ARTIST
            else Page(items=(), next_cursor_key=None, total=0)
        ),
    )


def _plan() -> Plan:
    return Plan(
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        plan_type=PlanType.ADD,
        status=PlanStatus.READY,
        created_at=NOW,
        config_hash="config",
        library_root_at_plan="/music",
    )


def _action() -> PlanAction:
    return PlanAction(
        action_id=ACTION_ID,
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        track_id=TRACK_ID,
        action_type=ActionType.MOVE,
        source_path="Artist/old.flac",
        target_path="Artist/Album/01 Title.flac",
        content_hash_at_plan="content",
        metadata_hash_at_plan="metadata",
        status=ActionStatus.PLANNED,
        reason=None,
        sort_order=1,
    )


def _track() -> Track:
    return Track(
        track_id=TRACK_ID,
        library_id=LIBRARY_ID,
        current_path="Artist/Album/01 Title.flac",
        canonical_path="Artist/Album/01 Title.flac",
        content_hash="content",
        metadata_hash="metadata",
        size=1,
        mtime=NOW,
        metadata=TrackMetadata(title="Title", artist="Artist", album="Album"),
        status=TrackStatus.ACTIVE,
        first_seen_at=NOW,
        last_seen_at=NOW,
        updated_at=NOW,
    )


def _payload(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast("dict[str, object]", value)


def _object(payload: dict[str, object], key: str) -> dict[str, object]:
    return _payload(payload[key])


def _objects(payload: dict[str, object], key: str) -> list[dict[str, object]]:
    values = payload[key]
    assert isinstance(values, list)
    return [_payload(value) for value in cast("list[object]", values)]
