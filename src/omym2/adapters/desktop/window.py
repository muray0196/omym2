"""
Summary: Displays OMYM2 in the supported native Windows WebView.
Why: Provides a thin desktop shell without exposing Python objects to JavaScript.
"""

from __future__ import annotations

import ctypes
import importlib
import logging
import os
import sys
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import TYPE_CHECKING, Protocol, Self, cast

from omym2.config import (
    DESKTOP_ERROR_DIALOG_FLAGS,
    DESKTOP_SUPPORTED_PLATFORM,
    DESKTOP_WEBVIEW2_DOTNET_REGISTRY_KEY,
    DESKTOP_WEBVIEW2_DOTNET_REGISTRY_RELEASE_VALUE,
    DESKTOP_WEBVIEW2_ENVIRONMENT_OVERRIDE_PREFIXES,
    DESKTOP_WEBVIEW2_MACHINE_REGISTRY_KEY,
    DESKTOP_WEBVIEW2_MINIMUM_DOTNET_RELEASE,
    DESKTOP_WEBVIEW2_MINIMUM_VERSION,
    DESKTOP_WEBVIEW2_POLICY_APPLICATION_ONLY_NAMES,
    DESKTOP_WEBVIEW2_POLICY_NAMES,
    DESKTOP_WEBVIEW2_POLICY_REGISTRY_ROOT,
    DESKTOP_WEBVIEW2_POLICY_WILDCARD_APPLICATION_ID,
    DESKTOP_WEBVIEW2_REGISTRY_VERSION_VALUE,
    DESKTOP_WEBVIEW2_USER_REGISTRY_KEY,
    DESKTOP_WEBVIEW_BACKEND,
    DESKTOP_WEBVIEW_CONTENT_LOAD_TIMEOUT_SECONDS,
    DESKTOP_WEBVIEW_CONTENT_LOADED_LOG_MARKER,
    DESKTOP_WEBVIEW_PRIVATE_MODE,
    DESKTOP_WINDOW_BACKGROUND_COLOR,
    DESKTOP_WINDOW_HEIGHT,
    DESKTOP_WINDOW_MAXIMIZED,
    DESKTOP_WINDOW_MIN_HEIGHT,
    DESKTOP_WINDOW_MIN_WIDTH,
    DESKTOP_WINDOW_RESIZABLE,
    DESKTOP_WINDOW_TITLE,
    DESKTOP_WINDOW_WIDTH,
    HTTP_OK_STATUS,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from typing import TextIO

LOGGER = logging.getLogger(__name__)


class DesktopWindowError(RuntimeError):
    """Raised when the native desktop window cannot be created or run."""


class WebViewWindow(Protocol):
    """The native window behavior used by the desktop adapter."""

    events: WebViewEvents

    def destroy(self) -> None:
        """Close the native window after a bounded startup failure."""
        ...


class WebViewInitializedEvent(Protocol):
    """The synchronous pre-window pywebview renderer event."""

    def __iadd__(self, callback: Callable[[str], bool | None]) -> Self:
        """Register one renderer guard before native window creation."""
        ...


class WebViewLifecycleEvent(Protocol):
    """An asynchronous zero-argument pywebview lifecycle event."""

    def __iadd__(self, callback: Callable[[], None]) -> Self:
        """Register one lifecycle callback."""
        ...

    def is_set(self) -> bool:
        """Return whether pywebview has fired this lifecycle event."""
        ...


class WebViewResponse(Protocol):
    """The Web resource response fields needed to prove the root document response."""

    url: str
    status_code: int


class WebViewResponseReceivedEvent(Protocol):
    """The asynchronous pywebview Web resource response event."""

    def __iadd__(self, callback: Callable[[WebViewResponse], None]) -> Self:
        """Register one response observer."""
        ...


class WebViewEvents(Protocol):
    """The pywebview events required to enforce and observe the native shell."""

    initialized: WebViewInitializedEvent
    loaded: WebViewLifecycleEvent
    closed: WebViewLifecycleEvent
    response_received: WebViewResponseReceivedEvent
    _pywebviewready: WebViewLifecycleEvent


class WebViewBackend(Protocol):
    """The pywebview module behavior used by the desktop adapter."""

    def create_window(self, title: str, url: str, **kwargs: object) -> WebViewWindow | None:
        """Create one native window without starting its event loop."""
        ...

    def start(self, func: Callable[[], None] | None = None, **kwargs: object) -> None:
        """Start the blocking native GUI event loop."""
        ...


class WindowsUser32(Protocol):
    """The native Windows error-dialog function used by the adapter."""

    def MessageBoxW(  # noqa: N802  # The protocol must match the external Win32 API symbol.
        self,
        owner: object | None,
        message: str,
        title: str,
        flags: int,
    ) -> int:
        """Display a modal Unicode message box."""
        ...


class WindowsRegistryKey(Protocol):
    """Context-managed Windows registry key used by the WebView2 preflight."""

    def __enter__(self) -> object:
        """Return the opened registry key."""
        ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: object,
    ) -> bool | None:
        """Close the opened registry key."""
        ...


