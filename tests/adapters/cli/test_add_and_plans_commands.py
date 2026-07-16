"""
Summary: Tests add and plans CLI command behavior.
Why: Verifies add Plan creation, inspection, and apply orchestration.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import UTC, datetime
from io import StringIO
from typing import TYPE_CHECKING, Never, override
from uuid import UUID

from omym2.adapters.artist_ids.musicbrainz_artist_lookup import MusicBrainzArtistLookup
from omym2.adapters.cli.commands.add import AddCommandDependencies, run_add_command
from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.config.default_config import default_app_config
from omym2.adapters.config.toml_config_store import TomlConfigStore
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.adapters.metadata.mutagen_reader import MutagenMetadataReader
from omym2.domain.models.artist_name_resolution import ArtistNameResolutionProvenance
from omym2.domain.models.file_event import FileEventStatus
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.plan import Plan, PlanStatus, PlanType
from omym2.domain.models.plan_action import ActionStatus, ActionType, PlanAction
from omym2.domain.models.run import RunStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.domain.services.artist_name import derive_artist_name_source_key
from omym2.domain.services.config_fingerprint import calculate_path_policy_fingerprint
from omym2.features.add.dto import CreateAddPlanRequest
from omym2.features.add.usecases.create_add_plan import (
    SUMMARY_MOVE_ACTIONS_KEY,
    SUMMARY_UNPROCESSED_PREVIEW_LIMIT_KEY,
)
from omym2.features.artist_names.dto import (
    ArtistLanguagePrediction,
    ArtistNameProviderCandidate,
    ArtistNameSearchResult,
)
from omym2.platform.cli_entry_point import run_cli as main
from omym2.shared.ids import ActionId, LibraryId, PlanId

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from omym2.features.common_ports import FileSystemPath

AUDIO_CONTENT = b"fake audio bytes"
ACTION_IDS = tuple(
    ActionId(UUID(value))
    for value in (
        "018f6a4f-3c2d-7b8a-9abc-def01234567a",
        "018f6a4f-3c2d-7b8a-9abc-def01234567b",
        "018f6a4f-3c2d-7b8a-9abc-def01234567c",
    )
)
APPLY_MODEL_LOAD_MESSAGE = "Apply must not load the automatic artist-name model."
APPLY_PROVIDER_LOOKUP_MESSAGE = "Apply must not contact the artist-name provider."
BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CONFIG_HASH = "config-hash"
EXPECTED_CANONICAL_PATH = "Artist/2026_Album/1-02_Title.flac"
EXPECTED_RESOLVED_CANONICAL_PATH = "Hikaru-Utada/2026_Album/1-02_Title.flac"
ERROR_EXIT_CODE = 1
JAPANESE_ARTIST = "宇多田ヒカル"
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
LIBRARY_ROOT = "/library"
NORMALIZED_SOURCE_PATH = "normalized:incoming"
PLAN_ID = PlanId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345679"))
RAW_SOURCE_PATH = "incoming"
SUCCESS_EXIT_CODE = 0
TITLE = "Title"
TRACK_ALBUM = "Album"
TRACK_ARTIST = "Artist"
MUSICBRAINZ_ARTIST_ID = "4a9af2f1-e4b7-4b7b-a0be-7f3d2e6f8f21"
RESOLVED_ARTIST = "Hikaru Utada"
UNEXPECTED_STDIN_READ_MESSAGE = "stdin should not be read"
YEAR = 2026


def test_add_command_passes_normalized_source_path_to_request() -> None:
    """add delegates source normalization before creating the usecase request."""
    captured_requests: list[CreateAddPlanRequest] = []

    class CapturingCreateAddPlanUseCase:
        """Usecase test double that records the inbound request."""

        def __init__(self, ports: object) -> None:
            """Accept the injected ports without using them."""
            del ports

        def execute(self, request: CreateAddPlanRequest) -> Plan:
            """Capture the request and return an empty add Plan."""
            captured_requests.append(request)
            return _empty_plan(PlanType.ADD)

    stdout = StringIO()
    stderr = StringIO()

    exit_code = run_add_command(
        [RAW_SOURCE_PATH],
        stdout,
        stderr,
        AddCommandDependencies(
            create_add_plan=CapturingCreateAddPlanUseCase(object()).execute,
            apply_plan=_unexpected_apply,
            normalize_source_path=lambda path: f"normalized:{path}",
        ),
    )

    assert exit_code == SUCCESS_EXIT_CODE
    assert captured_requests == [CreateAddPlanRequest(source_path=NORMALIZED_SOURCE_PATH)]


def test_add_command_previews_only_the_deterministic_unprocessed_limit() -> None:
    """CLI output truncates presentation while the returned Plan still carries every action."""
    actions = tuple(
        PlanAction(
            action_id=action_id,
            plan_id=PLAN_ID,
            library_id=LIBRARY_ID,
            track_id=None,
            action_type=ActionType.MOVE_UNPROCESSED,
            source_path=f"/incoming/{name}.txt",
            target_path=f"/incoming/Unprocessed/{name}.txt",
            content_hash_at_plan=f"hash-{name}",
            metadata_hash_at_plan=None,
            status=ActionStatus.PLANNED,
            reason=None,
            sort_order=sort_order,
        )
        for action_id, name, sort_order in zip(
            ACTION_IDS,
            ("c", "a", "b"),
            (30, 10, 20),
            strict=True,
        )
    )
    plan = replace(
        _empty_plan(PlanType.ADD),
        summary={"unprocessed_preview_limit": "2"},
        actions=actions,
    )
    stdout = StringIO()
    stderr = StringIO()

    exit_code = run_add_command(
        [],
        stdout,
        stderr,
        AddCommandDependencies(
            create_add_plan=lambda _request: plan,
            apply_plan=_unexpected_apply,
            normalize_source_path=str,
        ),
    )

    assert exit_code == SUCCESS_EXIT_CODE
    assert stderr.getvalue() == ""
    assert stdout.getvalue().splitlines()[-4:] == [
        "unprocessed_actions: 3",
        "unprocessed: /incoming/a.txt -> /incoming/Unprocessed/a.txt",
        "unprocessed: /incoming/b.txt -> /incoming/Unprocessed/b.txt",
        "unprocessed_truncated: 1",
    ]
    assert len(plan.actions) == len(ACTION_IDS)


def test_add_command_reports_all_planned_mutation_types_as_moves() -> None:
    """CLI move count matches the authoritative mixed Add Plan summary."""
    action_types = (ActionType.MOVE, ActionType.MOVE_LYRICS, ActionType.MOVE_UNPROCESSED)
    actions = tuple(
        PlanAction(
            action_id=action_id,
            plan_id=PLAN_ID,
            library_id=LIBRARY_ID,
            track_id=None,
            action_type=action_type,
            source_path=f"/incoming/source-{sort_order}",
            target_path=f"target-{sort_order}",
            content_hash_at_plan=f"hash-{sort_order}",
            metadata_hash_at_plan=None,
            status=ActionStatus.PLANNED,
            reason=None,
            sort_order=sort_order,
        )
        for action_id, action_type, sort_order in zip(ACTION_IDS, action_types, (1, 2, 3), strict=True)
    )
    plan = replace(
        _empty_plan(PlanType.ADD),
        summary={
            SUMMARY_MOVE_ACTIONS_KEY: str(len(actions)),
            SUMMARY_UNPROCESSED_PREVIEW_LIMIT_KEY: "0",
        },
        actions=actions,
    )
    stdout = StringIO()
    stderr = StringIO()

    exit_code = run_add_command(
        [],
        stdout,
        stderr,
        AddCommandDependencies(
            create_add_plan=lambda _request: plan,
            apply_plan=_unexpected_apply,
            normalize_source_path=str,
        ),
    )

    assert exit_code == SUCCESS_EXIT_CODE
    assert stderr.getvalue() == ""
    assert stdout.getvalue().splitlines() == [
        f"Add plan created: {PLAN_ID}",
        "actions: 3",
        "move_actions: 3",
        "skip_actions: 0",
        "blocked_actions: 0",
        "unprocessed_actions: 1",
        "unprocessed_truncated: 1",
    ]


def test_add_command_creates_plan_and_plans_command_displays_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """add creates a Plan that plans list/detail can inspect."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    incoming_root = tmp_path / "incoming"
    audio_path = incoming_root / "Title.flac"
    library_root.mkdir()
    incoming_root.mkdir()
    _ = audio_path.write_bytes(AUDIO_CONTENT)
    _register_library(app_paths.database_file, str(library_root))
    add_stdout = StringIO()
    add_stderr = StringIO()

    def read(self: MutagenMetadataReader, path: FileSystemPath) -> TrackMetadata:
        del self
        assert path == audio_path
        return TrackMetadata(
            title=TITLE,
            artist=TRACK_ARTIST,
            album=TRACK_ALBUM,
            year=YEAR,
            track_number=2,
            disc_number=1,
        )

    monkeypatch.setattr(MutagenMetadataReader, "read", read)
    monkeypatch.setattr(sys, "stdin", UnreadableInput())

    add_exit_code = main(
        ["add", str(incoming_root)],
        stdout=add_stdout,
        stderr=add_stderr,
        config_path=app_paths.config_file,
        database_path=app_paths.database_file,
    )

    assert add_exit_code == SUCCESS_EXIT_CODE
    assert "Add plan created:" in add_stdout.getvalue()
    assert "actions: 1" in add_stdout.getvalue()
    assert add_stderr.getvalue() == ""

    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        plans = uow.plans.list_by_library(LIBRARY_ID)
        assert len(plans) == 1
        plan = plans[0]
        actions = uow.plan_actions.list_by_plan(plan.plan_id)
        assert plan.plan_type == PlanType.ADD
        assert len(actions) == 1
        assert actions[0].action_type == ActionType.MOVE
        assert actions[0].status == ActionStatus.PLANNED
        assert actions[0].target_path == EXPECTED_CANONICAL_PATH

    list_stdout = StringIO()
    list_stderr = StringIO()
    list_exit_code = main(
        ["plans"],
        stdout=list_stdout,
        stderr=list_stderr,
        database_path=app_paths.database_file,
    )

    assert list_exit_code == SUCCESS_EXIT_CODE
    assert str(plan.plan_id) in list_stdout.getvalue()
    assert "type=add" in list_stdout.getvalue()
    assert list_stderr.getvalue() == ""

    detail_stdout = StringIO()
    detail_stderr = StringIO()
    detail_exit_code = main(
        ["plans", str(plan.plan_id)],
        stdout=detail_stdout,
        stderr=detail_stderr,
        database_path=app_paths.database_file,
    )

    assert detail_exit_code == SUCCESS_EXIT_CODE
    assert f"plan_id: {plan.plan_id}" in detail_stdout.getvalue()
    assert f"target_path: {EXPECTED_CANONICAL_PATH}" in detail_stdout.getvalue()
    assert detail_stderr.getvalue() == ""


