"""
Summary: Tests shared Web and CLI exclusive-operation composition.
Why: Prevents either surface from bypassing cross-process mutation exclusion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import StringIO
from threading import Event, Thread
from typing import TYPE_CHECKING, Never, cast
from uuid import UUID

from fastapi.testclient import TestClient

from omym2.adapters.cli.commands.artist_ids import ArtistIdsCommandDependencies, run_artist_ids_command
from omym2.adapters.config.default_config import default_app_config
from omym2.adapters.config.toml_config_store import TomlConfigStore
from omym2.adapters.web.app import create_web_app
from omym2.adapters.web.routes.api_context import ApiRouteContext, OperationsRouteContext, SettingsRouteContext
from omym2.adapters.web.schemas.settings import AppConfigResource
from omym2.config import (
    HTTP_ACCEPTED_STATUS,
    HTTP_CONFLICT_STATUS,
    HTTP_OK_STATUS,
    OPERATION_RECONCILE_INTERVAL_SECONDS,
    WEB_API_CHECK_RUN_ROUTE,
    WEB_API_SETTINGS_ARTIST_IDS_ROUTE,
    WEB_API_SETTINGS_ROUTE,
    WEB_CSRF_HEADER_NAME,
    WEB_IDEMPOTENCY_HEADER_NAME,
)
from omym2.domain.models.operation import OperationKind
from omym2.features.artist_ids.usecases.generate_artist_id_draft import GenerateArtistIdDraftUseCase
from omym2.platform.artist_ids_composition import artist_ids_command_ports_for
from omym2.platform.operation_composition import OperationRuntime
from omym2.platform.runtime_context import runtime_context_for

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from fastapi import FastAPI
    from httpx2 import Response

    from omym2.domain.models.operation import OperationResult
    from omym2.features.add.dto import CreateAddPlanRequest
    from omym2.features.check.dto import CheckLibraryRequest
    from omym2.features.operations.dto import ReserveOperationResult
    from omym2.features.organize.dto import CreateOrganizePlanRequest
    from omym2.features.refresh.dto import CreateRefreshPlanRequest
    from omym2.features.settings.dto import (
        PathPolicyPreviewRequest,
        PathPolicyPreviewResult,
        SaveSettingsRequest,
        SettingsCandidateResult,
        SettingsEditResult,
        ValidateSettingsRequest,
    )
    from omym2.features.undo.dto import CreateUndoPlanRequest
    from omym2.shared.ids import OperationId, PlanId

CSRF_TOKEN = "web-cli-exclusion-csrf"  # noqa: S105  # Deterministic non-secret test token.
IDEMPOTENCY_KEY = UUID("018f6a4f-3c2d-7b8a-9abc-def012345690")
ARTIST_NAME = "John Smith"
LOCK_BUSY_TEXT = "Another state-changing operation is already in progress."
WEB_WORK_FAILURE_MESSAGE = "Release the synthetic Web worker as a controlled failure."
BLOCKING_DETECTOR_TIMEOUT_MESSAGE = "The blocking CLI detector was not released in time."
UNEXPECTED_CALLBACK_MESSAGE = "The contended callback must not execute."


def test_web_check_blocks_cli_artist_id_config_mutation(tmp_path: Path) -> None:
    """A Web worker retains the shared lease until a CLI Config mutation is rejected."""
    config_path = tmp_path / "config.toml"
    database_path = tmp_path / "state.sqlite3"
    web_runtime_context = runtime_context_for(config_path, database_path)
    cli_runtime_context = runtime_context_for(config_path, database_path)
    web_operations = OperationRuntime(web_runtime_context)
    cli_operations = OperationRuntime(cli_runtime_context)
    worker_started = Event()
    release_worker = Event()

    def blocking_web_work(_operation_id: OperationId) -> OperationResult:
        worker_started.set()
        _ = release_worker.wait(OPERATION_RECONCILE_INTERVAL_SECONDS)
        raise RuntimeError(WEB_WORK_FAILURE_MESSAGE)

    app = _web_app(web_operations, blocking_web_work, tmp_path)
    try:
        with TestClient(app, base_url="http://localhost") as client:
            try:
                accepted = client.post(
                    WEB_API_CHECK_RUN_ROUTE,
                    json={"library_id": None},
                    headers=_mutation_headers(),
                )
                assert accepted.status_code == HTTP_ACCEPTED_STATUS
                assert worker_started.wait(OPERATION_RECONCILE_INTERVAL_SECONDS)

                stdout = StringIO()
                stderr = StringIO()
                exit_code = run_artist_ids_command(
                    ["generate", ARTIST_NAME],
                    stdout,
                    stderr,
                    artist_ids_command_ports_for(cli_runtime_context, cli_operations),
                    ArtistIdsCommandDependencies(
                        language_detector=_NonJapaneseDetector(),
                        artist_resolver=_NoopArtistResolver(),
                    ),
                )

                assert exit_code == 1
                assert stdout.getvalue() == ""
                assert LOCK_BUSY_TEXT in stderr.getvalue()
                assert not config_path.exists()
            finally:
                release_worker.set()
    finally:
        cli_operations.close()


def test_cli_artist_id_mutation_blocks_web_mutations_but_not_draft(tmp_path: Path) -> None:
    """A CLI lease rejects Web Check and Settings save while draft generation remains read-only."""
    config_path = tmp_path / "config.toml"
    database_path = tmp_path / "state.sqlite3"
    cli_runtime_context = runtime_context_for(config_path, database_path)
    web_runtime_context = runtime_context_for(config_path, database_path)
    cli_operations = OperationRuntime(cli_runtime_context)
    web_operations = OperationRuntime(web_runtime_context)
    detector = _BlockingNonJapaneseDetector()
    stdout = StringIO()
    stderr = StringIO()
    exit_codes: list[int] = []

    def run_cli_mutation() -> None:
        exit_codes.append(
            run_artist_ids_command(
                ["generate", ARTIST_NAME],
                stdout,
                stderr,
                artist_ids_command_ports_for(cli_runtime_context, cli_operations),
                ArtistIdsCommandDependencies(
                    language_detector=detector,
                    artist_resolver=_NoopArtistResolver(),
                ),
            )
        )

    cli_thread = Thread(target=run_cli_mutation, name="test-cli-artist-id-mutation")
    cli_thread.start()
    assert detector.entered.wait(OPERATION_RECONCILE_INTERVAL_SECONDS)

    app = _web_app(web_operations, _unexpected_work, tmp_path)
    with TestClient(app, base_url="http://localhost") as client:
        try:
            check_response = client.post(
                WEB_API_CHECK_RUN_ROUTE,
                json={"library_id": None},
                headers=_mutation_headers(),
            )
            settings_response = client.put(
                WEB_API_SETTINGS_ROUTE,
                json={
                    "config": AppConfigResource.from_domain(default_app_config()).model_dump(mode="json"),
                    "expected_config_revision": "v1:test-edit-base",
                },
                headers={WEB_CSRF_HEADER_NAME: CSRF_TOKEN},
            )
            draft_response = client.post(
                WEB_API_SETTINGS_ARTIST_IDS_ROUTE,
                json={
                    "artist_names": [ARTIST_NAME],
                    "overwrite": False,
                    "artist_ids": AppConfigResource.from_domain(default_app_config()).artist_ids.model_dump(
                        mode="json"
                    ),
                },
            )

            assert check_response.status_code == HTTP_CONFLICT_STATUS
            assert _first_error(check_response)["code"] == "operation_in_progress"
            assert settings_response.status_code == HTTP_CONFLICT_STATUS
            assert _first_error(settings_response)["code"] == "operation_in_progress"
            assert draft_response.status_code == HTTP_OK_STATUS
            draft_data = _data(draft_response)
            assert cast("list[dict[str, object]]", draft_data["entries"])[0]["source_artist"] == ARTIST_NAME
        finally:
            detector.release.set()
            cli_thread.join(timeout=OPERATION_RECONCILE_INTERVAL_SECONDS)

    cli_operations.close()
    assert not cli_thread.is_alive()
    assert exit_codes == [0]
    assert stderr.getvalue() == ""
    assert TomlConfigStore(config_path).load().artist_ids.entries == {ARTIST_NAME: "JOHNSMTH"}


def _web_app(
    operations: OperationRuntime,
    check_work: Callable[[OperationId], OperationResult],
    tmp_path: Path,
) -> FastAPI:
    def start_check(request: CheckLibraryRequest, idempotency_key: UUID) -> ReserveOperationResult:
        return operations.accept(
            kind=OperationKind.CHECK,
            idempotency_key=idempotency_key,
            canonical_request={"library_id": request.library_id},
            library_id=request.library_id,
            work=check_work,
        )

    def save_settings(_request: SaveSettingsRequest) -> SettingsCandidateResult:
        return operations.execute_exclusive("save_settings", _unexpected_settings_save)

    context = ApiRouteContext(
        csrf_token=CSRF_TOKEN,
        get_bootstrap=_unexpected_bootstrap,
        settings=SettingsRouteContext(
            get_settings=_unexpected_get_settings,
            validate_settings=_unexpected_validate_settings,
            preview_path_policy=_unexpected_preview,
            save_settings=save_settings,
            generate_artist_id_draft=GenerateArtistIdDraftUseCase(
                language_detector=_NonJapaneseDetector(),
                artist_resolver=_NoopArtistResolver(),
            ).execute,
        ),
        operations=OperationsRouteContext(
            get_operation=operations.get,
            active_operation_id=operations.active_operation_id,
            start_add_plan=_unexpected_add,
            start_organize_plan=_unexpected_organize,
            start_refresh_plan=_unexpected_refresh,
            start_check=start_check,
            start_apply_plan=_unexpected_apply,
            start_undo_plan=_unexpected_undo,
        ),
        start_runtime=operations.start,
        close_runtime=operations.close,
    )
    return create_web_app(context, tmp_path / "missing-static")


def _mutation_headers() -> dict[str, str]:
    return {
        WEB_CSRF_HEADER_NAME: CSRF_TOKEN,
        WEB_IDEMPOTENCY_HEADER_NAME: str(IDEMPOTENCY_KEY),
    }


def _unexpected_work(_operation_id: OperationId) -> OperationResult:
    raise AssertionError(UNEXPECTED_CALLBACK_MESSAGE)


def _unexpected_bootstrap() -> Never:
    raise AssertionError(UNEXPECTED_CALLBACK_MESSAGE)


def _unexpected_get_settings() -> SettingsEditResult:
    raise AssertionError(UNEXPECTED_CALLBACK_MESSAGE)


def _unexpected_validate_settings(_request: ValidateSettingsRequest) -> SettingsCandidateResult:
    raise AssertionError(UNEXPECTED_CALLBACK_MESSAGE)


def _unexpected_preview(_request: PathPolicyPreviewRequest) -> PathPolicyPreviewResult:
    raise AssertionError(UNEXPECTED_CALLBACK_MESSAGE)


def _unexpected_settings_save() -> SettingsCandidateResult:
    raise AssertionError(UNEXPECTED_CALLBACK_MESSAGE)


def _unexpected_add(_request: CreateAddPlanRequest, _key: UUID) -> ReserveOperationResult:
    raise AssertionError(UNEXPECTED_CALLBACK_MESSAGE)


def _unexpected_organize(_request: CreateOrganizePlanRequest, _key: UUID) -> ReserveOperationResult:
    raise AssertionError(UNEXPECTED_CALLBACK_MESSAGE)


def _unexpected_refresh(_request: CreateRefreshPlanRequest, _key: UUID) -> ReserveOperationResult:
    raise AssertionError(UNEXPECTED_CALLBACK_MESSAGE)


def _unexpected_apply(_plan_id: PlanId, _key: UUID) -> ReserveOperationResult:
    raise AssertionError(UNEXPECTED_CALLBACK_MESSAGE)


def _unexpected_undo(_request: CreateUndoPlanRequest, _key: UUID) -> ReserveOperationResult:
    raise AssertionError(UNEXPECTED_CALLBACK_MESSAGE)


def _response_object(response: Response) -> dict[str, object]:
    return cast("dict[str, object]", response.json())


def _data(response: Response) -> dict[str, object]:
    data = _response_object(response)["data"]
    assert isinstance(data, dict)
    return cast("dict[str, object]", data)


def _first_error(response: Response) -> dict[str, object]:
    errors = _response_object(response)["errors"]
    assert isinstance(errors, list)
    return cast("dict[str, object]", errors[0])


@dataclass(frozen=True, slots=True)
class _NonJapaneseDetector:
    def is_japanese(self, text: str) -> bool:
        del text
        return False


@dataclass(slots=True)
class _BlockingNonJapaneseDetector:
    entered: Event = field(default_factory=Event)
    release: Event = field(default_factory=Event)

    def is_japanese(self, text: str) -> bool:
        del text
        self.entered.set()
        if not self.release.wait(OPERATION_RECONCILE_INTERVAL_SECONDS):
            raise AssertionError(BLOCKING_DETECTOR_TIMEOUT_MESSAGE)
        return False


@dataclass(frozen=True, slots=True)
class _NoopArtistResolver:
    def english_or_latin_name(self, source_artist: str) -> str | None:
        del source_artist
        return None
