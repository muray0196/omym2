"""
Summary: Tests Web Track browsing JSON API routes.
Why: Verifies keyset pagination, search, status filter, facets, and group-by envelopes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol, cast
from uuid import UUID

from fastapi.testclient import TestClient

from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.config.default_config import default_app_config
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.config import WEB_API_TRACKS_FACETS_ROUTE, WEB_API_TRACKS_GROUPS_ROUTE, WEB_API_TRACKS_ROUTE
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.track import Track, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.config_fingerprint import calculate_path_policy_fingerprint
from omym2.platform.web_composition import build_web_app as create_web_app
from omym2.shared.ids import LibraryId, TrackId
from omym2.shared.pagination import MAX_PAGE_LIMIT

if TYPE_CHECKING:
    from pathlib import Path

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CONTENT_HASH = "content"
METADATA_HASH = "metadata"
ERROR_STATUS_CODE = 400
SERVER_ERROR_STATUS_CODE = 500
SUCCESS_STATUS_CODE = 200
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345680"))
SECOND_TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345681"))
THIRD_TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345682"))
FOURTH_TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345683"))
FIFTH_TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345684"))
FIVE_TRACK_TOTAL = 5
THREE_TRACK_STATUS_TOTAL = 3
TWO_TRACK_GROUP_TOTAL = 2
TWO_ITEM_LIMIT = 2
CLAMPED_LIMIT_REQUEST = 1000


class _JsonResponse(Protocol):
    def json(self) -> object: ...


def test_tracks_api_paginates_forward_with_keyset_cursor_and_terminates(tmp_path: Path) -> None:
    """A limit=2 walk over 5 Tracks visits every Track once, in order, then next_cursor is null."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    track_ids = (TRACK_ID, SECOND_TRACK_ID, THIRD_TRACK_ID, FOURTH_TRACK_ID, FIFTH_TRACK_ID)
    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        uow.libraries.save(_library(str(library_root)))
        for index, track_id in enumerate(track_ids):
            uow.tracks.save(_track(track_id, current_path=f"{index}/Title.flac"))
        uow.commit()
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    visited: list[str] = []
    cursor: str | None = None
    last_page: dict[str, object] | None = None
    for _ in range(len(track_ids) + 1):
        params = {"limit": str(TWO_ITEM_LIMIT)} | ({"cursor": cursor} if cursor else {})
        response = client.get(WEB_API_TRACKS_ROUTE, params=params)
        assert response.status_code == SUCCESS_STATUS_CODE
        payload = _json_payload(response)
        items = _object_list_payload(payload, "items")
        page = _object_payload(payload, "page")
        visited.extend(cast("str", item["track_id"]) for item in items)
        assert page["total"] == FIVE_TRACK_TOTAL
        assert page["limit"] == TWO_ITEM_LIMIT
        last_page = page
        next_cursor = page["next_cursor"]
        if next_cursor is None:
            break
        cursor = cast("str", next_cursor)

    assert visited == [str(track_id) for track_id in track_ids]
    assert len(visited) == len(set(visited))
    assert last_page is not None
    assert last_page["next_cursor"] is None