class WindowsRegistry(Protocol):
    """Windows registry behavior required to detect the shared WebView2 Runtime."""

    HKEY_CURRENT_USER: object
    HKEY_LOCAL_MACHINE: object

    def OpenKey(self, hive: object, key: str) -> WindowsRegistryKey:  # noqa: N802  # External API symbol.
        """Open one WebView2 runtime registry key."""
        ...

    def QueryValueEx(self, key: object, value_name: str) -> tuple[object, int]:  # noqa: N802  # External API symbol.
        """Read one WebView2 runtime registry value."""
        ...


def _load_pywebview() -> WebViewBackend:
    try:
        module = importlib.import_module("webview")
    except ModuleNotFoundError as exc:
        msg = "The OMYM2 Desktop WebView dependency is not installed."
        raise DesktopWindowError(msg) from exc
    return cast("WebViewBackend", cast("object", module))


def _load_windows_user32() -> WindowsUser32:
    library_loader = cast("Callable[..., object]", ctypes.WinDLL)
    return cast("WindowsUser32", library_loader("user32", use_last_error=True))


def _load_windows_registry() -> WindowsRegistry:
    try:
        module = importlib.import_module("winreg")
    except ModuleNotFoundError as exc:
        msg = "The Windows registry API is unavailable."
        raise DesktopWindowError(msg) from exc
    return cast("WindowsRegistry", cast("object", module))


def _require_webview2_runtime(
    registry_loader: Callable[[], WindowsRegistry] = _load_windows_registry,
    *,
    executable_name: str | None = None,
) -> str:
    """Return the supported shared Evergreen WebView2 version or fail before pywebview can fall back."""
    registry = registry_loader()
    policy_application_name = Path(sys.executable).name if executable_name is None else executable_name
    _require_unmodified_webview2_registry_policy(registry, policy_application_name)
    try:
        with registry.OpenKey(registry.HKEY_LOCAL_MACHINE, DESKTOP_WEBVIEW2_DOTNET_REGISTRY_KEY) as key:
            dotnet_release, _value_type = registry.QueryValueEx(
                key,
                DESKTOP_WEBVIEW2_DOTNET_REGISTRY_RELEASE_VALUE,
            )
    except AttributeError, OSError:
        dotnet_release = None
    if (
        not isinstance(dotnet_release, int)
        or isinstance(dotnet_release, bool)
        or dotnet_release < DESKTOP_WEBVIEW2_MINIMUM_DOTNET_RELEASE
    ):
        msg = "The Microsoft .NET Framework required by the EdgeChromium desktop backend is missing or too old."
        raise DesktopWindowError(msg)
    versions: list[tuple[tuple[int, int, int, int], str]] = []
    for hive, key_path in (
        (registry.HKEY_LOCAL_MACHINE, DESKTOP_WEBVIEW2_MACHINE_REGISTRY_KEY),
        (registry.HKEY_CURRENT_USER, DESKTOP_WEBVIEW2_USER_REGISTRY_KEY),
    ):
        try:
            with registry.OpenKey(hive, key_path) as key:
                raw_version, _value_type = registry.QueryValueEx(key, DESKTOP_WEBVIEW2_REGISTRY_VERSION_VALUE)
        except FileNotFoundError:
            continue
        except (AttributeError, OSError) as exc:
            msg = "A shared Evergreen Microsoft Edge WebView2 Runtime registration could not be inspected."
            raise DesktopWindowError(msg) from exc
        parsed_version = _parse_webview2_version(raw_version)
        if parsed_version is None or parsed_version < DESKTOP_WEBVIEW2_MINIMUM_VERSION:
            msg = "A shared Evergreen Microsoft Edge WebView2 Runtime registration is invalid or too old."
            raise DesktopWindowError(msg)
        versions.append((parsed_version, cast("str", raw_version)))
    if not versions:
        msg = "The shared Evergreen Microsoft Edge WebView2 Runtime is missing or too old."
        raise DesktopWindowError(msg)
    _parsed_version, display_version = min(versions)
    return display_version


