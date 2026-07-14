"""
Summary: Tests the native desktop window adapter without opening a real window.
Why: Protects the one-window, no-bridge, Windows WebView configuration contract.
"""

from __future__ import annotations

import logging
from io import StringIO
from typing import TYPE_CHECKING, Self, cast, final, override

import pytest

from omym2.adapters.desktop.window import (
    DesktopWindowError,
    PyWebViewWindow,
    WebViewResponse,
    WebViewWindow,
    WindowsErrorDialog,
    _require_webview2_runtime,  # pyright: ignore[reportPrivateUsage] -- directly verifies the required runtime guard.
)
from omym2.config import (
    DESKTOP_ERROR_DIALOG_FLAGS,
    DESKTOP_SUPPORTED_PLATFORM,
    DESKTOP_WEBVIEW2_DOTNET_REGISTRY_KEY,
    DESKTOP_WEBVIEW2_DOTNET_REGISTRY_RELEASE_VALUE,
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
    HTTP_INTERNAL_ERROR_STATUS,
    HTTP_OK_STATUS,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

TEST_IMMEDIATE_TIMEOUT_SECONDS = 0.0  # unit-test timeout that completes without wall-clock delay, seconds, exactly 0
TEST_DESKTOP_EXECUTABLE_NAME = "OMYM2.exe"  # packaged executable name used to select applicable WebView2 policies
TEST_OTHER_EXECUTABLE_NAME = "Other.exe"  # unrelated executable name whose WebView2 policies must be ignored
TEST_POLICY_VALUE = "untrusted-value"  # arbitrary WebView2 policy value that must never appear in an error
TEST_REGISTRY_ACCESS_ERROR = "registry access denied"  # diagnostic cause for unreadable WebView2 state


class RecordingInitializedEvent:
    """Records and synchronously emits pywebview initialization callbacks."""

    def __init__(self) -> None:
        self.callbacks: list[Callable[[str], bool | None]] = []

    def __iadd__(self, callback: Callable[[str], bool | None]) -> Self:
        self.callbacks.append(callback)
        return self

    def emit(self, renderer: str) -> bool:
        return any(callback(renderer) is False for callback in self.callbacks)


@final
class RecordingLifecycleEvent:
    """Records and emits one zero-argument pywebview lifecycle event."""

    def __init__(self) -> None:
        self.callbacks: list[Callable[[], None]] = []
        self.emitted: bool = False

    def __iadd__(self, callback: Callable[[], None]) -> Self:
        self.callbacks.append(callback)
        return self

    def emit(self) -> None:
        self.emitted = True
        for callback in self.callbacks:
            callback()

    def is_set(self) -> bool:
        return self.emitted


@final
class RecordingResponseEvent:
    """Records and emits pywebview Web resource response callbacks."""

    def __init__(self) -> None:
        self.callbacks: list[Callable[[WebViewResponse], None]] = []

    def __iadd__(self, callback: Callable[[WebViewResponse], None]) -> Self:
        self.callbacks.append(callback)
        return self

    def emit(self, response: WebViewResponse) -> None:
        for callback in self.callbacks:
            callback(response)


@final
class FakeWindowEvents:
    """Provides the fake lifecycle events required by the desktop shell."""

    def __init__(self) -> None:
        self.initialized = RecordingInitializedEvent()
        self.loaded = RecordingLifecycleEvent()
        self.closed = RecordingLifecycleEvent()
        self.response_received = RecordingResponseEvent()
        self._pywebviewready = RecordingLifecycleEvent()

    def emit_document_bridge_ready(self) -> None:
        self._pywebviewready.emit()


@final
class FakeWebViewResponse:
    """Provides the root-response fields observed by the desktop startup monitor."""

    def __init__(self, url: str, status_code: int) -> None:
        self.url = url
        self.status_code = status_code


@final
class FakeNativeWindow:
    """Represents the native window returned by the fake backend."""

    def __init__(self) -> None:
        self.events = FakeWindowEvents()
        self.destroy_calls = 0

    def destroy(self) -> None:
        self.destroy_calls += 1
        self.events.closed.emit()


class RecordingWebViewBackend:
    """Records pywebview calls made by the adapter."""

    renderer: str = DESKTOP_WEBVIEW_BACKEND

    def __init__(
        self,
        *,
        create_result: FakeNativeWindow | None = None,
        failure: Exception | None = None,
    ) -> None:
        self.create_result: FakeNativeWindow = FakeNativeWindow() if create_result is None else create_result
        self.emit_document_bridge_ready: bool = True
        self.emit_loaded: bool = True
        self.emit_root_response: bool = True
        self.emit_closed: bool = False
        self.failure: Exception | None = failure
        self.root_response_status_code: int = HTTP_OK_STATUS
        self.create_calls: list[tuple[str, str, dict[str, object]]] = []
        self.start_calls: list[tuple[Callable[[], None] | None, dict[str, object]]] = []

    def create_window(self, title: str, url: str, **kwargs: object) -> WebViewWindow | None:
        self.create_calls.append((title, url, kwargs))
        if self.failure is not None:
            raise self.failure
        return cast("WebViewWindow | None", cast("object", self.create_result))

    def start(self, func: Callable[[], None] | None = None, **kwargs: object) -> None:
        self.start_calls.append((func, kwargs))
        if self.failure is not None:
            raise self.failure
        if self.create_result.events.initialized.emit(self.renderer):
            return
        if self.emit_root_response:
            self.create_result.events.response_received.emit(
                FakeWebViewResponse(self.create_calls[-1][1], self.root_response_status_code)
            )
        if self.emit_document_bridge_ready:
            self.create_result.events.emit_document_bridge_ready()
        if self.emit_loaded:
            self.create_result.events.loaded.emit()
        if self.emit_closed:
            self.create_result.events.closed.emit()
        if func is not None:
            func()


@final
class NullWebViewBackend(RecordingWebViewBackend):
    """Returns no window to exercise pywebview creation failure."""

    @override
    def create_window(self, title: str, url: str, **kwargs: object) -> None:
        self.create_calls.append((title, url, kwargs))


@final
class RecordingUser32:
    """Records one Windows Unicode message-box invocation."""

    def __init__(self, *, result: int = 1) -> None:
        self.calls: list[tuple[object | None, str, str, int]] = []
        self.result = result

    def MessageBoxW(  # noqa: N802  # The fake must match the external Win32 API symbol.
        self,
        owner: object | None,
        message: str,
        title: str,
        flags: int,
    ) -> int:
        self.calls.append((owner, message, title, flags))
        return self.result


@final
class RecordingRegistryKey:
    """Provides one context-managed fake registry value."""

    def __init__(self, identity: tuple[object, str]) -> None:
        self.identity = identity

    def __enter__(self) -> object:
        return self.identity

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: object,
    ) -> None:
        return None


