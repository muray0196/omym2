"""
Summary: Runs a command against an ephemeral loopback OMYM2 Web server.
Why: Gives browser and package gates isolated application state and a real server.
"""
# ruff: noqa: INP001, T201 -- Standalone gate script reports concise CLI results.

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast
from uuid import UUID

import uvicorn
from mutagen.flac import FLAC

from omym2.adapters.config.toml_config_store import TomlConfigStore
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.domain.models.app_config import AppConfig, PathPolicyConfig, PathsConfig
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.services.config_fingerprint import calculate_path_policy_fingerprint
from omym2.platform.web_composition import build_web_app
from omym2.shared.ids import LibraryId

if TYPE_CHECKING:
    from collections.abc import Sequence

PROJECT_ROOT_NOT_FOUND_MESSAGE = "Unable to locate the project root."
DEFAULT_BASE_URL_ENVIRONMENT_VARIABLE = "OMYM2_E2E_BASE_URL"
APPLICATION_ROOT_ENVIRONMENT_VARIABLE = "OMYM2_E2E_APPLICATION_ROOT"
FIXTURE_PROFILE_ENVIRONMENT_VARIABLE = "OMYM2_E2E_FIXTURE_PROFILE"
CHILD_PATH_OVERRIDE_ENVIRONMENT_VARIABLE = "OMYM2_TEST_CHILD_PATH"
LOOPBACK_HOST = "127.0.0.1"
EPHEMERAL_PORT = 0
SERVER_START_TIMEOUT_SECONDS = 20.0
SERVER_STOP_TIMEOUT_SECONDS = 10.0
ENVIRONMENT_VARIABLE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
E2E_LIBRARY_DIRECTORY_NAME = "library"
E2E_INCOMING_DIRECTORY_NAME = "incoming"
E2E_SENTINEL_FILE_NAME = "sentinel.flac"
E2E_APPLY_SUCCESS_FILE_NAME = "A-Success.flac"
E2E_APPLY_FAILURE_FILE_NAME = "Z-Failure.flac"
E2E_FIRST_RUN_ORGANIZE_FILE_NAME = "Needs-Organizing.flac"
E2E_FIRST_RUN_ADD_SUCCESS_FILE_NAME = "First-Run-Success.flac"
E2E_FIRST_RUN_ADD_BLOCKED_FILE_NAME = "Blocked-Arrival.flac"
E2E_LIBRARY_ID = LibraryId(UUID("01912345-6789-7abc-8def-0123456789ab"))
E2E_FIXED_TIME = datetime(2026, 1, 1, tzinfo=UTC)
E2E_FLAC_BYTE_ORDER = "big"
E2E_FLAC_CHANNEL_COUNT = 1
E2E_FLAC_CHANNEL_COUNT_BITS = 3
E2E_FLAC_FRAME_SIZE_FIELDS_BYTES = 6
E2E_FLAC_LAST_METADATA_BLOCK_FLAG = 0x80
E2E_FLAC_MD5_BYTES = 16
E2E_FLAC_SAMPLE_RATE_BITS = 20
E2E_FLAC_SAMPLE_RATE_HZ = 8_000
E2E_FLAC_SAMPLE_SIZE_BITS = 8
E2E_FLAC_SAMPLE_SIZE_FIELD_BITS = 5
E2E_FLAC_STREAMINFO_BLOCK_SIZE_SAMPLES = 4_096
E2E_FLAC_STREAMINFO_LENGTH_BYTES = 34
E2E_FLAC_STREAM_MARKER = b"fLaC"
E2E_FLAC_TOTAL_SAMPLES_BITS = 36
E2E_INDEX_DISPLAY_OFFSET = 1
E2E_SENTINEL_TITLE = "sentinel"
E2E_APPLY_SUCCESS_TITLE = "A Success"
E2E_APPLY_FAILURE_TITLE = "Z Failure"
E2E_FIRST_RUN_ORGANIZE_TITLE = "Organized Title"
E2E_FIRST_RUN_ADD_SUCCESS_TITLE = "First Run Success"
E2E_FIRST_RUN_ADD_BLOCKED_TITLE = "Blocked Arrival"
E2E_SENTINEL_ARTIST = "Sentinel Artist"
E2E_SENTINEL_ALBUM = "Sentinel Album"
E2E_SENTINEL_YEAR = 2026
E2E_SENTINEL_TRACK_NUMBER = "1/1"
E2E_SENTINEL_DISC_NUMBER = "1/1"
E2E_PATH_POLICY_TEMPLATE = "{title}"
E2E_FIXTURE_PROFILE_REGISTERED = "registered"
E2E_FIXTURE_PROFILE_FIRST_RUN = "first-run"
E2E_FIXTURE_PROFILES = (
    E2E_FIXTURE_PROFILE_REGISTERED,
    E2E_FIXTURE_PROFILE_FIRST_RUN,
)


