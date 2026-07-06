"""
Summary: Tests Web Plan review JSON API routes.
Why: Verifies browser Plan creation and inspection without apply wiring.
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
from omym2.adapters.web.app import create_web_app
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
from omym2.shared.ids import ActionId, LibraryId, PlanId, TrackId

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
SUCCESS_STATUS_CODE = 200
NOT_FOUND_STATUS_CODE = 404
SEEDED_ACTION_COUNT = 2
TARGET_PATH = "Artist/2026_Album/1-02_Title.flac"
TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345679"))

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


def test_plans_api_lists_plans_with_filters(tmp_path: Path) -> None:
    """Plans API returns newest-first rows and applies status/type/limit filters."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        uow.libraries.save(_library(str(library_root)))
        uow.plans.save(_plan(str(library_root), plan_type=PlanType.ADD, status=PlanStatus.READY))
        uow.plans.save(
            _plan(
                str(library_root),
                plan_id=SECOND_PLAN_ID,
                plan_type=PlanType.REFRESH,
                status=PlanStatus.APPLIED,
                created_at=datetime(2026, 1, 2, tzinfo=UTC),
            )
        )
        uow.commit()
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(WEB_API_PLANS_ROUTE, params={"status": "ready", "type": "add", "limit": "1"})

    assert response.status_code == SUCCESS_STATUS_CODE
    payload = _json_payload(response)
    rows = _object_list_payload(payload, "plans")
    assert payload["errors"] == []
    assert len(rows) == 1
    assert rows[0]["plan_id"] == str(PLAN_ID)
    assert rows[0]["plan_type"] == PlanType.ADD.value
    assert rows[0]["status"] == PlanStatus.READY.value
    assert rows[0]["summary"] == {"action_count": "2"}


def test_plan_detail_api_returns_actions_and_filters_by_action_status(tmp_path: Path) -> None:
    """Plan detail returns recorded target paths and can narrow actions by status."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _seed_plan_detail(app_paths.database_file, str(library_root))
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(f"{WEB_API_PLANS_ROUTE}/{PLAN_ID}", params={"actions": "blocked"})

    assert response.status_code == SUCCESS_STATUS_CODE
    payload = _json_payload(response)
    detail = _object_payload(payload, "detail")
    plan = _object_payload(detail, "plan")
    actions = _object_list_payload(detail, "actions")
    assert payload["errors"] == []
    assert plan["plan_id"] == str(PLAN_ID)
    assert plan["config_hash"] == calculate_config_fingerprint(AppConfig())
    assert detail["total_action_count"] == SEEDED_ACTION_COUNT
    assert len(actions) == 1
    assert actions[0]["action_id"] == str(BLOCKED_ACTION_ID)
    assert actions[0]["status"] == ActionStatus.BLOCKED.value
    assert actions[0]["reason"] == PlanActionReason.TARGET_EXISTS.value
    assert actions[0]["target_path"] == TARGET_PATH


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


def test_plan_detail_api_rejects_invalid_action_filter(tmp_path: Path) -> None:
    """Plan detail validates action-status query filters before loading actions."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _seed_plan_detail(app_paths.database_file, str(library_root))
    client = TestClient(create_web_app(app_paths.config_file, app_paths.database_file))

    response = client.get(f"{WEB_API_PLANS_ROUTE}/{PLAN_ID}", params={"actions": "moved"})

    assert response.status_code == ERROR_STATUS_CODE
    assert response.json()["detail"] is None
    assert response.json()["errors"] == ["Invalid action status filter: moved"]


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
    actions = _object_list_payload(detail, "actions")
    assert payload["created"] is True
    assert payload["errors"] == []
    assert plan["plan_type"] == PlanType.ADD.value
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
    """Organize Plan creation scans a Library root and returns reviewable actions."""
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
    actions = _object_list_payload(detail, "actions")
    assert payload["created"] is True
    assert payload["errors"] == []
    assert _object_payload(payload, "registration")["track_count"] == 1
    assert plan["plan_type"] == PlanType.ORGANIZE.value
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
    """Refresh Plan creation records relocation actions for managed Tracks."""
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
    actions = _object_list_payload(detail, "actions")
    assert payload["created"] is True
    assert payload["errors"] == []
    assert plan["plan_type"] == PlanType.REFRESH.value
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


def _action(
    *,
    action_id: ActionId,
    status: ActionStatus,
    reason: PlanActionReason | None,
    sort_order: int = 1,
) -> PlanAction:
    return PlanAction(
        action_id=action_id,
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        track_id=None,
        action_type=ActionType.MOVE,
        source_path="/incoming/Title.flac",
        target_path=TARGET_PATH,
        content_hash_at_plan=CONTENT_HASH,
        metadata_hash_at_plan=calculate_metadata_fingerprint(METADATA),
        status=status,
        reason=reason,
        sort_order=sort_order,
    )