@final
class RecordingRegistry:
    """Records WebView2 runtime lookups against injected registry values."""

    HKEY_CURRENT_USER: object = object()
    HKEY_LOCAL_MACHINE: object = object()

    def __init__(
        self,
        versions: Mapping[tuple[object, str], object],
        *,
        policy_values: Mapping[tuple[object, str, str], object] | None = None,
        open_errors: Mapping[tuple[object, str], OSError] | None = None,
        query_errors: Mapping[tuple[object, str, str], OSError] | None = None,
    ) -> None:
        self.versions: Mapping[tuple[object, str], object] = versions
        self.policy_values: Mapping[tuple[object, str, str], object] = {} if policy_values is None else policy_values
        self.open_errors: Mapping[tuple[object, str], OSError] = {} if open_errors is None else open_errors
        self.query_errors: Mapping[tuple[object, str, str], OSError] = {} if query_errors is None else query_errors
        self.queries: list[tuple[object, str]] = []
        self.policy_queries: list[tuple[object, str, str]] = []

    def OpenKey(self, hive: object, key: str) -> RecordingRegistryKey:  # noqa: N802  # Mirrors winreg.
        identity = (hive, key)
        if identity in self.open_errors:
            raise self.open_errors[identity]
        has_policy_values = any(
            policy_hive is hive and policy_key == key
            for policy_hive, policy_key, _ in (*self.policy_values, *self.query_errors)
        )
        if identity not in self.versions and not has_policy_values:
            raise FileNotFoundError(key)
        return RecordingRegistryKey(identity)

    def QueryValueEx(self, key: object, value_name: str) -> tuple[object, int]:  # noqa: N802  # Mirrors winreg.
        identity = cast("tuple[object, str]", key)
        policy_identity = (identity[0], identity[1], value_name)
        if policy_identity in self.query_errors:
            raise self.query_errors[policy_identity]
        if policy_identity in self.policy_values:
            self.policy_queries.append(policy_identity)
            return self.policy_values[policy_identity], 1
        if any(
            policy_hive is identity[0] and policy_key == identity[1]
            for policy_hive, policy_key, _ in (*self.policy_values, *self.query_errors)
        ):
            raise FileNotFoundError(value_name)
        self.queries.append(identity)
        expected_value_name = (
            DESKTOP_WEBVIEW2_DOTNET_REGISTRY_RELEASE_VALUE
            if identity[1] == DESKTOP_WEBVIEW2_DOTNET_REGISTRY_KEY
            else DESKTOP_WEBVIEW2_REGISTRY_VERSION_VALUE
        )
        assert value_name == expected_value_name
        return self.versions[identity], 1