class FlacTagWriter(Protocol):
    """Narrow fixture-only surface used to tag E2E FLAC files."""

    def __setitem__(self, key: str, value: str) -> None:
        """Set one Vorbis-comment field."""

    def save(self) -> None:
        """Persist the fixture metadata."""


class WebTestServerError(RuntimeError):
    """Raised when an isolated Web test server cannot run safely."""


@dataclass(frozen=True, slots=True)
class WebTestServerOptions:
    """Resolved options for one isolated Web server process."""

    environment_variable: str
    working_directory: Path
    application_root: Path
    require_installed: bool
    fixture_profile: str


class ParsedArgs(argparse.Namespace):
    """Typed command-line arguments for the ephemeral server."""

    def __init__(self) -> None:
        super().__init__()
        self.environment_variable: str = DEFAULT_BASE_URL_ENVIRONMENT_VARIABLE
        self.working_directory: Path = Path.cwd()
        self.application_root: Path | None = None
        self.require_installed: bool = False
        self.fixture_profile: str = E2E_FIXTURE_PROFILE_REGISTERED
        self.command: list[str] = []


def run_with_server(
    command: Sequence[str],
    *,
    options: WebTestServerOptions,
) -> int:
    """Run command with an ephemeral Web server URL in its environment."""
    if not command:
        msg = "A command is required after --."
        raise WebTestServerError(msg)
    if not ENVIRONMENT_VARIABLE_PATTERN.fullmatch(options.environment_variable):
        msg = f"Invalid environment-variable name: {options.environment_variable}"
        raise WebTestServerError(msg)
    if options.require_installed:
        _require_installed_package()
    if options.fixture_profile not in E2E_FIXTURE_PROFILES:
        msg = f"Unknown E2E fixture profile: {options.fixture_profile}"
        raise WebTestServerError(msg)

    _require_empty_application_root(options.application_root)
    _ = options.application_root.mkdir(parents=True, exist_ok=True)
    config_path = options.application_root / ".config" / "config.toml"
    database_path = options.application_root / ".data" / "omym2.sqlite3"
    _ = config_path.parent.mkdir(parents=True, exist_ok=True)
    _ = database_path.parent.mkdir(parents=True, exist_ok=True)
    _seed_e2e_state(
        config_path,
        database_path,
        options.application_root,
        fixture_profile=options.fixture_profile,
    )
    app = build_web_app(config_path=config_path, database_path=database_path)

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((LOOPBACK_HOST, EPHEMERAL_PORT))
    listener.listen()
    _bound_host, port = cast("tuple[str, int]", listener.getsockname())
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=LOOPBACK_HOST,
            log_level="warning",
            lifespan="on",
        )
    )
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [listener]},
        name="omym2-web-test-server",
        daemon=True,
    )
    thread.start()
    try:
        _wait_until_started(server, thread)
        environment = os.environ.copy()
        environment[options.environment_variable] = f"http://{LOOPBACK_HOST}:{port}"
        environment[APPLICATION_ROOT_ENVIRONMENT_VARIABLE] = str(options.application_root)
        environment[FIXTURE_PROFILE_ENVIRONMENT_VARIABLE] = options.fixture_profile
        child_path = environment.pop(CHILD_PATH_OVERRIDE_ENVIRONMENT_VARIABLE, None)
        if child_path is not None:
            environment["PATH"] = child_path
        if options.require_installed:
            _ = environment.pop("PYTHONPATH", None)
        result = subprocess.run(  # noqa: S603 -- the caller explicitly supplies the test command.
            tuple(command),
            cwd=options.working_directory,
            env=environment,
            check=False,
        )
        return result.returncode
    finally:
        server.should_exit = True
        thread.join(timeout=SERVER_STOP_TIMEOUT_SECONDS)
        listener.close()
        if thread.is_alive():
            msg = "Ephemeral Web server did not stop within the timeout."
            raise WebTestServerError(msg)


