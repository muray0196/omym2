"""
Summary: Tests Web execution mutations against real lock and SQLite adapters.
Why: Proves synchronous preflight and Apply/Cancel race responses before dispatch.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Never, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from omym2.adapters.artist_ids.musicbrainz_artist_lookup import MusicBrainzArtistLookup
from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.config.default_config import default_app_config
from omym2.adapters.config.toml_config_store import TomlConfigStore
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.adapters.metadata.mutagen_reader import MutagenMetadataReader
from omym2.adapters.web.app import create_web_app
from omym2.config import (
    HTTP_ACCEPTED_STATUS,
    HTTP_CONFLICT_STATUS,
    HTTP_NOT_FOUND_STATUS,
    HTTP_OK_STATUS,
    WEB_API_ADD_PLAN_ROUTE,
    WEB_API_APPLY_PLAN_ROUTE,
    WEB_API_CANCEL_PLAN_ROUTE,
    WEB_API_RUN_DETAIL_ROUTE,
    WEB_API_RUN_EVENTS_ROUTE,
    WEB_API_UNDO_PLAN_ROUTE,
    WEB_CSRF_HEADER_NAME,
    WEB_IDEMPOTENCY_HEADER_NAME,
)
from omym2.domain.models.artist_name_resolution import ArtistNameResolutionProvenance
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.artist_name import derive_artist_name_source_key
from omym2.domain.services.config_fingerprint import calculate_path_policy_fingerprint
from omym2.domain.services.content_fingerprint import calculate_content_fingerprint
from omym2.domain.services.metadata_fingerprint import calculate_metadata_fingerprint
from omym2.features.apply.usecases.apply_plan import TARGET_EXISTS_MOVE_FAILURE_MESSAGE
from omym2.features.artist_names.dto import (
    ArtistLanguagePrediction,
    ArtistNameProviderCandidate,
    ArtistNameSearchResult,
)
from omym2.features.common_ports import ExclusiveOperationRequest
from omym2.platform.runtime_context import runtime_context_for
from omym2.platform.web_composition import build_api_route_context
from omym2.shared.ids import ActionId, LibraryId, PlanId, RunId

if TYPE_CHECKING:
    from pathlib import Path

    from omym2.features.common_ports import FileSystemPath

NOW = datetime(2026, 7, 13, tzinfo=UTC)
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345690"))
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345691"))
RUN_ID = RunId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345692"))
IDEMPOTENCY_KEY = UUID("018f6a4f-3c2d-7b8a-9abc-def012345693")
ACTION_ID = ActionId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345694"))
AUDIO_CONTENT = b"not-real-audio"
APPLY_MODEL_LOAD_MESSAGE = "Apply must not load the automatic artist-name model."
APPLY_PROVIDER_LOOKUP_MESSAGE = "Apply must not contact the artist-name provider."
EXPECTED_RESOLVED_TARGET_PATH = "Hikaru-Utada/2026_Album/1-02_Title.flac"
JAPANESE_ARTIST = "宇多田ヒカル"
MUSICBRAINZ_ARTIST_ID = "4a9af2f1-e4b7-4b7b-a0be-7f3d2e6f8f21"
RESOLVED_ARTIST = "Hikaru Utada"
SENSITIVE_LIBRARY_COMPONENT = "private-owner-token"
SOURCE_PATH = "Incoming/Secret.flac"
TARGET_PATH = "Artist/Existing.flac"


@pytest.mark.parametrize(
    ("route", "plan_status", "expected_code"),
    [
        (WEB_API_APPLY_PLAN_ROUTE, PlanStatus.READY, "operation_in_progress"),
        (WEB_API_CANCEL_PLAN_ROUTE, PlanStatus.READY, "operation_in_progress"),
        (WEB_API_APPLY_PLAN_ROUTE, PlanStatus.APPLYING, "plan_not_ready"),
        (WEB_API_CANCEL_PLAN_ROUTE, PlanStatus.APPLYING, "plan_not_ready"),
    ],
)
def test_apply_and_cancel_distinguish_unrelated_contention_from_a_committed_winner(
    tmp_path: Path,
    route: str,
    plan_status: PlanStatus,
    expected_code: str,
) -> None:
    """A committed claim wins the race, while contention against a ready Plan stays generic."""
    paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _seed_plan(paths.database_file, library_root, plan_status)
    context = build_api_route_context(paths.config_file, paths.database_file)
    client = TestClient(
        create_web_app(context, tmp_path / "missing-static", allowed_hosts=("testserver",)),
        raise_server_exceptions=False,
    )
    owner_runtime = runtime_context_for(paths.config_file, paths.database_file)

    try:
        with owner_runtime.exclusive_operation_lock.hold(ExclusiveOperationRequest(operation_name="race_winner")):
            response = client.post(
                route.format(plan_id=PLAN_ID),
                headers={
                    WEB_CSRF_HEADER_NAME: context.csrf_token,
                    WEB_IDEMPOTENCY_HEADER_NAME: str(IDEMPOTENCY_KEY),
                },
            )
    finally:
        assert context.close_runtime is not None
        context.close_runtime()

    assert response.status_code == HTTP_CONFLICT_STATUS
    assert response.json()["errors"][0]["code"] == expected_code
    with SQLiteUnitOfWork(paths.database_file) as uow:
        persisted = uow.plans.get(PLAN_ID)
    assert persisted is not None
    assert persisted.status is plan_status


def test_undo_preflight_returns_not_found_without_reserving_an_operation(tmp_path: Path) -> None:
    """Undo eligibility is revalidated under the lock before its durable reservation exists."""
    paths = default_application_paths(tmp_path)
    context = build_api_route_context(paths.config_file, paths.database_file)
    client = TestClient(
        create_web_app(context, tmp_path / "missing-static", allowed_hosts=("testserver",)),
        raise_server_exceptions=False,
    )

    try:
        response = client.post(
            WEB_API_UNDO_PLAN_ROUTE.format(run_id=RUN_ID),
            headers={
                WEB_CSRF_HEADER_NAME: context.csrf_token,
                WEB_IDEMPOTENCY_HEADER_NAME: str(IDEMPOTENCY_KEY),
            },
        )
    finally:
        assert context.close_runtime is not None
        context.close_runtime()

    assert response.status_code == HTTP_NOT_FOUND_STATUS
    assert response.json()["errors"][0]["code"] == "run_not_found"
    with SQLiteUnitOfWork(paths.database_file) as uow:
        assert uow.operations.find_by_idempotency_key(IDEMPOTENCY_KEY) is None


def test_apply_route_claims_and_completes_one_durable_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Web Apply uses the atomic claim and returns a pollable run_completed Operation."""
    paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    library_root.mkdir()
    _seed_plan(paths.database_file, library_root, PlanStatus.READY)
    with SQLiteUnitOfWork(paths.database_file) as uow:
        uow.plan_actions.save(
            PlanAction(
                action_id=ACTION_ID,
                plan_id=PLAN_ID,
                library_id=LIBRARY_ID,
                track_id=None,
                action_type=ActionType.SKIP,
                source_path="Artist/source.flac",
                target_path="Artist/source.flac",
                content_hash_at_plan=None,
                metadata_hash_at_plan=None,
                status=ActionStatus.PLANNED,
                reason=None,
                sort_order=1,
            )
        )
        uow.commit()
    _forbid_automatic_artist_name_lookup(
        monkeypatch,
        paths.config_file,
        tmp_path / "apply-must-not-load.ftz",
    )
    context = build_api_route_context(paths.config_file, paths.database_file)
    client = TestClient(
        create_web_app(context, tmp_path / "missing-static", allowed_hosts=("testserver",)),
        raise_server_exceptions=False,
    )

    accepted = client.post(
        WEB_API_APPLY_PLAN_ROUTE.format(plan_id=PLAN_ID),
        headers={
            WEB_CSRF_HEADER_NAME: context.csrf_token,
            WEB_IDEMPOTENCY_HEADER_NAME: str(IDEMPOTENCY_KEY),
        },
    )
    assert context.close_runtime is not None
    context.close_runtime()
    terminal = client.get(accepted.headers["Location"])

    assert accepted.status_code == HTTP_ACCEPTED_STATUS
    assert terminal.status_code == HTTP_OK_STATUS
    terminal_payload = cast("dict[str, object]", terminal.json())
    raw_terminal_data = terminal_payload["data"]
    assert isinstance(raw_terminal_data, dict)
    terminal_data = cast("dict[str, object]", raw_terminal_data)
    raw_result = terminal_data["result"]
    assert isinstance(raw_result, dict)
    result = cast("dict[str, object]", raw_result)
    assert terminal_data["status"] == "succeeded"
    assert result["kind"] == "run_completed"
    with SQLiteUnitOfWork(paths.database_file) as uow:
        plan = uow.plans.get(PLAN_ID)
        action = uow.plan_actions.get(ACTION_ID)
        runs = tuple(uow.runs.list_by_plan(PLAN_ID))
    assert plan is not None
    assert plan.status is PlanStatus.APPLIED
    assert action is not None
    assert action.status is ActionStatus.APPLIED
    assert len(runs) == 1
    assert result["run_id"] == str(runs[0].run_id)