def _supported_runtime_registry_values() -> dict[tuple[object, str], object]:
    """Return the minimum complete registry state accepted by the desktop preflight."""
    minimum_version = ".".join(str(part) for part in DESKTOP_WEBVIEW2_MINIMUM_VERSION)
    return {
        (RecordingRegistry.HKEY_LOCAL_MACHINE, DESKTOP_WEBVIEW2_DOTNET_REGISTRY_KEY): (
            DESKTOP_WEBVIEW2_MINIMUM_DOTNET_RELEASE
        ),
        (RecordingRegistry.HKEY_LOCAL_MACHINE, DESKTOP_WEBVIEW2_MACHINE_REGISTRY_KEY): minimum_version,
    }


@pytest.mark.parametrize("policy_name", DESKTOP_WEBVIEW2_POLICY_NAMES)
@pytest.mark.parametrize(
    "hive",
    [RecordingRegistry.HKEY_LOCAL_MACHINE, RecordingRegistry.HKEY_CURRENT_USER],
    ids=["machine", "user"],
)
def test_webview2_runtime_probe_rejects_app_specific_policy_override(policy_name: str, hive: object) -> None:
    """Every loader override for the packaged executable fails before runtime selection."""
    policy_key = rf"{DESKTOP_WEBVIEW2_POLICY_REGISTRY_ROOT}\{policy_name}"
    policy_identity = (hive, policy_key, TEST_DESKTOP_EXECUTABLE_NAME)
    registry = RecordingRegistry(
        _supported_runtime_registry_values(),
        policy_values={policy_identity: TEST_POLICY_VALUE},
    )

    with pytest.raises(DesktopWindowError, match="Unsupported WebView2 policy override") as exc_info:
        _ = _require_webview2_runtime(lambda: registry, executable_name=TEST_DESKTOP_EXECUTABLE_NAME)

    assert policy_name in str(exc_info.value)
    assert TEST_DESKTOP_EXECUTABLE_NAME in str(exc_info.value)
    assert TEST_POLICY_VALUE not in str(exc_info.value)
    assert registry.policy_queries == [policy_identity]
    assert registry.queries == []


@pytest.mark.parametrize(
    "policy_name",
    tuple(name for name in DESKTOP_WEBVIEW2_POLICY_NAMES if name not in DESKTOP_WEBVIEW2_POLICY_APPLICATION_ONLY_NAMES),
)
def test_webview2_runtime_probe_rejects_wildcard_policy_override(policy_name: str) -> None:
    """A wildcard loader policy applies to OMYM2 even without an executable-specific value."""
    policy_key = rf"{DESKTOP_WEBVIEW2_POLICY_REGISTRY_ROOT}\{policy_name}"
    policy_identity = (
        RecordingRegistry.HKEY_CURRENT_USER,
        policy_key,
        DESKTOP_WEBVIEW2_POLICY_WILDCARD_APPLICATION_ID,
    )
    registry = RecordingRegistry(
        _supported_runtime_registry_values(),
        policy_values={policy_identity: TEST_POLICY_VALUE},
    )

    with pytest.raises(DesktopWindowError, match="Unsupported WebView2 policy override") as exc_info:
        _ = _require_webview2_runtime(lambda: registry, executable_name=TEST_DESKTOP_EXECUTABLE_NAME)

    assert policy_name in str(exc_info.value)
    assert DESKTOP_WEBVIEW2_POLICY_WILDCARD_APPLICATION_ID in str(exc_info.value)
    assert TEST_POLICY_VALUE not in str(exc_info.value)
    assert registry.policy_queries == [policy_identity]
    assert registry.queries == []