def _require_unmodified_webview2_registry_policy(registry: WindowsRegistry, executable_name: str) -> None:
    """Reject applicable machine or user policies that can replace the checked WebView2 environment."""
    for hive in (registry.HKEY_LOCAL_MACHINE, registry.HKEY_CURRENT_USER):
        for policy_name in DESKTOP_WEBVIEW2_POLICY_NAMES:
            application_ids = (executable_name,)
            if policy_name not in DESKTOP_WEBVIEW2_POLICY_APPLICATION_ONLY_NAMES:
                application_ids += (DESKTOP_WEBVIEW2_POLICY_WILDCARD_APPLICATION_ID,)
            policy_path = rf"{DESKTOP_WEBVIEW2_POLICY_REGISTRY_ROOT}\{policy_name}"
            try:
                with registry.OpenKey(hive, policy_path) as key:
                    for application_id in application_ids:
                        try:
                            _policy_value, _value_type = registry.QueryValueEx(key, application_id)
                        except FileNotFoundError:
                            continue
                        except OSError as exc:
                            msg = f"The WebView2 policy override {policy_name!r} could not be inspected."
                            raise DesktopWindowError(msg) from exc
                        msg = f"Unsupported WebView2 policy override {policy_name!r} for {application_id!r}."
                        raise DesktopWindowError(msg)
            except FileNotFoundError:
                continue
            except OSError as exc:
                msg = f"The WebView2 policy override {policy_name!r} could not be inspected."
                raise DesktopWindowError(msg) from exc


def _require_unmodified_webview2_environment(environment: Mapping[str, str]) -> None:
    """Reject inherited variables that can replace or debug the selected WebView2 environment."""
    overrides = sorted(
        key for key in environment if key.upper().startswith(DESKTOP_WEBVIEW2_ENVIRONMENT_OVERRIDE_PREFIXES)
    )
    if overrides:
        joined_names = ", ".join(overrides)
        msg = f"Unsupported inherited WebView2 environment override(s): {joined_names}."
        raise DesktopWindowError(msg)


def _parse_webview2_version(raw_version: object) -> tuple[int, int, int, int] | None:
    if not isinstance(raw_version, str):
        return None
    parts = raw_version.split(".")
    if len(parts) != len(DESKTOP_WEBVIEW2_MINIMUM_VERSION) or any(not part.isdecimal() for part in parts):
        return None
    return cast("tuple[int, int, int, int]", tuple(int(part) for part in parts))


def _create_native_window(backend: WebViewBackend, url: str) -> WebViewWindow:
    window = backend.create_window(
        DESKTOP_WINDOW_TITLE,
        url,
        width=DESKTOP_WINDOW_WIDTH,
        height=DESKTOP_WINDOW_HEIGHT,
        resizable=DESKTOP_WINDOW_RESIZABLE,
        min_size=(DESKTOP_WINDOW_MIN_WIDTH, DESKTOP_WINDOW_MIN_HEIGHT),
        maximized=DESKTOP_WINDOW_MAXIMIZED,
        background_color=DESKTOP_WINDOW_BACKGROUND_COLOR,
    )
    if window is None:
        msg = "pywebview did not create the OMYM2 window."
        raise DesktopWindowError(msg)
    return window


def _close_failed_window(
    window: WebViewWindow,
    failures: list[tuple[DesktopWindowError, BaseException | None]],
    failure: DesktopWindowError,
    cause: BaseException | None = None,
) -> None:
    """Record one startup failure and close the blank or non-interactive window."""
    failures.append((failure, cause))
    try:
        window.destroy()
    except Exception:
        LOGGER.exception("Failed to close the native window after a desktop startup error")


def _raise_startup_failure(failure: tuple[DesktopWindowError, BaseException | None]) -> None:
    """Raise a background startup failure on the GUI thread with its diagnostic cause."""
    error, cause = failure
    if cause is None:
        raise error
    raise error from cause


@dataclass(slots=True)
class _WindowStartupMonitor:
    """Bound native document initialization without blocking the GUI thread."""

    window: WebViewWindow
    expected_url: str
    content_load_timeout_seconds: float
    content_loaded: Event = field(default_factory=Event)
    lifecycle_changed: Event = field(default_factory=Event)
    root_response_received: Event = field(default_factory=Event)
    root_response_status_codes: list[int] = field(default_factory=list)
    window_closed: Event = field(default_factory=Event)
    failures: list[tuple[DesktopWindowError, BaseException | None]] = field(default_factory=list)

    def record_content_loaded(self) -> None:
        """Wake the monitor after pywebview reports document navigation complete."""
        self.content_loaded.set()
        self._signal_complete_document()

    def record_response(self, response: WebViewResponse) -> None:
        """Record the exact root URL response without treating assets as the document."""
        if response.url != self.expected_url or self.root_response_received.is_set():
            return
        self.root_response_status_codes.append(response.status_code)
        self.root_response_received.set()
        self._signal_complete_document()

    def record_window_closed(self) -> None:
        """Wake the monitor when the user closes during startup."""
        self.window_closed.set()
        self.lifecycle_changed.set()

    def run(self) -> None:
        """Wait for a document whose pinned pywebview injection completed successfully."""
        if not self.lifecycle_changed.wait(self.content_load_timeout_seconds):
            self._fail("The native WebView did not load the OMYM2 document in time.")
            return
        if self.window_closed.is_set():
            return
        if not self.content_loaded.is_set():
            self._fail("The native WebView closed before loading the OMYM2 document.")
            return
        if not self.root_response_received.is_set():
            self._fail("The native WebView did not receive the OMYM2 root document response.")
            return
        if self.root_response_status_codes[0] != HTTP_OK_STATUS:
            status_code = self.root_response_status_codes[0]
            self._fail(f"The native WebView received HTTP {status_code} for the OMYM2 root document.")
            return
        if not self.window.events._pywebviewready.is_set():  # noqa: SLF001  # pyright: ignore[reportPrivateUsage] -- Pinned pywebview event distinguishes its injection error path.
            self._fail("The native WebView could not initialize the OMYM2 document bridge.")
            return
        LOGGER.info(DESKTOP_WEBVIEW_CONTENT_LOADED_LOG_MARKER)

    def _signal_complete_document(self) -> None:
        if self.content_loaded.is_set() and self.root_response_received.is_set():
            self.lifecycle_changed.set()

    def _fail(self, message: str, cause: BaseException | None = None) -> None:
        _close_failed_window(self.window, self.failures, DesktopWindowError(message), cause)