def test_add_command_persisted_opt_in_records_new_musicbrainz_target_and_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Normal CLI Add uses the shared lazy model/provider path after persisted opt-in."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    incoming_root = tmp_path / "incoming"
    audio_path = incoming_root / "Title.flac"
    model_path = tmp_path / "lid.176.ftz"
    library_root.mkdir()
    incoming_root.mkdir()
    _ = audio_path.write_bytes(AUDIO_CONTENT)
    _register_library(app_paths.database_file, str(library_root))
    provider_calls: list[str] = []

    def read(self: MutagenMetadataReader, path: FileSystemPath) -> TrackMetadata:
        del self
        assert path == audio_path
        return TrackMetadata(
            title=TITLE,
            artist=JAPANESE_ARTIST,
            album=TRACK_ALBUM,
            year=YEAR,
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
    _enable_automatic_artist_name_lookup(app_paths.config_file, model_path)

    exit_code = main(
        ["add", str(incoming_root)],
        stdout=StringIO(),
        stderr=StringIO(),
        config_path=app_paths.config_file,
        database_path=app_paths.database_file,
    )

    assert exit_code == SUCCESS_EXIT_CODE
    assert provider_calls == [JAPANESE_ARTIST]
    source_key = derive_artist_name_source_key(JAPANESE_ARTIST)
    assert source_key is not None
    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        plan = uow.plans.list_by_library(LIBRARY_ID)[0]
        action = uow.plan_actions.list_by_plan(plan.plan_id)[0]
        accepted_name = uow.accepted_artist_names.find_by_source_key(source_key)
    assert action.target_path == EXPECTED_RESOLVED_CANONICAL_PATH
    assert action.artist_name_diagnostics is not None
    assert action.artist_name_diagnostics.artist.resolved_name == RESOLVED_ARTIST
    assert action.artist_name_diagnostics.artist.provenance is ArtistNameResolutionProvenance.NEW_MUSICBRAINZ
    assert accepted_name is not None
    assert accepted_name.resolved_name == RESOLVED_ARTIST


def test_apply_command_applies_existing_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """apply executes a reviewed Plan created by add."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    incoming_root = tmp_path / "incoming"
    audio_path = incoming_root / "Title.flac"
    library_root.mkdir()
    incoming_root.mkdir()
    _ = audio_path.write_bytes(AUDIO_CONTENT)
    _register_library(app_paths.database_file, str(library_root))

    def read(self: MutagenMetadataReader, path: FileSystemPath) -> TrackMetadata:
        del self
        assert path == audio_path
        return TrackMetadata(
            title=TITLE,
            artist=TRACK_ARTIST,
            album=TRACK_ALBUM,
            year=YEAR,
            track_number=2,
            disc_number=1,
        )

    monkeypatch.setattr(MutagenMetadataReader, "read", read)

    add_exit_code = main(
        ["add", str(incoming_root)],
        stdout=StringIO(),
        stderr=StringIO(),
        config_path=app_paths.config_file,
        database_path=app_paths.database_file,
    )
    assert add_exit_code == SUCCESS_EXIT_CODE

    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        plan = uow.plans.list_by_library(LIBRARY_ID)[0]

    _forbid_automatic_artist_name_lookup(
        monkeypatch,
        app_paths.config_file,
        tmp_path / "apply-must-not-load.ftz",
    )
    apply_stdout = StringIO()
    apply_stderr = StringIO()
    apply_exit_code = main(
        ["apply", str(plan.plan_id), "--yes"],
        stdout=apply_stdout,
        stderr=apply_stderr,
        config_path=app_paths.config_file,
        database_path=app_paths.database_file,
    )

    assert apply_exit_code == SUCCESS_EXIT_CODE
    assert "Apply run completed:" in apply_stdout.getvalue()
    assert "status: succeeded" in apply_stdout.getvalue()
    assert apply_stderr.getvalue() == ""
    assert not audio_path.exists()
    assert library_root.joinpath(*EXPECTED_CANONICAL_PATH.split("/")).is_file()

    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        applied_plan = uow.plans.get(plan.plan_id)
        assert applied_plan is not None
        assert applied_plan.status == PlanStatus.APPLIED
        runs = uow.runs.list_by_plan(plan.plan_id)
        assert len(runs) == 1
        assert runs[0].status == RunStatus.SUCCEEDED
        events = uow.file_events.list_by_run(runs[0].run_id)
        assert len(events) == 1
        assert events[0].status == FileEventStatus.SUCCEEDED
        tracks = uow.tracks.list_by_library(LIBRARY_ID)
        assert len(tracks) == 1
        assert tracks[0].current_path == EXPECTED_CANONICAL_PATH


def test_apply_latest_applies_most_recent_ready_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """apply latest resolves the newest ready Plan before execution."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    incoming_root = tmp_path / "incoming"
    audio_path = incoming_root / "Title.flac"
    library_root.mkdir()
    incoming_root.mkdir()
    _ = audio_path.write_bytes(AUDIO_CONTENT)
    _register_library(app_paths.database_file, str(library_root))

    def read(self: MutagenMetadataReader, path: FileSystemPath) -> TrackMetadata:
        del self
        assert path == audio_path
        return TrackMetadata(
            title=TITLE,
            artist=TRACK_ARTIST,
            album=TRACK_ALBUM,
            year=YEAR,
            track_number=2,
            disc_number=1,
        )

    monkeypatch.setattr(MutagenMetadataReader, "read", read)
    monkeypatch.setattr(sys, "stdin", StringIO("y\n"))

    add_exit_code = main(
        ["add", str(incoming_root)],
        stdout=StringIO(),
        stderr=StringIO(),
        config_path=app_paths.config_file,
        database_path=app_paths.database_file,
    )
    assert add_exit_code == SUCCESS_EXIT_CODE

    apply_stdout = StringIO()
    apply_stderr = StringIO()
    apply_exit_code = main(
        ["apply", "latest"],
        stdout=apply_stdout,
        stderr=apply_stderr,
        database_path=app_paths.database_file,
    )

    assert apply_exit_code == SUCCESS_EXIT_CODE
    assert "status: succeeded" in apply_stdout.getvalue()
    assert apply_stderr.getvalue() == ""
    assert library_root.joinpath(*EXPECTED_CANONICAL_PATH.split("/")).is_file()


def test_apply_command_reports_invalid_plan_id() -> None:
    """apply reports invalid Plan IDs without a traceback."""
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(["apply", "not-a-plan"], stdout=stdout, stderr=stderr)

    assert exit_code == ERROR_EXIT_CODE
    assert stdout.getvalue() == ""
    assert "Invalid Plan ID." in stderr.getvalue()


def test_apply_latest_reports_no_ready_plan(tmp_path: Path) -> None:
    """apply latest reports a clear message when no ready Plan exists."""
    app_paths = default_application_paths(tmp_path)
    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        ["apply", "latest"],
        stdout=stdout,
        stderr=stderr,
        database_path=app_paths.database_file,
    )

    assert exit_code == ERROR_EXIT_CODE
    assert stdout.getvalue() == ""
    assert "No ready Plan exists." in stderr.getvalue()