def test_webview2_runtime_probe_ignores_policy_for_another_executable() -> None:
    """An application-scoped policy for another host does not alter the OMYM2 environment."""
    policy_name = DESKTOP_WEBVIEW2_POLICY_NAMES[0]
    policy_key = rf"{DESKTOP_WEBVIEW2_POLICY_REGISTRY_ROOT}\{policy_name}"
    registry = RecordingRegistry(
        _supported_runtime_registry_values(),
        policy_values={
            (RecordingRegistry.HKEY_LOCAL_MACHINE, policy_key, TEST_OTHER_EXECUTABLE_NAME): TEST_POLICY_VALUE
        },
    )

    result = _require_webview2_runtime(lambda: registry, executable_name=TEST_DESKTOP_EXECUTABLE_NAME)

    assert result == ".".join(str(part) for part in DESKTOP_WEBVIEW2_MINIMUM_VERSION)
    assert registry.policy_queries == []


def test_webview2_runtime_probe_ignores_unsupported_wildcard_user_data_policy() -> None:
    """WebView2 does not apply a wildcard UserDataFolder policy to any host."""
    policy_name = DESKTOP_WEBVIEW2_POLICY_APPLICATION_ONLY_NAMES[0]
    policy_key = rf"{DESKTOP_WEBVIEW2_POLICY_REGISTRY_ROOT}\{policy_name}"
    registry = RecordingRegistry(
        _supported_runtime_registry_values(),
        policy_values={
            (
                RecordingRegistry.HKEY_CURRENT_USER,
                policy_key,
                DESKTOP_WEBVIEW2_POLICY_WILDCARD_APPLICATION_ID,
            ): TEST_POLICY_VALUE
        },
    )

    result = _require_webview2_runtime(lambda: registry, executable_name=TEST_DESKTOP_EXECUTABLE_NAME)

    assert result == ".".join(str(part) for part in DESKTOP_WEBVIEW2_MINIMUM_VERSION)
    assert registry.policy_queries == []


@pytest.mark.parametrize("failure_location", ["open", "query"])
def test_webview2_runtime_probe_fails_closed_when_policy_registry_is_unreadable(failure_location: str) -> None:
    """A policy inspection error cannot be treated as proof that no override exists."""
    policy_name = DESKTOP_WEBVIEW2_POLICY_NAMES[0]
    policy_key = rf"{DESKTOP_WEBVIEW2_POLICY_REGISTRY_ROOT}\{policy_name}"
    key_identity = (RecordingRegistry.HKEY_LOCAL_MACHINE, policy_key)
    value_identity = (*key_identity, TEST_DESKTOP_EXECUTABLE_NAME)
    error = PermissionError(TEST_REGISTRY_ACCESS_ERROR)
    registry = RecordingRegistry(
        _supported_runtime_registry_values(),
        policy_values={} if failure_location == "open" else {value_identity: TEST_POLICY_VALUE},
        open_errors={key_identity: error} if failure_location == "open" else {},
        query_errors={value_identity: error} if failure_location == "query" else {},
    )

    with pytest.raises(DesktopWindowError, match="could not be inspected") as exc_info:
        _ = _require_webview2_runtime(lambda: registry, executable_name=TEST_DESKTOP_EXECUTABLE_NAME)

    assert exc_info.value.__cause__ is error
    assert registry.queries == []


def _runtime_probe() -> str:
    return ".".join(str(part) for part in DESKTOP_WEBVIEW2_MINIMUM_VERSION)