def test_add_route_runtime_opt_in_records_new_musicbrainz_target_and_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Normal Web Add shares the explicit lazy model/provider activation used by CLI."""
    paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    incoming_root = tmp_path / "incoming"
    audio_path = incoming_root / "Title.flac"
    model_path = tmp_path / "lid.176.ftz"
    library_root.mkdir()
    incoming_root.mkdir()
    _ = audio_path.write_bytes(AUDIO_CONTENT)
    _register_library(paths.database_file, library_root)
    provider_calls: list[str] = []

    def read(self: MutagenMetadataReader, path: FileSystemPath) -> TrackMetadata:
        del self
        assert path == audio_path
        return TrackMetadata(
            title="Title",
            artist=JAPANESE_ARTIST,
            album="Album",
            year=2026,
            track_number=2,
            disc_number=1,
        )

    def build_predictor(*, model_path: Path | None = None) -> _JapanesePredictor:
        assert model_path == tmp_path / "lid.176.ftz"
        return _JapanesePredictor()

    def search_artists(_self: MusicBrainzArtistLookup, source_name: str) -> ArtistNameSearchResult:
        provider_calls.append(source_name)
        return ArtistNameSearchResult(
            available=True,
            candidates=(
                ArtistNameProviderCandidate(
                    provider_artist_id=MUSICBRAINZ_ARTIST_ID,
                    score=100,
                    name=RESOLVED_ARTIST,
                ),
            ),
        )

    monkeypatch.setattr(MutagenMetadataReader, "read", read)
    monkeypatch.setattr(
        "omym2.adapters.artist_ids.fasttext_language_detector.FastTextLanguageDetector",
        build_predictor,
    )
    monkeypatch.setattr(MusicBrainzArtistLookup, "search_artists", search_artists)
    _enable_automatic_artist_name_lookup(paths.config_file, model_path)
    context = build_api_route_context(paths.config_file, paths.database_file)
    client = TestClient(
        create_web_app(context, tmp_path / "missing-static", allowed_hosts=("testserver",)),
        raise_server_exceptions=False,
    )

    try:
        accepted = client.post(
            WEB_API_ADD_PLAN_ROUTE,
            json={"source_path": str(incoming_root), "library_id": str(LIBRARY_ID)},
            headers={
                WEB_CSRF_HEADER_NAME: context.csrf_token,
                WEB_IDEMPOTENCY_HEADER_NAME: str(IDEMPOTENCY_KEY),
            },
        )
    finally:
        assert context.close_runtime is not None
        context.close_runtime()

    assert accepted.status_code == HTTP_ACCEPTED_STATUS
    assert provider_calls == [JAPANESE_ARTIST]
    source_key = derive_artist_name_source_key(JAPANESE_ARTIST)
    assert source_key is not None
    with SQLiteUnitOfWork(paths.database_file) as uow:
        plan = uow.plans.list_by_library(LIBRARY_ID)[0]
        action = uow.plan_actions.list_by_plan(plan.plan_id)[0]
        accepted_name = uow.accepted_artist_names.find_by_source_key(source_key)
    assert action.target_path == EXPECTED_RESOLVED_TARGET_PATH
    assert action.artist_name_diagnostics is not None
    assert action.artist_name_diagnostics.artist.resolved_name == RESOLVED_ARTIST
    assert action.artist_name_diagnostics.artist.provenance is ArtistNameResolutionProvenance.NEW_MUSICBRAINZ
    assert accepted_name is not None
    assert accepted_name.resolved_name == RESOLVED_ARTIST


def test_apply_move_failure_redacts_sensitive_path_from_history_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Apply persists and serves stable move diagnostics without raw OS path details."""
    _patch_metadata_reader(monkeypatch)
    paths = default_application_paths(tmp_path)
    library_root = tmp_path / SENSITIVE_LIBRARY_COMPONENT
    source_file = library_root.joinpath(*SOURCE_PATH.split("/"))
    target_file = library_root.joinpath(*TARGET_PATH.split("/"))
    source_file.parent.mkdir(parents=True)
    target_file.parent.mkdir(parents=True)
    _ = source_file.write_bytes(AUDIO_CONTENT)
    _ = target_file.write_bytes(AUDIO_CONTENT)
    _seed_plan(paths.database_file, library_root, PlanStatus.READY)
    with SQLiteUnitOfWork(paths.database_file) as uow:
        uow.plan_actions.save(
            PlanAction(
                action_id=ACTION_ID,
                plan_id=PLAN_ID,
                library_id=LIBRARY_ID,
                track_id=None,
                action_type=ActionType.MOVE,
                source_path=SOURCE_PATH,
                target_path=TARGET_PATH,
                content_hash_at_plan=calculate_content_fingerprint(AUDIO_CONTENT),
                metadata_hash_at_plan=calculate_metadata_fingerprint(TrackMetadata(title="Secret")),
                status=ActionStatus.PLANNED,
                reason=None,
                sort_order=1,
            )
        )
        uow.commit()
    context = build_api_route_context(paths.config_file, paths.database_file)
    client = TestClient(
        create_web_app(context, tmp_path / "missing-static", allowed_hosts=("testserver",)),
        raise_server_exceptions=False,
    )

    try:
        accepted = client.post(
            WEB_API_APPLY_PLAN_ROUTE.format(plan_id=PLAN_ID),
            headers={
                WEB_CSRF_HEADER_NAME: context.csrf_token,
                WEB_IDEMPOTENCY_HEADER_NAME: str(IDEMPOTENCY_KEY),
            },
        )
    finally:
        assert context.close_runtime is not None
        context.close_runtime()

    assert accepted.status_code == HTTP_ACCEPTED_STATUS
    with SQLiteUnitOfWork(paths.database_file) as uow:
        runs = tuple(uow.runs.list_by_plan(PLAN_ID))
    assert len(runs) == 1
    run_id = runs[0].run_id

    run_response = client.get(WEB_API_RUN_DETAIL_ROUTE.format(run_id=run_id))
    events_response = client.get(WEB_API_RUN_EVENTS_ROUTE.format(run_id=run_id))
    run_payload = cast("dict[str, object]", run_response.json())
    run_data = cast("dict[str, object]", run_payload["data"])
    run_resource = cast("dict[str, object]", run_data["run"])
    events_payload = cast("dict[str, object]", events_response.json())
    events_data = cast("dict[str, object]", events_payload["data"])
    event_items = cast("list[dict[str, object]]", events_data["items"])

    assert run_response.status_code == HTTP_OK_STATUS
    assert events_response.status_code == HTTP_OK_STATUS
    assert run_resource["error_summary"] == TARGET_EXISTS_MOVE_FAILURE_MESSAGE
    assert event_items[0]["error_code"] == "target_exists"
    assert event_items[0]["error_message"] == TARGET_EXISTS_MOVE_FAILURE_MESSAGE
    assert SENSITIVE_LIBRARY_COMPONENT not in run_response.text
    assert SENSITIVE_LIBRARY_COMPONENT not in events_response.text


