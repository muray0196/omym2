"""
Summary: Tests the desktop loopback Uvicorn server lifecycle.
Why: Protects race-free port selection, readiness, failure, and graceful shutdown behavior.
"""

from __future__ import annotations

import socket
from threading import Event, Thread
from time import sleep
from typing import TYPE_CHECKING, final
from urllib.parse import urlparse

import pytest
from fastapi import FastAPI

from omym2.adapters.desktop.server import (
    DesktopServerDependencies,
    DesktopServerError,
    UvicornDesktopServer,
    _make_windows_listener_exclusive,  # pyright: ignore[reportPrivateUsage] -- directly verifies Windows bind security.
)
from omym2.config import DESKTOP_LOOPBACK_HOST, DESKTOP_READINESS_INTERVAL_SECONDS, DESKTOP_SUPPORTED_PLATFORM

if TYPE_CHECKING:
    from collections.abc import Callable


@final
class BlockingServerBackend:
    """Blocks on a setter-backed shutdown event and records its listener."""

    def __init__(self, *, failure: BaseException | None = None, return_immediately: bool = False) -> None:
        self.failure = failure
        self.return_immediately = return_immediately
        self.started = Event()
        self.finished = Event()
        self.exit_requested = Event()
        self.sockets: list[socket.socket] = []
        self._should_exit = False

    @property
    def should_exit(self) -> bool:
        return self._should_exit

    @should_exit.setter
    def should_exit(self, value: bool) -> None:
        self._should_exit = value
        if value:
            self.exit_requested.set()

    def run(self, *, sockets: list[socket.socket]) -> None:
        try:
            self.sockets = sockets
            self.started.set()
            if self.failure is not None:
                raise self.failure
            if not self.return_immediately:
                _ = self.exit_requested.wait()
        finally:
            self.finished.set()


@final
class RecordingSocket:
    """Records socket-option calls without depending on the host operating system."""

    def __init__(self) -> None:
        self.options: list[tuple[int, int, int]] = []

    def setsockopt(self, level: int, option: int, value: int) -> None:
        self.options.append((level, option, value))


def _dependencies(
    backend: BlockingServerBackend,
    probe: Callable[[str, int], bool],
    *,
    listener_factory: Callable[[], socket.socket] | None = None,
    readiness_wait: Callable[[float], object] | None = None,
) -> DesktopServerDependencies:
    default_dependencies = DesktopServerDependencies()
    return DesktopServerDependencies(
        listener_factory=default_dependencies.listener_factory if listener_factory is None else listener_factory,
        server_factory=lambda _app: backend,
        readiness_probe=probe,
        readiness_wait=(lambda _seconds: None) if readiness_wait is None else readiness_wait,
    )


def test_server_retains_ephemeral_loopback_listener_until_graceful_stop() -> None:
    """Uvicorn receives the same bound socket whose dynamic URL is returned to the window."""
    backend = BlockingServerBackend()
    observed_probes: list[tuple[str, int]] = []

    def probe(host: str, port: int) -> bool:
        observed_probes.append((host, port))
        return backend.started.wait(DESKTOP_READINESS_INTERVAL_SECONDS)

    server = UvicornDesktopServer(FastAPI(), _dependencies(backend, probe))

    url = server.start()

    parsed = urlparse(url)
    assert parsed.hostname == DESKTOP_LOOPBACK_HOST
    assert parsed.port == server.port
    assert parsed.path == "/"
    assert server.port is not None
    assert server.port > 0
    assert observed_probes[-1] == (DESKTOP_LOOPBACK_HOST, server.port)
    assert backend.sockets[0].fileno() >= 0

    server.stop()

    assert backend.should_exit is True
    assert backend.sockets[0].fileno() == -1
    assert server.url is None