def test_window_uses_one_native_window_without_javascript_bridge(caplog: pytest.LogCaptureFixture) -> None:
    """The existing loopback UI opens with the complete desktop-only configuration."""
    backend = RecordingWebViewBackend()
    application_url = "http://127.0.0.1:49152/"

    with caplog.at_level(logging.INFO):
        PyWebViewWindow(backend_loader=lambda: backend, runtime_probe=_runtime_probe, environment={}).show(
            application_url
        )

    assert backend.create_calls == [
        (
            DESKTOP_WINDOW_TITLE,
            application_url,
            {
                "width": DESKTOP_WINDOW_WIDTH,
                "height": DESKTOP_WINDOW_HEIGHT,
                "resizable": DESKTOP_WINDOW_RESIZABLE,
                "min_size": (DESKTOP_WINDOW_MIN_WIDTH, DESKTOP_WINDOW_MIN_HEIGHT),
                "maximized": DESKTOP_WINDOW_MAXIMIZED,
                "background_color": DESKTOP_WINDOW_BACKGROUND_COLOR,
            },
        )
    ]
    assert "js_api" not in backend.create_calls[0][2]
    assert len(backend.start_calls) == 1
    start_function, start_options = backend.start_calls[0]
    assert callable(start_function)
    assert start_options == {
        "gui": DESKTOP_WEBVIEW_BACKEND,
        "private_mode": DESKTOP_WEBVIEW_PRIVATE_MODE,
    }
    assert DESKTOP_WEBVIEW_CONTENT_LOADED_LOG_MARKER in caplog.messages


def test_window_rejects_missing_native_window() -> None:
    """A backend that cannot create a window becomes a typed startup failure."""
    backend = NullWebViewBackend()

    with pytest.raises(DesktopWindowError, match="did not create"):
        PyWebViewWindow(backend_loader=lambda: backend, runtime_probe=_runtime_probe, environment={}).show(
            "http://127.0.0.1:49152/"
        )


def test_window_wraps_native_backend_failure() -> None:
    """Backend details stay in the exception chain instead of becoming user-facing text."""
    native_failure = RuntimeError("native details")
    backend = RecordingWebViewBackend(failure=native_failure)

    with pytest.raises(DesktopWindowError, match="native window failed") as exc_info:
        PyWebViewWindow(backend_loader=lambda: backend, runtime_probe=_runtime_probe, environment={}).show(
            "http://127.0.0.1:49152/"
        )

    assert exc_info.value.__cause__ is native_failure


def test_window_requires_shared_evergreen_webview2_before_loading_pywebview() -> None:
    """Missing WebView2 fails instead of allowing pywebview's deprecated MSHTML fallback."""
    backend_loaded = False

    def load_backend() -> RecordingWebViewBackend:
        nonlocal backend_loaded
        backend_loaded = True
        return RecordingWebViewBackend()

    def fail_runtime_probe() -> str:
        message = "WebView2 missing"
        raise DesktopWindowError(message)

    with pytest.raises(DesktopWindowError, match="WebView2 missing"):
        PyWebViewWindow(backend_loader=load_backend, runtime_probe=fail_runtime_probe, environment={}).show(
            "http://127.0.0.1:49152/"
        )

    assert backend_loaded is False


def test_window_rejects_renderer_fallback_before_native_window_creation_completes() -> None:
    """The synchronous initialized guard aborts pywebview's MSHTML fallback path."""
    backend = RecordingWebViewBackend()
    backend.renderer = "mshtml"

    with pytest.raises(DesktopWindowError, match="Unsupported desktop WebView backend 'mshtml'"):
        PyWebViewWindow(backend_loader=lambda: backend, runtime_probe=_runtime_probe, environment={}).show(
            "http://127.0.0.1:49152/"
        )

    assert backend.create_result is not None
    assert len(backend.create_result.events.initialized.callbacks) == 1


@pytest.mark.parametrize(
    "variable_name",
    ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "webview2_browser_executable_folder", "COREWEBVIEW2_MAX_INSTANCES"],
)
def test_window_rejects_inherited_webview2_environment_overrides(variable_name: str) -> None:
    """User-controlled runtime and debugger overrides fail before native dependencies load."""
    backend_loaded = False

    def load_backend() -> RecordingWebViewBackend:
        nonlocal backend_loaded
        backend_loaded = True
        return RecordingWebViewBackend()

    with pytest.raises(DesktopWindowError, match=variable_name):
        PyWebViewWindow(
            backend_loader=load_backend,
            runtime_probe=_runtime_probe,
            environment={variable_name: "untrusted-value"},
        ).show("http://127.0.0.1:49152/")

    assert backend_loaded is False