def _run_native_window(
    backend: WebViewBackend,
    url: str,
    *,
    content_load_timeout_seconds: float,
) -> None:
    """Run one native window and fail closed when its document cannot initialize."""
    window = _create_native_window(backend, url)
    renderer_failures: list[DesktopWindowError] = []
    monitor = _WindowStartupMonitor(
        window=window,
        expected_url=url,
        content_load_timeout_seconds=content_load_timeout_seconds,
    )

    def require_renderer(renderer: str) -> bool | None:
        LOGGER.info("Desktop WebView initialized backend=%s", renderer)
        if renderer == DESKTOP_WEBVIEW_BACKEND:
            return None
        renderer_failures.append(DesktopWindowError(f"Unsupported desktop WebView backend {renderer!r}."))
        return False

    window.events.initialized += require_renderer
    window.events.loaded += monitor.record_content_loaded
    window.events.closed += monitor.record_window_closed
    window.events.response_received += monitor.record_response
    backend.start(
        func=monitor.run,
        gui=DESKTOP_WEBVIEW_BACKEND,
        private_mode=DESKTOP_WEBVIEW_PRIVATE_MODE,
    )
    if renderer_failures:
        raise renderer_failures[0]
    if monitor.failures:
        _raise_startup_failure(monitor.failures[0])


def _require_dialog_success(result: int) -> None:
    if result == 0:
        message = "The native Windows error dialog reported a failure."
        raise OSError(message)


@dataclass(slots=True)
class PyWebViewWindow:
    """Create and run the single pywebview window used by OMYM2 Desktop."""

    backend_loader: Callable[[], WebViewBackend] = _load_pywebview
    runtime_probe: Callable[[], str] = _require_webview2_runtime
    environment: Mapping[str, str] = field(default_factory=lambda: os.environ)
    content_load_timeout_seconds: float = DESKTOP_WEBVIEW_CONTENT_LOAD_TIMEOUT_SECONDS

    def show(self, url: str) -> None:
        """Display the ready loopback application until its native window closes."""
        _require_unmodified_webview2_environment(self.environment)
        runtime_version = self.runtime_probe()
        LOGGER.info("Evergreen WebView2 Runtime ready version=%s", runtime_version)
        backend = self.backend_loader()
        try:
            _run_native_window(
                backend,
                url,
                content_load_timeout_seconds=self.content_load_timeout_seconds,
            )
        except DesktopWindowError:
            raise
        except Exception as exc:
            msg = "The OMYM2 native window failed."
            raise DesktopWindowError(msg) from exc


@dataclass(frozen=True, slots=True)
class WindowsErrorDialog:
    """Report fatal startup errors through the supported platform's native dialog."""

    stderr: TextIO | None = field(default_factory=lambda: sys.stderr)
    platform: str = field(default_factory=lambda: sys.platform)
    user32_loader: Callable[[], WindowsUser32] = _load_windows_user32

    def show(self, title: str, message: str) -> None:
        """Display a native Windows error and retain a stderr fallback for diagnostics."""
        if self.platform != DESKTOP_SUPPORTED_PLATFORM:
            self._write_stderr(title, message)
            return
        try:
            dialog_result = self.user32_loader().MessageBoxW(None, message, title, DESKTOP_ERROR_DIALOG_FLAGS)
            _require_dialog_success(dialog_result)
        except Exception:
            with suppress(Exception):
                LOGGER.exception("Native desktop error dialog failed")
            self._write_stderr(title, message)

    def _write_stderr(self, title: str, message: str) -> None:
        if self.stderr is None:
            return
        with suppress(Exception):
            _ = self.stderr.write(f"{title}: {message}\n")