def test_windows_listener_uses_exclusive_address_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows prevents competing processes from rebinding the retained loopback port."""
    exclusive_option = 4096
    monkeypatch.setattr(socket, "SO_EXCLUSIVEADDRUSE", exclusive_option, raising=False)
    listener = RecordingSocket()

    _make_windows_listener_exclusive(listener, platform=DESKTOP_SUPPORTED_PLATFORM)

    assert listener.options == [(socket.SOL_SOCKET, exclusive_option, 1)]


def test_non_windows_listener_does_not_enable_reusable_address_binding() -> None:
    """Unsupported hosts leave the listener at safe operating-system defaults."""
    listener = RecordingSocket()

    _make_windows_listener_exclusive(listener, platform="linux")

    assert listener.options == []


def test_server_stop_is_idempotent() -> None:
    """Repeated shutdown requests do not touch an already released listener."""
    backend = BlockingServerBackend()
    server = UvicornDesktopServer(
        FastAPI(),
        _dependencies(backend, lambda _host, _port: backend.started.wait(DESKTOP_READINESS_INTERVAL_SECONDS)),
    )
    _ = server.start()

    server.stop()
    server.stop()

    assert backend.should_exit is True


def test_server_reports_listener_creation_failure() -> None:
    """Bind failures become typed startup errors before a server thread is created."""
    bind_failure = OSError("bind failed")

    def fail_listener() -> socket.socket:
        raise bind_failure

    server = UvicornDesktopServer(
        FastAPI(),
        _dependencies(BlockingServerBackend(), lambda _host, _port: False, listener_factory=fail_listener),
    )

    with pytest.raises(DesktopServerError, match="listener") as exc_info:
        _ = server.start()

    assert exc_info.value.__cause__ is bind_failure


def test_server_closes_listener_when_backend_configuration_fails() -> None:
    """A failure between bind and thread creation releases the reserved loopback port."""
    listeners: list[socket.socket] = []
    default_listener_factory = DesktopServerDependencies().listener_factory
    configuration_failure = RuntimeError("configuration failed")

    def record_listener() -> socket.socket:
        listener = default_listener_factory()
        listeners.append(listener)
        return listener

    def fail_configuration(_app: FastAPI) -> BlockingServerBackend:
        raise configuration_failure

    server = UvicornDesktopServer(
        FastAPI(),
        DesktopServerDependencies(
            listener_factory=record_listener,
            server_factory=fail_configuration,
            readiness_probe=lambda _host, _port: False,
        ),
    )

    with pytest.raises(DesktopServerError, match="configured") as exc_info:
        _ = server.start()

    assert exc_info.value.__cause__ is configuration_failure
    assert listeners[0].fileno() == -1


def test_server_closes_listener_when_thread_cannot_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A thread-start failure clears lifecycle state and releases the reserved listener."""
    listeners: list[socket.socket] = []
    default_listener_factory = DesktopServerDependencies().listener_factory
    thread_failure = RuntimeError("thread start failed")

    def record_listener() -> socket.socket:
        listener = default_listener_factory()
        listeners.append(listener)
        return listener

    def fail_thread_start(_thread: Thread) -> None:
        raise thread_failure

    monkeypatch.setattr(Thread, "start", fail_thread_start)
    server = UvicornDesktopServer(
        FastAPI(),
        DesktopServerDependencies(
            listener_factory=record_listener,
            server_factory=lambda _app: BlockingServerBackend(),
            readiness_probe=lambda _host, _port: False,
        ),
    )

    with pytest.raises(DesktopServerError, match="thread could not start") as exc_info:
        _ = server.start()

    assert exc_info.value.__cause__ is thread_failure
    assert listeners[0].fileno() == -1
    assert server.port is None


def test_server_reports_readiness_timeout_and_cleans_up() -> None:
    """A bounded failed Bootstrap probe stops Uvicorn and closes the listener."""
    backend = BlockingServerBackend()
    server = UvicornDesktopServer(FastAPI(), _dependencies(backend, lambda _host, _port: False))

    with pytest.raises(DesktopServerError, match="startup deadline"):
        _ = server.start()

    assert backend.should_exit is True
    assert backend.sockets[0].fileno() == -1


def test_server_reports_early_thread_termination() -> None:
    """A server thread that exits before Bootstrap readiness cannot open the window."""
    backend = BlockingServerBackend(return_immediately=True)

    dependencies = _dependencies(
        backend,
        lambda _host, _port: False,
        readiness_wait=sleep,
    )
    server = UvicornDesktopServer(FastAPI(), dependencies)

    with pytest.raises(DesktopServerError, match="exited before readiness"):
        _ = server.start()


def test_server_preserves_background_thread_failure() -> None:
    """Unexpected Uvicorn failure details remain available through exception chaining and logs."""
    thread_failure = OSError("uvicorn failed")
    backend = BlockingServerBackend(failure=thread_failure)
    server = UvicornDesktopServer(
        FastAPI(),
        _dependencies(
            backend,
            lambda _host, _port: False,
            readiness_wait=sleep,
        ),
    )

    with pytest.raises(DesktopServerError, match="exited before readiness") as exc_info:
        _ = server.start()

    assert exc_info.value.__cause__ is thread_failure