def test_window_closes_and_reports_document_load_timeout() -> None:
    """A WebView2 navigation failure cannot leave an indefinite blank native window."""
    native_window = FakeNativeWindow()
    backend = RecordingWebViewBackend(create_result=native_window)
    backend.emit_loaded = False

    with pytest.raises(DesktopWindowError, match="did not load"):
        PyWebViewWindow(
            backend_loader=lambda: backend,
            runtime_probe=_runtime_probe,
            environment={},
            content_load_timeout_seconds=TEST_IMMEDIATE_TIMEOUT_SECONDS,
        ).show("http://127.0.0.1:49152/")

    assert native_window.destroy_calls == 1


def test_window_requires_exact_root_document_response() -> None:
    """Asset or error-page activity cannot substitute for the loopback root response."""
    native_window = FakeNativeWindow()
    backend = RecordingWebViewBackend(create_result=native_window)
    backend.emit_root_response = False

    with pytest.raises(DesktopWindowError, match="did not load"):
        PyWebViewWindow(
            backend_loader=lambda: backend,
            runtime_probe=_runtime_probe,
            environment={},
            content_load_timeout_seconds=TEST_IMMEDIATE_TIMEOUT_SECONDS,
        ).show("http://127.0.0.1:49152/")

    assert native_window.destroy_calls == 1


def test_window_rejects_unsuccessful_root_document_response() -> None:
    """The native content marker requires a successful response for the exact root URL."""
    native_window = FakeNativeWindow()
    backend = RecordingWebViewBackend(create_result=native_window)
    backend.root_response_status_code = HTTP_INTERNAL_ERROR_STATUS

    with pytest.raises(DesktopWindowError, match=f"HTTP {HTTP_INTERNAL_ERROR_STATUS}"):
        PyWebViewWindow(backend_loader=lambda: backend, runtime_probe=_runtime_probe, environment={}).show(
            "http://127.0.0.1:49152/"
        )

    assert native_window.destroy_calls == 1


def test_window_rejects_loaded_event_when_pywebview_document_injection_failed() -> None:
    """pywebview's error-path loaded event cannot pass a blank document as ready."""
    native_window = FakeNativeWindow()
    backend = RecordingWebViewBackend(create_result=native_window)
    backend.emit_document_bridge_ready = False

    with pytest.raises(DesktopWindowError, match="document bridge"):
        PyWebViewWindow(backend_loader=lambda: backend, runtime_probe=_runtime_probe, environment={}).show(
            "http://127.0.0.1:49152/"
        )

    assert native_window.destroy_calls == 1


def test_window_allows_user_close_before_document_load() -> None:
    """An intentional early close exits without manufacturing a startup failure or timeout delay."""
    native_window = FakeNativeWindow()
    backend = RecordingWebViewBackend(create_result=native_window)
    backend.emit_loaded = False
    backend.emit_closed = True

    PyWebViewWindow(backend_loader=lambda: backend, runtime_probe=_runtime_probe, environment={}).show(
        "http://127.0.0.1:49152/"
    )

    assert native_window.destroy_calls == 0


def test_webview2_runtime_probe_reports_guaranteed_floor_across_supported_registrations() -> None:
    """Every registered Runtime is checked and the lowest guaranteed version is reported."""
    minimum_version = ".".join(str(part) for part in DESKTOP_WEBVIEW2_MINIMUM_VERSION)
    newer_version = ".".join(str(part + 1) for part in DESKTOP_WEBVIEW2_MINIMUM_VERSION)
    registry = RecordingRegistry(
        {
            (RecordingRegistry.HKEY_LOCAL_MACHINE, DESKTOP_WEBVIEW2_DOTNET_REGISTRY_KEY): (
                DESKTOP_WEBVIEW2_MINIMUM_DOTNET_RELEASE
            ),
            (RecordingRegistry.HKEY_LOCAL_MACHINE, DESKTOP_WEBVIEW2_MACHINE_REGISTRY_KEY): minimum_version,
            (RecordingRegistry.HKEY_CURRENT_USER, DESKTOP_WEBVIEW2_USER_REGISTRY_KEY): newer_version,
        }
    )

    result = _require_webview2_runtime(lambda: registry)

    assert result == minimum_version
    assert registry.queries == [
        (RecordingRegistry.HKEY_LOCAL_MACHINE, DESKTOP_WEBVIEW2_DOTNET_REGISTRY_KEY),
        (RecordingRegistry.HKEY_LOCAL_MACHINE, DESKTOP_WEBVIEW2_MACHINE_REGISTRY_KEY),
        (RecordingRegistry.HKEY_CURRENT_USER, DESKTOP_WEBVIEW2_USER_REGISTRY_KEY),
    ]