def test_tracks_api_filters_by_status(tmp_path: Path) -> None:
    """The status filter only returns Tracks with a matching status."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        uow.libraries.save(_library(str(library_root)))
        uow.tracks.save(_track(TRACK_ID, current_path="A/1.flac", status=TrackStatus.ACTIVE))
        uow.tracks.save(_track(SECOND_TRACK_ID, current_path="B/1.flac", status=TrackStatus.REMOVED))
        uow.commit()
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_API_TRACKS_ROUTE, params={"status": "removed"})

    assert response.status_code == SUCCESS_STATUS_CODE
    payload = _json_payload(response)
    items = _object_list_payload(payload, "items")
    assert [item["track_id"] for item in items] == [str(SECOND_TRACK_ID)]


def test_tracks_api_search_escapes_like_wildcards(tmp_path: Path) -> None:
    """Search treats literal % and _ characters in the query as literal, not SQL wildcards."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        uow.libraries.save(_library(str(library_root)))
        uow.tracks.save(
            _track(
                TRACK_ID,
                current_path="A/1.flac",
                metadata=TrackMetadata(title="50% Off_Deal", artist="Artist", album="Album"),
            )
        )
        uow.tracks.save(
            _track(
                SECOND_TRACK_ID,
                current_path="B/1.flac",
                metadata=TrackMetadata(title="50X OffXDeal", artist="Artist", album="Album"),
            )
        )
        uow.commit()
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_API_TRACKS_ROUTE, params={"query": "50% Off_Deal"})

    assert response.status_code == SUCCESS_STATUS_CODE
    payload = _json_payload(response)
    items = _object_list_payload(payload, "items")
    assert [item["track_id"] for item in items] == [str(TRACK_ID)]


def test_tracks_api_rejects_invalid_cursor(tmp_path: Path) -> None:
    """An undecodable cursor returns the documented 400 invalid-cursor envelope."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_API_TRACKS_ROUTE, params={"cursor": "not-valid-base64url!!"})

    assert response.status_code == ERROR_STATUS_CODE
    assert response.json() == {"items": [], "page": None, "errors": ["Invalid cursor."]}


def test_tracks_api_rejects_invalid_status_filter(tmp_path: Path) -> None:
    """An unknown status filter value returns a 400 with items/page emptied."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_API_TRACKS_ROUTE, params={"status": "not-a-status"})

    assert response.status_code == ERROR_STATUS_CODE
    payload = _json_payload(response)
    assert payload["items"] == []
    assert payload["page"] is None
    assert payload["errors"] == ["Invalid track status filter: not-a-status"]


def test_tracks_api_rejects_limit_below_one(tmp_path: Path) -> None:
    """limit=0 is a request error, not a silently substituted default."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_API_TRACKS_ROUTE, params={"limit": "0"})

    assert response.status_code == ERROR_STATUS_CODE
    payload = _json_payload(response)
    assert payload["items"] == []
    assert payload["page"] is None


def test_tracks_api_clamps_limit_above_maximum(tmp_path: Path) -> None:
    """A limit above 500 is clamped down to 500, not rejected."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_API_TRACKS_ROUTE, params={"limit": str(CLAMPED_LIMIT_REQUEST)})

    assert response.status_code == SUCCESS_STATUS_CODE
    payload = _json_payload(response)
    page = _object_payload(payload, "page")
    assert page["limit"] == MAX_PAGE_LIMIT


