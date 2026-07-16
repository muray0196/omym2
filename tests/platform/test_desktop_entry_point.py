"""
Summary: Tests native desktop entry-point composition and fatal error mapping.
Why: Keeps stable paths, diagnostics, and GUI exit behavior reliable without native I/O.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import TYPE_CHECKING, final

from fastapi import FastAPI

from omym2.adapters.config.application_paths import ApplicationPaths, DesktopApplicationPathError
from omym2.adapters.config.toml_config_store import TomlConfigStore
from omym2.config import DESKTOP_FAILURE_EXIT_CODE, DESKTOP_SUCCESS_EXIT_CODE, DESKTOP_WINDOW_TITLE
from omym2.domain.models.app_config import LoggingConfig
from omym2.platform.desktop_entry_point import (
    DesktopEntryDependencies,
    configure_desktop_logging,
    run_desktop,
)

if TYPE_CHECKING:
    from pathlib import Path

LOG_ROTATION_TEST_MAX_BYTES = 1
LOG_ROTATION_TEST_RETENTION_FILES = 2
LOG_ROTATION_TEST_RECORD_COUNT = LOG_ROTATION_TEST_RETENTION_FILES + 2


@final
class RecordingServer:
    """Records entry-point server lifecycle calls."""

    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure
        self.start_calls = 0
        self.stop_calls = 0

    def start(self) -> str:
        self.start_calls += 1
        if self.failure is not None:
            raise self.failure
        return "http://127.0.0.1:49152/"

    def stop(self) -> None:
        self.stop_calls += 1


@final
class RecordingWindow:
    """Records the ready URL shown by entry-point composition."""

    def __init__(self) -> None:
        self.urls: list[str] = []

    def show(self, url: str) -> None:
        self.urls.append(url)


@final
class RecordingErrorReporter:
    """Records fatal user-visible desktop errors."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def show(self, title: str, message: str) -> None:
        self.calls.append((title, message))


def test_entry_point_composes_stable_paths_server_and_window(tmp_path: Path) -> None:
    """Desktop composition passes its stable Config and database paths into the existing Web app."""
    paths = ApplicationPaths(tmp_path)
    app = FastAPI()
    server = RecordingServer()
    window = RecordingWindow()
    build_calls: list[tuple[Path, Path]] = []
    configured_logs: list[Path] = []
    reporter = RecordingErrorReporter()

    def build_app(config_path: Path, database_path: Path) -> FastAPI:
        build_calls.append((config_path, database_path))
        return app

    def configure_log(log_file: Path, _config: LoggingConfig, _sensitive_values: tuple[str, ...]) -> None:
        configured_logs.append(log_file)

    result = run_desktop(
        DesktopEntryDependencies(
            paths_resolver=lambda: paths,
            web_app_builder=build_app,
            server_factory=lambda built_app: server if built_app is app else RecordingServer(),
            window_factory=lambda: window,
            logging_configurator=configure_log,
            error_reporter=reporter,
        )
    )

    assert result == DESKTOP_SUCCESS_EXIT_CODE
    assert build_calls == [(paths.config_file, paths.database_file)]
    assert configured_logs == [paths.desktop_log_file]
    assert window.urls == ["http://127.0.0.1:49152/"]
    assert server.stop_calls == 1
    assert reporter.calls == []


def test_entry_point_maps_runtime_failure_to_visible_error(tmp_path: Path) -> None:
    """Fatal server failures return nonzero and direct users to the persistent log."""
    paths = ApplicationPaths(tmp_path)
    reporter = RecordingErrorReporter()

    result = run_desktop(
        DesktopEntryDependencies(
            paths_resolver=lambda: paths,
            web_app_builder=lambda _config, _database: FastAPI(),
            server_factory=lambda _app: RecordingServer(failure=RuntimeError("private details")),
            window_factory=RecordingWindow,
            logging_configurator=lambda _path, _config, _sensitive: None,
            error_reporter=reporter,
        )
    )

    assert result == DESKTOP_FAILURE_EXIT_CODE
    assert reporter.calls == [
        (DESKTOP_WINDOW_TITLE, f"OMYM2 could not start. See the diagnostic log at {paths.desktop_log_file}.")
    ]
    assert "private details" not in reporter.calls[0][1]


def test_entry_point_reports_path_failure_without_claiming_log_exists() -> None:
    """A missing supported data root still produces concise user-visible failure text."""
    reporter = RecordingErrorReporter()

    def fail_paths() -> ApplicationPaths:
        message = "missing local data"
        raise DesktopApplicationPathError(message)

    result = run_desktop(
        DesktopEntryDependencies(
            paths_resolver=fail_paths,
            logging_configurator=lambda _path, _config, _sensitive: None,
            error_reporter=reporter,
        )
    )

    assert result == DESKTOP_FAILURE_EXIT_CODE
    assert reporter.calls == [(DESKTOP_WINDOW_TITLE, "OMYM2 could not start and no diagnostic log could be created.")]