@pytest.mark.parametrize(
    "runtime_identity",
    [
        (RecordingRegistry.HKEY_LOCAL_MACHINE, DESKTOP_WEBVIEW2_MACHINE_REGISTRY_KEY),
        (RecordingRegistry.HKEY_CURRENT_USER, DESKTOP_WEBVIEW2_USER_REGISTRY_KEY),
    ],
    ids=["machine", "user"],
)
def test_webview2_runtime_probe_accepts_one_supported_registration(runtime_identity: tuple[object, str]) -> None:
    """Either documented Evergreen registration scope can satisfy preflight by itself."""
    minimum_version = ".".join(str(part) for part in DESKTOP_WEBVIEW2_MINIMUM_VERSION)
    values = {
        (RecordingRegistry.HKEY_LOCAL_MACHINE, DESKTOP_WEBVIEW2_DOTNET_REGISTRY_KEY): (
            DESKTOP_WEBVIEW2_MINIMUM_DOTNET_RELEASE
        ),
        runtime_identity: minimum_version,
    }

    result = _require_webview2_runtime(lambda: RecordingRegistry(values))

    assert result == minimum_version


@pytest.mark.parametrize(
    ("first_version", "second_version"),
    [
        ("85.0.621.9", None),
        (None, "85.0.621.9"),
        ("invalid", None),
        (None, "invalid"),
        ("", None),
        (None, ""),
    ],
)
def test_webview2_runtime_probe_rejects_one_bad_registration_alongside_a_current_one(
    first_version: object | None,
    second_version: object | None,
) -> None:
    """A second current registration cannot hide an old, empty, or malformed one."""
    minimum_version = ".".join(str(part) for part in DESKTOP_WEBVIEW2_MINIMUM_VERSION)
    machine_version = minimum_version if first_version is None else first_version
    user_version = minimum_version if second_version is None else second_version
    values = {
        (RecordingRegistry.HKEY_LOCAL_MACHINE, DESKTOP_WEBVIEW2_DOTNET_REGISTRY_KEY): (
            DESKTOP_WEBVIEW2_MINIMUM_DOTNET_RELEASE
        ),
        (RecordingRegistry.HKEY_LOCAL_MACHINE, DESKTOP_WEBVIEW2_MACHINE_REGISTRY_KEY): machine_version,
        (RecordingRegistry.HKEY_CURRENT_USER, DESKTOP_WEBVIEW2_USER_REGISTRY_KEY): user_version,
    }

    with pytest.raises(DesktopWindowError, match="invalid or too old"):
        _ = _require_webview2_runtime(lambda: RecordingRegistry(values))


@pytest.mark.parametrize("failure_location", ["open", "query"])
def test_webview2_runtime_probe_fails_closed_when_runtime_registration_is_unreadable(failure_location: str) -> None:
    """An unreadable second Runtime registration cannot be ignored after finding a current one."""
    values = _supported_runtime_registry_values()
    runtime_key = (RecordingRegistry.HKEY_CURRENT_USER, DESKTOP_WEBVIEW2_USER_REGISTRY_KEY)
    value_key = (*runtime_key, DESKTOP_WEBVIEW2_REGISTRY_VERSION_VALUE)
    error = PermissionError(TEST_REGISTRY_ACCESS_ERROR)
    runtime_values = values if failure_location == "open" else {**values, runtime_key: _runtime_probe()}
    registry = RecordingRegistry(
        runtime_values,
        open_errors={runtime_key: error} if failure_location == "open" else {},
        query_errors={value_key: error} if failure_location == "query" else {},
    )

    with pytest.raises(DesktopWindowError, match="could not be inspected") as exc_info:
        _ = _require_webview2_runtime(lambda: registry)

    assert exc_info.value.__cause__ is error