def test_track_facets_api_returns_status_counts(tmp_path: Path) -> None:
    """Facets returns status value/count pairs ordered count DESC then value ASC, plus total."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        uow.libraries.save(_library(str(library_root)))
        uow.tracks.save(_track(TRACK_ID, current_path="A/1.flac", status=TrackStatus.ACTIVE))
        uow.tracks.save(_track(SECOND_TRACK_ID, current_path="B/1.flac", status=TrackStatus.ACTIVE))
        uow.tracks.save(_track(THIRD_TRACK_ID, current_path="C/1.flac", status=TrackStatus.REMOVED))
        uow.commit()
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_API_TRACKS_FACETS_ROUTE)

    assert response.status_code == SUCCESS_STATUS_CODE
    payload = _json_payload(response)
    facets = _object_payload(payload, "facets")
    assert facets["status"] == [
        {"value": TrackStatus.ACTIVE.value, "count": 2},
        {"value": TrackStatus.REMOVED.value, "count": 1},
    ]
    assert payload["total"] == THREE_TRACK_STATUS_TOTAL
    assert payload["errors"] == []


def test_track_groups_api_returns_ordered_groups_with_keyset(tmp_path: Path) -> None:
    """Groups are ordered count DESC/key ASC, and the (count, key) keyset walks every group once."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        uow.libraries.save(_library(str(library_root)))
        uow.tracks.save(_track(TRACK_ID, current_path="A/1.flac", metadata=TrackMetadata(artist="Nova", album="Dawn")))
        uow.tracks.save(
            _track(SECOND_TRACK_ID, current_path="A/2.flac", metadata=TrackMetadata(artist="Nova", album="Dawn"))
        )
        uow.tracks.save(
            _track(
                THIRD_TRACK_ID,
                current_path="B/1.flac",
                metadata=TrackMetadata(album_artist="Echo Collective", artist="Echo", album="Dusk"),
            )
        )
        uow.commit()
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    first_response = client.get(
        WEB_API_TRACKS_GROUPS_ROUTE,
        params={"group_by": "artist_album", "limit": "1"},
    )

    assert first_response.status_code == SUCCESS_STATUS_CODE
    first_payload = _json_payload(first_response)
    assert first_payload["group_by"] == "artist_album"
    first_items = _object_list_payload(first_payload, "items")
    assert first_items == [{"key": "Nova\x1fDawn", "label": "Nova — Dawn", "count": 2}]
    first_page = _object_payload(first_payload, "page")
    assert first_page["total"] == TWO_TRACK_GROUP_TOTAL
    next_cursor = first_page["next_cursor"]
    assert next_cursor is not None

    second_response = client.get(
        WEB_API_TRACKS_GROUPS_ROUTE,
        params={"group_by": "artist_album", "limit": "1", "cursor": cast("str", next_cursor)},
    )

    assert second_response.status_code == SUCCESS_STATUS_CODE
    second_payload = _json_payload(second_response)
    second_items = _object_list_payload(second_payload, "items")
    assert second_items == [{"key": "Echo Collective\x1fDusk", "label": "Echo Collective — Dusk", "count": 1}]
    second_page = _object_payload(second_payload, "page")
    assert second_page["next_cursor"] is None


def test_track_groups_api_rejects_invalid_group_by(tmp_path: Path) -> None:
    """An unknown group_by value returns a 400 with items/page emptied and group_by null."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_API_TRACKS_GROUPS_ROUTE, params={"group_by": "not-a-grouping"})

    assert response.status_code == ERROR_STATUS_CODE
    payload = _json_payload(response)
    assert payload["group_by"] is None
    assert payload["items"] == []
    assert payload["page"] is None
    assert payload["errors"] == ["Invalid group_by filter: not-a-grouping"]


def test_track_groups_api_requires_group_by(tmp_path: Path) -> None:
    """A missing group_by value is a request error, not a silent default."""
    app_paths = default_application_paths(tmp_path)
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_API_TRACKS_GROUPS_ROUTE)

    assert response.status_code == ERROR_STATUS_CODE
    assert response.json()["errors"] == ["Query parameter group_by is required."]


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


def _library(library_root: str) -> Library:
    return Library(
        library_id=LIBRARY_ID,
        root_path=library_root,
        path_policy_hash=calculate_path_policy_fingerprint(
            default_app_config().path_policy,
            default_app_config().artist_ids,
        ),
        registered_at=BASE_TIME,
        status=LibraryStatus.REGISTERED,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _track(
    track_id: TrackId,
    *,
    current_path: str,
    status: TrackStatus = TrackStatus.ACTIVE,
    metadata: TrackMetadata | None = None,
) -> Track:
    return Track(
        track_id=track_id,
        library_id=LIBRARY_ID,
        current_path=current_path,
        canonical_path=current_path,
        content_hash=CONTENT_HASH,
        metadata_hash=METADATA_HASH,
        metadata=TrackMetadata(title="Title", artist="Artist", album="Album") if metadata is None else metadata,
        status=status,
        first_seen_at=BASE_TIME,
        last_seen_at=BASE_TIME,
        updated_at=BASE_TIME,
    )