def _require_empty_application_root(application_root: Path) -> None:
    if application_root.exists() and any(application_root.iterdir()):
        msg = f"Ephemeral application root must be empty: {application_root}"
        raise WebTestServerError(msg)


def _seed_e2e_state(
    config_path: Path,
    database_path: Path,
    application_root: Path,
    *,
    fixture_profile: str,
) -> None:
    if fixture_profile == E2E_FIXTURE_PROFILE_FIRST_RUN:
        _seed_first_run_audio_state(application_root)
        return

    library_root = application_root / E2E_LIBRARY_DIRECTORY_NAME
    _ = library_root.mkdir(parents=True)
    _write_e2e_audio(library_root / E2E_SENTINEL_FILE_NAME, title=E2E_SENTINEL_TITLE)
    incoming_root = application_root / E2E_INCOMING_DIRECTORY_NAME
    _ = incoming_root.mkdir(parents=True)
    _write_e2e_audio(incoming_root / E2E_APPLY_SUCCESS_FILE_NAME, title=E2E_APPLY_SUCCESS_TITLE)
    _write_e2e_audio(incoming_root / E2E_APPLY_FAILURE_FILE_NAME, title=E2E_APPLY_FAILURE_TITLE)
    config = AppConfig(
        paths=PathsConfig(library=str(library_root), incoming=str(incoming_root)),
        path_policy=PathPolicyConfig(template=E2E_PATH_POLICY_TEMPLATE),
    )
    config_store = TomlConfigStore(config_path)
    config_snapshot = config_store.read_snapshot()
    _ = config_store.save(config, expected_config_revision=config_snapshot.config_revision)
    path_policy_hash = calculate_path_policy_fingerprint(
        config.path_policy,
        config.artist_ids,
        config.metadata.album_year_resolution,
    )
    library = Library(
        library_id=E2E_LIBRARY_ID,
        root_path=str(library_root),
        path_policy_hash=path_policy_hash,
        registered_at=E2E_FIXED_TIME,
        status=LibraryStatus.REGISTERED,
        created_at=E2E_FIXED_TIME,
        updated_at=E2E_FIXED_TIME,
    )
    with SQLiteUnitOfWork(database_path) as unit_of_work:
        unit_of_work.libraries.save(library)
        unit_of_work.commit()


def _seed_first_run_audio_state(application_root: Path) -> None:
    library_root = application_root / E2E_LIBRARY_DIRECTORY_NAME
    _ = library_root.mkdir(parents=True)
    _write_e2e_audio(
        library_root / E2E_FIRST_RUN_ORGANIZE_FILE_NAME,
        title=E2E_FIRST_RUN_ORGANIZE_TITLE,
    )
    incoming_root = application_root / E2E_INCOMING_DIRECTORY_NAME
    _ = incoming_root.mkdir(parents=True)
    _write_e2e_audio(
        incoming_root / E2E_FIRST_RUN_ADD_SUCCESS_FILE_NAME,
        title=E2E_FIRST_RUN_ADD_SUCCESS_TITLE,
    )
    _write_e2e_audio(
        incoming_root / E2E_FIRST_RUN_ADD_BLOCKED_FILE_NAME,
        title=E2E_FIRST_RUN_ADD_BLOCKED_TITLE,
    )


def _write_e2e_audio(path: Path, *, title: str) -> None:
    _ = path.write_bytes(_minimal_flac_bytes())
    audio = cast("FlacTagWriter", FLAC(path))
    audio["title"] = title
    audio["artist"] = E2E_SENTINEL_ARTIST
    audio["albumartist"] = E2E_SENTINEL_ARTIST
    audio["album"] = E2E_SENTINEL_ALBUM
    audio["date"] = str(E2E_SENTINEL_YEAR)
    audio["tracknumber"] = E2E_SENTINEL_TRACK_NUMBER
    audio["discnumber"] = E2E_SENTINEL_DISC_NUMBER
    audio.save()


