"""
Summary: Runs the existing FastAPI application on a private desktop loopback socket.
Why: Gives the native window a race-free ready URL and graceful shutdown boundary.
"""

from __future__ import annotations

import json
import logging
import socket
import sys
from dataclasses import dataclass, field
from http.client import HTTPConnection, HTTPException
from threading import Lock, Thread
from time import sleep
from typing import TYPE_CHECKING, Protocol, cast
from urllib.parse import urlunparse

import uvicorn

from omym2.config import (
    DESKTOP_EPHEMERAL_PORT,
    DESKTOP_LOOPBACK_HOST,
    DESKTOP_READINESS_INTERVAL_SECONDS,
    DESKTOP_READINESS_MAX_ATTEMPTS,
    DESKTOP_READINESS_TIMEOUT_SECONDS,
    DESKTOP_SERVER_THREAD_NAME,
    DESKTOP_SUPPORTED_PLATFORM,
    HTTP_OK_STATUS,
    WEB_API_BOOTSTRAP_ROUTE,
    WEB_ROOT_ROUTE,
    WEB_URL_SCHEME,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

LOGGER = logging.getLogger(__name__)


class DesktopServerError(RuntimeError):
    """Raised when the private desktop server cannot start, become ready, or stop."""


class UvicornServerBackend(Protocol):
    """The Uvicorn behavior required by the desktop server adapter."""

    @property
    def should_exit(self) -> bool:
        """Return whether graceful server exit has been requested."""
        ...

    @should_exit.setter
    def should_exit(self, value: bool) -> None:
        """Request graceful server exit."""
        ...

    def run(self, *, sockets: list[socket.socket]) -> None:
        """Serve the ASGI application through the pre-bound listener."""
        ...


class SocketOptionWriter(Protocol):
    """The socket option behavior required before the desktop listener binds."""

    def setsockopt(self, level: int, option: int, value: int) -> None:
        """Set one integer socket option."""
        ...


type ListenerFactory = Callable[[], socket.socket]
type ServerFactory = Callable[["FastAPI"], UvicornServerBackend]
type ReadinessProbe = Callable[[str, int], bool]
type ReadinessWait = Callable[[float], object]


def _open_loopback_listener() -> socket.socket:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        _make_windows_listener_exclusive(listener)
        listener.bind((DESKTOP_LOOPBACK_HOST, DESKTOP_EPHEMERAL_PORT))
        listener.listen()
    except BaseException:
        listener.close()
        raise
    return listener


def _make_windows_listener_exclusive(listener: object, *, platform: str | None = None) -> None:
    """Prevent another Windows process from rebinding the selected desktop port."""
    current_platform = sys.platform if platform is None else platform
    if current_platform != DESKTOP_SUPPORTED_PLATFORM:
        return
    exclusive_address_option = cast("int", vars(socket)["SO_EXCLUSIVEADDRUSE"])
    cast("SocketOptionWriter", listener).setsockopt(socket.SOL_SOCKET, exclusive_address_option, 1)


def _build_uvicorn_server(app: FastAPI) -> UvicornServerBackend:
    return uvicorn.Server(
        uvicorn.Config(
            app,
            host=DESKTOP_LOOPBACK_HOST,
            lifespan="on",
            log_config=None,
            access_log=False,
        )
    )


def _probe_bootstrap(host: str, port: int) -> bool:
    connection = HTTPConnection(host, port, timeout=DESKTOP_READINESS_TIMEOUT_SECONDS)
    try:
        connection.request("GET", WEB_API_BOOTSTRAP_ROUTE, headers={"Accept": "application/json"})
        response = connection.getresponse()
        body = response.read()
        if response.status != HTTP_OK_STATUS:
            return False
        payload = cast("object", json.loads(body))
        if not isinstance(payload, dict):
            return False
        response_data = cast("dict[str, object]", payload).get("data")
        return isinstance(response_data, dict)
    except HTTPException, json.JSONDecodeError, OSError:
        return False
    finally:
        connection.close()


@dataclass(frozen=True, slots=True)
class DesktopServerDependencies:
    """Overridable server I/O for deterministic lifecycle tests."""

    listener_factory: ListenerFactory = _open_loopback_listener
    server_factory: ServerFactory = _build_uvicorn_server
    readiness_probe: ReadinessProbe = _probe_bootstrap
    readiness_wait: ReadinessWait = sleep


@dataclass(slots=True)
class UvicornDesktopServer:
    """Own one pre-bound loopback listener and background Uvicorn thread."""

    app: FastAPI
    dependencies: DesktopServerDependencies = field(default_factory=DesktopServerDependencies)
    _backend: UvicornServerBackend | None = field(default=None, init=False, repr=False)
    _listener: socket.socket | None = field(default=None, init=False, repr=False)
    _thread: Thread | None = field(default=None, init=False, repr=False)
    _thread_failure: BaseException | None = field(default=None, init=False, repr=False)
    _port: int | None = field(default=None, init=False, repr=False)
    _lifecycle_guard: Lock = field(default_factory=Lock, init=False, repr=False)

    @property
    def port(self) -> int | None:
        """Return the selected ephemeral port after startup begins."""
        return self._port

    @property
    def url(self) -> str | None:
        """Return the desktop root URL after startup begins."""
        return None if self._port is None else _desktop_url(self._port)

    def start(self) -> str:
        """Start Uvicorn on a retained ephemeral listener and wait for Bootstrap readiness."""
        with self._lifecycle_guard:
            if self._thread is not None:
                if self._thread.is_alive() and self.url is not None:
                    return self.url
                msg = "The desktop server cannot restart after its thread exits."
                raise DesktopServerError(msg)
            try:
                listener = self.dependencies.listener_factory()
            except OSError as exc:
                msg = "The desktop loopback listener could not be opened."
                raise DesktopServerError(msg) from exc
            try:
                _bound_host, port = cast("tuple[str, int]", listener.getsockname())
                backend = self.dependencies.server_factory(self.app)
                thread = Thread(
                    target=self._run_backend,
                    args=(backend, listener),
                    name=DESKTOP_SERVER_THREAD_NAME,
                    daemon=False,
                )
            except Exception as exc:
                listener.close()
                msg = "The desktop server could not be configured."
                raise DesktopServerError(msg) from exc
            self._listener = listener
            self._backend = backend
            self._thread = thread
            self._port = port
            try:
                thread.start()
            except Exception as exc:
                listener.close()
                self._backend = None
                self._listener = None
                self._thread = None
                self._port = None
                msg = "The desktop server thread could not start."
                raise DesktopServerError(msg) from exc
        try:
            self._wait_until_ready(thread, port)
        except BaseException:
            try:
                self.stop()
            except Exception:
                LOGGER.exception("Desktop server cleanup failed after startup failure")
            raise
        url = _desktop_url(port)
        LOGGER.info("Desktop server started host=%s port=%s", DESKTOP_LOOPBACK_HOST, port)
        return url

    def stop(self) -> None:
        """Request graceful shutdown, waiting for accepted operations before listener release."""
        with self._lifecycle_guard:
            backend = self._backend
            listener = self._listener
            thread = self._thread
            if backend is None or listener is None or thread is None:
                return
            backend.should_exit = True
        LOGGER.info("Desktop server shutdown requested")
        thread.join()
        listener.close()
        with self._lifecycle_guard:
            failure = self._thread_failure
            self._backend = None
            self._listener = None
            self._thread = None
            self._thread_failure = None
            self._port = None
        if failure is not None:
            msg = "The desktop server thread failed."
            raise DesktopServerError(msg) from failure
        LOGGER.info("Desktop server stopped gracefully")

    def _run_backend(self, backend: UvicornServerBackend, listener: socket.socket) -> None:
        try:
            backend.run(sockets=[listener])
        except BaseException as exc:
            with self._lifecycle_guard:
                self._thread_failure = exc
            LOGGER.exception("Desktop server thread terminated with an error")

    def _wait_until_ready(self, thread: Thread, port: int) -> None:
        for attempt in range(DESKTOP_READINESS_MAX_ATTEMPTS):
            if self._thread_failure is not None or not thread.is_alive():
                self._raise_early_thread_exit()
            try:
                is_ready = self.dependencies.readiness_probe(DESKTOP_LOOPBACK_HOST, port)
            except Exception as exc:
                msg = "The desktop Bootstrap readiness probe failed."
                raise DesktopServerError(msg) from exc
            if is_ready:
                if not thread.is_alive():
                    self._raise_early_thread_exit()
                return
            if attempt + 1 < DESKTOP_READINESS_MAX_ATTEMPTS:
                _ = self.dependencies.readiness_wait(DESKTOP_READINESS_INTERVAL_SECONDS)
        if self._thread_failure is not None or not thread.is_alive():
            self._raise_early_thread_exit()
        msg = "The desktop server did not become ready before the startup deadline."
        raise DesktopServerError(msg)

    def _raise_early_thread_exit(self) -> None:
        failure = self._thread_failure
        msg = "The desktop server thread exited before readiness."
        if failure is None:
            raise DesktopServerError(msg)
        raise DesktopServerError(msg) from failure


def _desktop_url(port: int) -> str:
    return urlunparse((WEB_URL_SCHEME, f"{DESKTOP_LOOPBACK_HOST}:{port}", WEB_ROOT_ROUTE, "", "", ""))