@pytest.mark.parametrize("version", [None, "", "85.0.621.9", "invalid"])
def test_webview2_runtime_probe_rejects_missing_or_unsupported_version(version: object) -> None:
    """Invalid or pre-EdgeChromium registry values cannot permit an MSHTML fallback."""
    values = (
        {
            (RecordingRegistry.HKEY_LOCAL_MACHINE, DESKTOP_WEBVIEW2_DOTNET_REGISTRY_KEY): (
                DESKTOP_WEBVIEW2_MINIMUM_DOTNET_RELEASE
            )
        }
        if version is None
        else {
            (RecordingRegistry.HKEY_LOCAL_MACHINE, DESKTOP_WEBVIEW2_DOTNET_REGISTRY_KEY): (
                DESKTOP_WEBVIEW2_MINIMUM_DOTNET_RELEASE
            ),
            (RecordingRegistry.HKEY_CURRENT_USER, DESKTOP_WEBVIEW2_USER_REGISTRY_KEY): version,
        }
    )

    with pytest.raises(DesktopWindowError, match=r"(?:missing|invalid) or too old"):
        _ = _require_webview2_runtime(lambda: RecordingRegistry(values))


@pytest.mark.parametrize("release", [None, True, DESKTOP_WEBVIEW2_MINIMUM_DOTNET_RELEASE - 1])
def test_webview2_runtime_probe_rejects_missing_or_unsupported_dotnet(release: object) -> None:
    """The pywebview WinForms prerequisite cannot fail into its MSHTML renderer path."""
    values = (
        {}
        if release is None
        else {(RecordingRegistry.HKEY_LOCAL_MACHINE, DESKTOP_WEBVIEW2_DOTNET_REGISTRY_KEY): release}
    )
    registry = RecordingRegistry(values)

    with pytest.raises(DesktopWindowError, match=r"\.NET Framework"):
        _ = _require_webview2_runtime(lambda: registry)

    if release is not None:
        assert registry.queries == [(RecordingRegistry.HKEY_LOCAL_MACHINE, DESKTOP_WEBVIEW2_DOTNET_REGISTRY_KEY)]
        assert DESKTOP_WEBVIEW2_DOTNET_REGISTRY_RELEASE_VALUE == "Release"


def test_error_dialog_uses_windows_unicode_message_box() -> None:
    """Fatal GUI-process errors remain visible when no console window exists."""
    user32 = RecordingUser32()
    stderr = StringIO()

    WindowsErrorDialog(
        stderr=stderr,
        platform=DESKTOP_SUPPORTED_PLATFORM,
        user32_loader=lambda: user32,
    ).show(DESKTOP_WINDOW_TITLE, "Startup failed")

    assert user32.calls == [(None, "Startup failed", DESKTOP_WINDOW_TITLE, DESKTOP_ERROR_DIALOG_FLAGS)]
    assert stderr.getvalue() == ""


def test_error_dialog_retains_stderr_fallback_off_supported_platform() -> None:
    """Source-checkout diagnostics remain visible when Windows native APIs are unavailable."""
    stderr = StringIO()

    WindowsErrorDialog(stderr=stderr, platform="linux").show(DESKTOP_WINDOW_TITLE, "Startup failed")

    assert stderr.getvalue() == f"{DESKTOP_WINDOW_TITLE}: Startup failed\n"


def test_error_dialog_never_raises_when_gui_process_has_no_stderr() -> None:
    """A failed native dialog remains contained in a windowed executable without standard streams."""

    def fail_user32() -> RecordingUser32:
        message = "user32 unavailable"
        raise OSError(message)

    WindowsErrorDialog(
        stderr=None,
        platform=DESKTOP_SUPPORTED_PLATFORM,
        user32_loader=fail_user32,
    ).show(DESKTOP_WINDOW_TITLE, "Startup failed")


def test_error_dialog_uses_stderr_when_message_box_reports_failure() -> None:
    """A zero MessageBoxW result triggers the remaining best-effort diagnostic channel."""
    stderr = StringIO()

    WindowsErrorDialog(
        stderr=stderr,
        platform=DESKTOP_SUPPORTED_PLATFORM,
        user32_loader=lambda: RecordingUser32(result=0),
    ).show(DESKTOP_WINDOW_TITLE, "Startup failed")

    assert stderr.getvalue() == f"{DESKTOP_WINDOW_TITLE}: Startup failed\n"