def _minimal_flac_bytes() -> bytes:
    stream_info = E2E_FLAC_STREAMINFO_BLOCK_SIZE_SAMPLES.to_bytes(2, E2E_FLAC_BYTE_ORDER) * 2
    stream_info += bytes(E2E_FLAC_FRAME_SIZE_FIELDS_BYTES)
    sample_rate_shift = E2E_FLAC_CHANNEL_COUNT_BITS + E2E_FLAC_SAMPLE_SIZE_FIELD_BITS + E2E_FLAC_TOTAL_SAMPLES_BITS
    channel_count_shift = E2E_FLAC_SAMPLE_SIZE_FIELD_BITS + E2E_FLAC_TOTAL_SAMPLES_BITS
    sample_size_shift = E2E_FLAC_TOTAL_SAMPLES_BITS
    packed_audio_properties = (
        E2E_FLAC_SAMPLE_RATE_HZ << sample_rate_shift
        | (E2E_FLAC_CHANNEL_COUNT - E2E_INDEX_DISPLAY_OFFSET) << channel_count_shift
        | (E2E_FLAC_SAMPLE_SIZE_BITS - E2E_INDEX_DISPLAY_OFFSET) << sample_size_shift
    )
    stream_info += packed_audio_properties.to_bytes(
        (
            E2E_FLAC_SAMPLE_RATE_BITS
            + E2E_FLAC_CHANNEL_COUNT_BITS
            + E2E_FLAC_SAMPLE_SIZE_FIELD_BITS
            + E2E_FLAC_TOTAL_SAMPLES_BITS
        )
        // 8,
        E2E_FLAC_BYTE_ORDER,
    )
    stream_info += bytes(E2E_FLAC_MD5_BYTES)
    block_header = bytes(
        (
            E2E_FLAC_LAST_METADATA_BLOCK_FLAG,
            0,
            0,
            E2E_FLAC_STREAMINFO_LENGTH_BYTES,
        )
    )
    return E2E_FLAC_STREAM_MARKER + block_header + stream_info


def _wait_until_started(server: uvicorn.Server, thread: threading.Thread) -> None:
    deadline = time.monotonic() + SERVER_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if server.started:
            return
        if not thread.is_alive():
            msg = "Ephemeral Web server exited before becoming ready."
            raise WebTestServerError(msg)
        time.sleep(0.01)
    msg = "Ephemeral Web server did not become ready within the timeout."
    raise WebTestServerError(msg)


def _require_installed_package() -> None:
    spec = importlib.util.find_spec("omym2")
    if spec is None or spec.origin is None:
        msg = "The installed omym2 package cannot be located."
        raise WebTestServerError(msg)
    origin = Path(spec.origin).resolve()
    project_source = _project_root() / "src"
    if origin.is_relative_to(project_source):
        msg = f"Installed-package gate resolved the source checkout instead of site-packages: {origin}"
        raise WebTestServerError(msg)


def _project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise WebTestServerError(PROJECT_ROOT_NOT_FOUND_MESSAGE)


def _parse_args(argv: Sequence[str] | None) -> ParsedArgs:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--environment-variable", default=DEFAULT_BASE_URL_ENVIRONMENT_VARIABLE)
    _ = parser.add_argument("--working-directory", type=Path, default=Path.cwd())
    _ = parser.add_argument("--application-root", type=Path)
    _ = parser.add_argument("--require-installed", action="store_true")
    _ = parser.add_argument(
        "--fixture-profile",
        choices=E2E_FIXTURE_PROFILES,
        default=E2E_FIXTURE_PROFILE_REGISTERED,
    )
    _ = parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv, namespace=ParsedArgs())
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    return args


def main(argv: Sequence[str] | None = None) -> int:
    """Run a supplied gate command against an isolated server."""
    args = _parse_args(argv)
    try:
        if args.application_root is not None:
            return run_with_server(
                args.command,
                options=_server_options(args, args.application_root),
            )
        with tempfile.TemporaryDirectory(prefix="omym2-web-test-") as temporary_directory:
            return run_with_server(
                args.command,
                options=_server_options(args, Path(temporary_directory)),
            )
    except (OSError, WebTestServerError) as exc:
        print(f"web test server failed: {exc}", file=sys.stderr)
        return 1


def _server_options(args: ParsedArgs, application_root: Path) -> WebTestServerOptions:
    return WebTestServerOptions(
        environment_variable=args.environment_variable,
        working_directory=args.working_directory,
        application_root=application_root,
        require_installed=args.require_installed,
        fixture_profile=args.fixture_profile,
    )


if __name__ == "__main__":
    raise SystemExit(main())