def _seed_plan(database_path: Path, library_root: Path, status: PlanStatus) -> None:
    """Persist the minimum Plan identity needed to exercise lock-contention classification."""
    with SQLiteUnitOfWork(database_path) as uow:
        uow.libraries.save(
            Library(
                library_id=LIBRARY_ID,
                root_path=str(library_root),
                path_policy_hash="path-policy",
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
                status=status,
                created_at=NOW,
                config_hash="config-hash",
                library_root_at_plan=str(library_root),
            )
        )
        uow.commit()


def _patch_metadata_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    def read(self: MutagenMetadataReader, path: FileSystemPath) -> TrackMetadata:
        del self, path
        return TrackMetadata(title="Secret")

    monkeypatch.setattr(MutagenMetadataReader, "read", read)


def _register_library(database_path: Path, library_root: Path) -> None:
    """Persist one registered Library suitable for normal Add planning."""
    config = default_app_config()
    with SQLiteUnitOfWork(database_path) as uow:
        uow.libraries.save(
            Library(
                library_id=LIBRARY_ID,
                root_path=str(library_root),
                path_policy_hash=calculate_path_policy_fingerprint(
                    config.path_policy,
                    config.artist_ids,
                    artist_name_config=config.artist_names,
                ),
                registered_at=NOW,
                status=LibraryStatus.REGISTERED,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        uow.commit()


class _JapanesePredictor:
    """Return the deterministic eligible observation used by composition tests."""

    def predict_language(self, text: str) -> ArtistLanguagePrediction:
        assert text == JAPANESE_ARTIST
        return ArtistLanguagePrediction(label="__label__ja", confidence=0.99, available=True)


def _enable_automatic_artist_name_lookup(config_path: Path, model_path: Path) -> None:
    """Persist the Stage 3 controls used by composition-level naming tests."""
    store = TomlConfigStore(config_path)
    snapshot = store.read_snapshot()
    configured = replace(
        snapshot.config,
        musicbrainz=replace(snapshot.config.musicbrainz, enabled=True),
        fasttext=replace(snapshot.config.fasttext, model_path=str(model_path)),
    )
    _ = store.save(configured, expected_config_revision=snapshot.config_revision)


def _forbid_automatic_artist_name_lookup(
    monkeypatch: pytest.MonkeyPatch,
    config_path: Path,
    model_path: Path,
) -> None:
    """Make any model load or provider request fail the current Apply test."""

    def fail_model_load(*, model_path: Path | None = None) -> Never:
        del model_path
        raise AssertionError(APPLY_MODEL_LOAD_MESSAGE)

    def fail_provider_lookup(_self: MusicBrainzArtistLookup, source_name: str) -> Never:
        del source_name
        raise AssertionError(APPLY_PROVIDER_LOOKUP_MESSAGE)

    _enable_automatic_artist_name_lookup(config_path, model_path)
    monkeypatch.setattr(
        "omym2.adapters.artist_ids.fasttext_language_detector.FastTextLanguageDetector",
        fail_model_load,
    )
    monkeypatch.setattr(MusicBrainzArtistLookup, "search_artists", fail_provider_lookup)