def test_add_command_apply_creates_and_applies_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """add --apply creates an add Plan and applies it in one command."""
    app_paths = default_application_paths(tmp_path)
    library_root = tmp_path / "library"
    incoming_root = tmp_path / "incoming"
    audio_path = incoming_root / "Title.flac"
    library_root.mkdir()
    incoming_root.mkdir()
    _ = audio_path.write_bytes(AUDIO_CONTENT)
    _register_library(app_paths.database_file, str(library_root))
    stdout = StringIO()
    stderr = StringIO()

    def read(self: MutagenMetadataReader, path: FileSystemPath) -> TrackMetadata:
        del self
        assert path == audio_path
        return TrackMetadata(
            title=TITLE,
            artist=TRACK_ARTIST,
            album=TRACK_ALBUM,
            year=YEAR,
            track_number=2,
            disc_number=1,
        )

    monkeypatch.setattr(MutagenMetadataReader, "read", read)

    exit_code = main(
        ["add", str(incoming_root), "--apply", "--yes"],
        stdout=stdout,
        stderr=stderr,
        config_path=app_paths.config_file,
        database_path=app_paths.database_file,
    )

    assert exit_code == SUCCESS_EXIT_CODE
    assert "Add plan created:" in stdout.getvalue()
    assert "Apply run completed:" in stdout.getvalue()
    assert stderr.getvalue() == ""
    assert not audio_path.exists()
    assert library_root.joinpath(*EXPECTED_CANONICAL_PATH.split("/")).is_file()

    with SQLiteUnitOfWork(app_paths.database_file) as uow:
        plans = uow.plans.list_by_library(LIBRARY_ID)
        assert len(plans) == 1
        assert plans[0].status == PlanStatus.APPLIED


class UnreadableInput(StringIO):
    """Input stream that fails if a command unexpectedly prompts."""

    @override
    def readline(self, size: int = -1) -> str:
        """Raise when a --yes command tries to read confirmation."""
        del size
        raise AssertionError(UNEXPECTED_STDIN_READ_MESSAGE)


def _empty_plan(plan_type: PlanType) -> Plan:
    return Plan(
        plan_id=PLAN_ID,
        library_id=LIBRARY_ID,
        plan_type=plan_type,
        status=PlanStatus.READY,
        created_at=BASE_TIME,
        config_hash=CONFIG_HASH,
        library_root_at_plan=LIBRARY_ROOT,
    )


def _unexpected_apply(*_args: object) -> Never:
    """Fail if a Plan-only command test unexpectedly enters Apply."""
    raise AssertionError


def _register_library(database_file: Path, library_root: str) -> None:
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(
            Library(
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
