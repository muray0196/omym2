"""
Summary: Tests coordination of the desktop server and native window lifecycles.
Why: Guarantees readiness ordering and safe shutdown across success and failure paths.
"""

from __future__ import annotations

from typing import final

import pytest

from omym2.platform.desktop_runtime import DesktopRuntime


@final
class RecordingServer:
    """Records desktop server lifecycle calls."""

    def __init__(
        self,
        events: list[str],
        *,
        start_failure: Exception | None = None,
        stop_failure: Exception | None = None,
    ) -> None:
        self.events = events
        self.start_failure = start_failure
        self.stop_failure = stop_failure
        self.url = "http://127.0.0.1:49152/"

    def start(self) -> str:
        self.events.append("server.start")
        if self.start_failure is not None:
            raise self.start_failure
        return self.url

    def stop(self) -> None:
        self.events.append("server.stop")
        if self.stop_failure is not None:
            raise self.stop_failure


@final
class RecordingWindow:
    """Records the URL passed to the native window."""

    def __init__(self, events: list[str], *, failure: Exception | None = None) -> None:
        self.events = events
        self.failure = failure

    def show(self, url: str) -> None:
        self.events.append(f"window.show:{url}")
        if self.failure is not None:
            raise self.failure


def test_runtime_opens_window_only_after_server_is_ready() -> None:
    """The native window never races a server that has not completed readiness."""
    events: list[str] = []
    server = RecordingServer(events)

    DesktopRuntime(server=server, window=RecordingWindow(events)).run()

    assert events == ["server.start", f"window.show:{server.url}", "server.stop"]


def test_runtime_stops_server_when_window_fails() -> None:
    """Window initialization failures still release the listener and application runtime."""
    events: list[str] = []
    window_failure = RuntimeError("window failed")

    with pytest.raises(RuntimeError, match="window failed") as exc_info:
        DesktopRuntime(
            server=RecordingServer(events),
            window=RecordingWindow(events, failure=window_failure),
        ).run()

    assert exc_info.value is window_failure
    assert events[-1] == "server.stop"


def test_runtime_stops_server_after_start_failure() -> None:
    """Partially initialized server adapters receive an idempotent cleanup request."""
    events: list[str] = []
    start_failure = RuntimeError("server failed")

    with pytest.raises(RuntimeError, match="server failed"):
        DesktopRuntime(
            server=RecordingServer(events, start_failure=start_failure),
            window=RecordingWindow(events),
        ).run()

    assert events == ["server.start", "server.stop"]


def test_runtime_preserves_window_failure_when_shutdown_also_fails() -> None:
    """Cleanup diagnostics do not hide the error that caused desktop teardown."""
    events: list[str] = []
    window_failure = RuntimeError("window failed")
    stop_failure = RuntimeError("stop failed")

    with pytest.raises(RuntimeError, match="window failed") as exc_info:
        DesktopRuntime(
            server=RecordingServer(events, stop_failure=stop_failure),
            window=RecordingWindow(events, failure=window_failure),
        ).run()

    assert exc_info.value is window_failure


def test_runtime_reports_shutdown_failure_after_normal_window_close() -> None:
    """A failed graceful shutdown is fatal when it is the only lifecycle error."""
    events: list[str] = []

    with pytest.raises(RuntimeError, match="stop failed"):
        DesktopRuntime(
            server=RecordingServer(events, stop_failure=RuntimeError("stop failed")),
            window=RecordingWindow(events),
        ).run()