def test_entry_point_does_not_claim_failed_log_configuration_created_a_log(tmp_path: Path) -> None:
    """An unwritable diagnostic path produces an honest no-log startup error."""
    paths = ApplicationPaths(tmp_path)
    reporter = RecordingErrorReporter()

    def fail_logging(_path: Path, _config: LoggingConfig, _sensitive_values: tuple[str, ...]) -> None:
        message = "log directory is unwritable"
        raise OSError(message)

    result = run_desktop(
        DesktopEntryDependencies(
            paths_resolver=lambda: paths,
            logging_configurator=fail_logging,
            error_reporter=reporter,
        )
    )

    assert result == DESKTOP_FAILURE_EXIT_CODE
    assert reporter.calls == [(DESKTOP_WINDOW_TITLE, "OMYM2 could not start and no diagnostic log could be created.")]


def test_desktop_logging_writes_bounded_persistent_log(tmp_path: Path) -> None:
    """GUI-process diagnostics reach a writable file even without a console."""
    log_file = tmp_path / "logs" / "desktop.log"
    logger = logging.getLogger("omym2.desktop-test")
    try:
        configure_desktop_logging(log_file, LoggingConfig(), ())
        logger.warning("desktop-log-sentinel")
        for handler in logging.getLogger().handlers:
            handler.flush()

        assert "desktop-log-sentinel" in log_file.read_text(encoding="utf-8")
    finally:
        for handler in tuple(logging.getLogger().handlers):
            handler.close()
            logging.getLogger().removeHandler(handler)


def test_desktop_logging_rotates_and_enforces_retention_limit(tmp_path: Path) -> None:
    """Configured thresholds rotate diagnostics without retaining excess backups."""
    log_file = tmp_path / "logs" / "desktop.log"
    logger = logging.getLogger("omym2.rotation-test")
    logging_config = LoggingConfig(
        rotation_max_bytes=LOG_ROTATION_TEST_MAX_BYTES,
        retention_files=LOG_ROTATION_TEST_RETENTION_FILES,
    )
    try:
        configure_desktop_logging(log_file, logging_config, ())
        for record_index in range(LOG_ROTATION_TEST_RECORD_COUNT):
            logger.warning("desktop-rotation-sentinel-%s", record_index)
        for handler in logging.getLogger().handlers:
            handler.flush()

        retained_logs = tuple(log_file.parent.glob(f"{log_file.name}*"))
        assert {path.name for path in retained_logs} == {
            log_file.name,
            f"{log_file.name}.1",
            f"{log_file.name}.2",
        }
        assert all(path.stat().st_size > 0 for path in retained_logs)
        assert f"desktop-rotation-sentinel-{LOG_ROTATION_TEST_RECORD_COUNT - 1}" in log_file.read_text(encoding="utf-8")
    finally:
        for handler in tuple(logging.getLogger().handlers):
            handler.close()
            logging.getLogger().removeHandler(handler)


def test_entry_point_honors_persisted_log_destination_and_controls(tmp_path: Path) -> None:
    """Desktop startup resolves persisted logging controls beneath writable application storage."""
    paths = ApplicationPaths(tmp_path)
    store = TomlConfigStore(paths.config_file)
    snapshot = store.read_snapshot()
    logging_config = replace(
        snapshot.config.logging,
        destination="diagnostics/custom.log",
        level="WARNING",
        rotation_max_bytes=97,
        retention_files=2,
    )
    _ = store.save(
        replace(snapshot.config, logging=logging_config),
        expected_config_revision=snapshot.config_revision,
    )
    observed: list[tuple[Path, LoggingConfig, tuple[str, ...]]] = []

    result = run_desktop(
        DesktopEntryDependencies(
            paths_resolver=lambda: paths,
            web_app_builder=lambda _config, _database: FastAPI(),
            server_factory=lambda _app: RecordingServer(),
            window_factory=RecordingWindow,
            logging_configurator=lambda path, config, sensitive: observed.append((path, config, sensitive)),
        )
    )

    assert result == DESKTOP_SUCCESS_EXIT_CODE
    assert observed[0][0] == tmp_path / "diagnostics" / "custom.log"
    assert observed[0][1] == logging_config
    assert str(tmp_path) in observed[0][2]
    assert "diagnostics/custom.log" in observed[0][2]


def test_desktop_logging_redacts_sensitive_message_and_exception_values(tmp_path: Path) -> None:
    """Configured path and identity values never reach persisted diagnostic text."""
    log_file = tmp_path / "logs" / "desktop.log"
    sensitive_value = "private-owner-token"
    logger = logging.getLogger("omym2.redaction-test")

    def fail_with_sensitive_value() -> None:
        message = f"failed at {sensitive_value}"
        raise RuntimeError(message)

    try:
        configure_desktop_logging(log_file, LoggingConfig(), (sensitive_value,))
        try:
            fail_with_sensitive_value()
        except RuntimeError:
            logger.exception("operation for %s failed", sensitive_value)
        for handler in logging.getLogger().handlers:
            handler.flush()

        rendered = log_file.read_text(encoding="utf-8")
        assert sensitive_value not in rendered
        assert "[REDACTED]" in rendered
    finally:
        for handler in tuple(logging.getLogger().handlers):
            handler.close()
            logging.getLogger().removeHandler(handler)
