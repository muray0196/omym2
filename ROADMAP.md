# OMYM2 Desktop Application Plan

## 1. Objective

Package OMYM2 as a lightweight desktop application while preserving the existing React/Vite user interface and FastAPI backend.

The desktop application will:

* Run only on desktop operating systems.
* Display the existing OMYM2 Web UI inside a native application window.
* Continue using the existing JSON API between the frontend and backend.
* Start and stop the local FastAPI server automatically.
* Require no browser window and no manual server startup.
* Preserve the existing CLI for advanced and diagnostic workflows.

Mobile, tablet, touch-first layouts, and mobile application distribution are explicitly out of scope.

---

## 2. Recommended Technology

Use:

* **pywebview** for the native desktop window.
* **Uvicorn** for the existing FastAPI server.
* **PyInstaller** for producing distributable desktop executables.
* The operating system’s native WebView implementation rather than Chromium or QtWebEngine.

Target architecture:

```text
OMYM2 Desktop Process
├── OMYM2 Python application
├── FastAPI / Uvicorn on a loopback address
└── pywebview native window
    └── Existing React / Vite application
```

The frontend will continue to communicate with FastAPI using same-origin HTTP requests.

No JavaScript-to-Python bridge will be introduced.

---

## 3. Design Principles

### 3.1 Preserve the Current UI

The existing frontend under `web/` remains authoritative.

The desktop implementation must not:

* Fork the frontend.
* Add a second desktop-specific React application.
* Replace React Router.
* Replace the generated OpenAPI client.
* Introduce desktop-only copies of API types.
* Reimplement backend behavior in JavaScript.

The same bundled `static_dist` files currently served by FastAPI will be displayed inside the desktop window.

### 3.2 Preserve the Backend Boundary

The frontend will continue to access OMYM2 exclusively through the JSON API.

The desktop shell must not expose:

* Direct SQLite access.
* Direct TOML access.
* Direct filesystem mutation APIs.
* A broad pywebview JavaScript bridge.
* Native operations that bypass backend validation.

All existing backend rules, capabilities, CSRF checks, idempotency behavior, and error responses remain authoritative.

### 3.3 Keep the Desktop Shell Minimal

The desktop shell is responsible only for:

1. Selecting an available loopback port.
2. Starting the OMYM2 FastAPI application.
3. Waiting until the server is ready.
4. Opening the native window.
5. Shutting down the server when the application exits.
6. Reporting startup failures to the user.

Business logic must remain outside the shell.

---

## 4. Proposed Repository Changes

```text
src/omym2/
├── platform/
│   ├── cli_entry_point.py
│   ├── web_composition.py
│   ├── desktop_entry_point.py      # New
│   └── desktop_runtime.py          # New
├── adapters/
│   └── desktop/
│       ├── __init__.py             # New
│       ├── window.py               # New
│       └── server.py               # New
└── adapters/web/
    └── static_dist/                # Existing bundled frontend
```

Suggested responsibilities:

### `desktop_entry_point.py`

* Public executable entry point.
* Configures logging.
* Builds the OMYM2 application.
* Starts the desktop runtime.
* Converts fatal startup failures into a user-visible error and non-zero exit code.

### `desktop_runtime.py`

* Coordinates server and window lifecycles.
* Does not contain FastAPI route or domain logic.
* Provides dependency injection points for tests.

### `adapters/desktop/server.py`

* Reserves an available loopback port.
* Starts Uvicorn in a background thread.
* Waits for startup readiness.
* Requests graceful shutdown.
* Joins the server thread before process termination.

### `adapters/desktop/window.py`

* Creates the pywebview window.
* Defines the initial title and dimensions.
* Handles the window-close lifecycle.
* Displays startup errors when the WebView cannot be created.

---

## 5. Application Entry Points

Keep the existing CLI entry point:

```toml
[project.scripts]
omym2 = "omym2.platform.cli_entry_point:main"
```

Add a dedicated desktop entry point:

```toml
[project.gui-scripts]
omym2-desktop = "omym2.platform.desktop_entry_point:main"
```

Using `gui-scripts` prevents a console window from appearing in normal packaged GUI builds on supported platforms.

The existing browser-based command may remain available for development and troubleshooting. It should not be the normal end-user desktop launch path.

---

## 6. Server Lifecycle

### 6.1 Port Selection

The desktop application should not rely on a permanently fixed port.

At startup:

1. Bind a temporary socket to `127.0.0.1` with port `0`.
2. Read the selected operating-system port.
3. Release the temporary socket immediately before Uvicorn starts.
4. Start Uvicorn on the selected port.
5. Retry with another port if the bind fails because of a race.

The application URL will be:

```text
http://127.0.0.1:<selected-port>/
```

The frontend uses relative API paths, so no frontend configuration change should be required.

### 6.2 Startup Readiness

The WebView must not open before FastAPI is ready.

Recommended readiness procedure:

1. Start Uvicorn in a background thread.
2. Poll a lightweight local endpoint such as `/api/bootstrap`.
3. Use a bounded startup attempt count.
4. Open the window only after the endpoint returns a valid response.
5. Abort cleanly if the server thread exits before readiness.

Do not use an arbitrary sleep as the primary readiness mechanism.

### 6.3 Shutdown

When the desktop window closes:

1. Set Uvicorn’s graceful-exit flag.
2. Allow FastAPI shutdown handlers to execute.
3. Wait for the Uvicorn thread to stop.
4. Release remaining application resources.
5. Exit the process.

A forced process exit should only be used as a final fallback if graceful shutdown cannot complete.

---

## 7. Desktop Window Configuration

Initial defaults:

```text
Title: OMYM2
Initial width: 1440 px
Initial height: 900 px
Minimum width: 1024 px
Minimum height: 700 px
Resizable: Yes
Maximized by default: No
Background: Match the existing dark canvas
```

The minimum width should align with OMYM2’s existing desktop-only frontend contract.

The application should initially use one window. Multiple windows are out of scope.

The shell should not add native navigation controls, browser chrome, an address bar, or a toolbar.

---

## 8. Security Requirements

### 8.1 Loopback Binding

The server must bind only to:

```text
127.0.0.1
```

It must not bind to:

```text
0.0.0.0
```

The desktop package is a local application, not a LAN-accessible server.

### 8.2 Existing HTTP Protections

Retain the existing:

* Host validation.
* CSRF token validation.
* Same-origin API boundary.
* Content Security Policy.
* Frame restrictions.
* Error redaction.
* Correlation IDs.
* Static asset restrictions.

The desktop shell must not weaken these protections solely because the UI is running inside a WebView.

### 8.3 No Broad Native Bridge

Do not register a general `js_api` object with pywebview.

Native folder pickers or other OS integrations should be proposed separately and require their own API and security design. The initial desktop packaging project should not change the existing path-entry behavior.

---

## 9. Dependency Changes

Add pywebview as a desktop dependency.

A preferable packaging structure is to keep desktop-only dependencies separate from the core package:

```toml
[project.optional-dependencies]
desktop = [
    "pywebview>=<validated-version>",
]
```

Development and packaging environments can install:

```bash
uv sync --extra desktop
```

PyInstaller can be added to the relevant development or packaging dependency group.

Exact versions should be pinned after confirming compatibility with OMYM2’s supported Python version and target operating systems.

---

## 10. Packaging Strategy

### 10.1 Initial Packaging Tool

Use PyInstaller for the first distributable desktop build.

Start with directory-based packaging:

```text
OMYM2/
├── OMYM2 executable
├── Python runtime files
├── native dependencies
└── packaged OMYM2 resources
```

Prefer `onedir` during initial implementation because it:

* Starts faster than extracting a one-file archive.
* Is easier to inspect and diagnose.
* Handles native WebView dependencies more predictably.
* Makes missing-data-file failures easier to identify.

A single-file executable may be evaluated later, but it should not be an initial requirement.

### 10.2 Static Frontend Assets

The packaged application must include the existing audited frontend output under:

```text
src/omym2/adapters/web/static_dist/
```

The desktop packaging process must reuse the same frontend export process as the Python wheel and sdist.

It must not run Vite at application startup.

Node.js must remain a build-time dependency only.

### 10.3 Configuration and Database Location

Do not place mutable data inside the PyInstaller application directory.

OMYM2 must continue to resolve its writable application root independently from the packaged executable resources.

The packaged application must preserve access to:

```text
.config/config.toml
.data/omym2.sqlite3
```

The specific default application-root location should be documented and tested for each supported operating system.

---

## 11. Platform Rollout

Implement and validate one platform at a time.

Recommended order:

1. **Windows**
2. **macOS**
3. **Linux**, only when a concrete Linux distribution target is defined

Each target requires a native build produced on that operating system. Cross-platform packaging should not be assumed.

### Windows

Validate:

* WebView2 availability.
* GUI launch without a terminal window.
* Long filesystem paths.
* Unicode paths.
* Application shutdown.
* Installer or archive distribution.
* Code-signing workflow when distribution begins.

### macOS

Validate:

* WKWebView rendering.
* `.app` bundle structure.
* Application data paths.
* Signing and notarization.
* Apple Silicon packaging.
* Intel packaging only if required.

### Linux

Do not claim generic Linux support without defining:

* Supported distribution.
* Required WebKitGTK package.
* Packaging format.
* Runtime dependency policy.

---

## 12. Testing Plan

### 12.1 Unit Tests

Add tests for:

* Loopback port selection.
* Server startup success.
* Server startup failure.
* Readiness timeout.
* Unexpected server-thread termination.
* Window creation failure.
* Graceful shutdown.
* Repeated shutdown requests.
* Exit-code mapping.
* URL construction.
* Dependency-injected window and server implementations.

Unit tests must not open a real native window.

### 12.2 Integration Tests

Add an integration test that:

1. Creates the existing FastAPI application.
2. Starts it through the desktop server adapter.
3. Waits for readiness.
4. Requests `/`.
5. Requests a deep frontend route.
6. Requests a hashed asset.
7. Requests `/api/bootstrap`.
8. Stops the server gracefully.

This verifies that the desktop server path serves the same application as the current browser path.

### 12.3 Packaged Smoke Tests

For each packaged build:

1. Launch the packaged desktop application.
2. Confirm that one OMYM2 window opens.
3. Confirm that no external browser opens.
4. Confirm that the Overview screen becomes interactive.
5. Navigate to every primary route.
6. Load settings.
7. Create a non-destructive test plan.
8. Close the window.
9. Confirm that the OMYM2 process and loopback listener terminate.
10. Relaunch and confirm persisted state remains available.

### 12.4 Regression Tests

The existing frontend tests must remain unchanged where possible:

* Unit tests.
* Accessibility tests.
* Playwright end-to-end tests.
* API drift checks.
* Package tests.
* Performance tests.

The browser-hosted production application remains the canonical test surface for frontend behavior. Desktop smoke tests verify the shell and lifecycle rather than duplicating every UI test.

---

## 13. Logging and Diagnostics

The packaged application should write logs to a writable OMYM2 application-data directory.

Logs should include:

* Application version.
* Operating system.
* Selected loopback port.
* Server startup status.
* WebView backend.
* Fatal startup failures.
* Graceful or forced shutdown result.

Logs must not contain:

* CSRF tokens.
* Secrets.
* Full file contents.
* Raw database records.
* Unredacted unexpected API responses.

A failed startup should present a concise native error dialog and reference the log location.

---

## 14. Performance Requirements

The desktop shell should add minimal overhead to the current Web UI.

Acceptance targets:

* No Chromium runtime bundled by OMYM2.
* No Node.js runtime in the production package.
* No duplicate copy of the frontend.
* No frontend development server in production.
* No additional application-level polling beyond existing operation behavior.
* No material regression against the existing interactive-shell performance budget.
* Window close should terminate the local server promptly.
* Repeated launches must not leave orphaned server processes.

Package-size measurements should be recorded separately for each platform.

---

## 15. Implementation Phases

### Phase 1 — Desktop Runtime Skeleton

Deliverables:

* Add the desktop dependency group.
* Add `desktop_entry_point.py`.
* Add testable server and window abstractions.
* Start the existing FastAPI application in a background thread.
* Open the existing UI in pywebview.
* Implement graceful shutdown.
* Add unit tests.

Exit criteria:

* Running `omym2-desktop` opens OMYM2 in a native window.
* Closing the window stops the server.
* No external browser opens.

### Phase 2 — Runtime Hardening

Deliverables:

* Dynamic loopback port selection.
* Readiness probing.
* Startup failure handling.
* Structured desktop logging.
* Duplicate shutdown protection.
* Integration tests.
* Minimum window dimensions.

Exit criteria:

* Port collisions do not prevent normal startup.
* Server failures produce a clear error.
* No orphaned process or listener remains after exit.

### Phase 3 — Packaged Development Build

Deliverables:

* PyInstaller specification.
* Inclusion rules for `static_dist`.
* Packaging scripts.
* Packaged smoke-test script.
* Build documentation.
* First platform artifact.

Exit criteria:

* A clean machine can launch the package without Python or Node.js installed.
* The full existing UI and API function from the packaged application.
* Mutable OMYM2 data survives application upgrades.

### Phase 4 — Distribution Readiness

Deliverables:

* Application icon and metadata.
* Version embedding.
* Platform signing configuration.
* Installer or archive format.
* Uninstall behavior.
* Release checklist.
* CI packaging workflow.

Exit criteria:

* The application can be installed, launched, upgraded, and removed without damaging the user’s OMYM2 configuration or database.

---

## 16. Explicit Non-Goals

The initial project will not include:

* Mobile applications.
* Tablet support.
* Responsive mobile navigation.
* Electron.
* Bundled Chromium.
* Tauri or Rust components.
* A rewritten native UI.
* Native playback functionality.
* Native metadata editing.
* A system tray process.
* Automatic updates.
* Multiple windows.
* Native folder pickers.
* OS file associations.
* Background startup at login.
* JavaScript access to arbitrary Python objects.
* Removal of the existing CLI.

These features can be evaluated independently after the basic desktop package is stable.

---

## 17. Acceptance Criteria

The implementation is complete when all of the following are true:

1. OMYM2 launches from a desktop executable or application bundle.
2. The existing React UI appears unchanged inside a native window.
3. The application supports the existing desktop viewport contract.
4. No mobile behavior is introduced or required.
5. No external browser opens during normal startup.
6. FastAPI starts automatically on a loopback-only address.
7. The frontend continues using the existing JSON API.
8. Existing CSRF, host, CSP, and error-handling behavior remains active.
9. No pywebview JavaScript bridge bypasses the API boundary.
10. The loopback port is selected dynamically.
11. Closing the final window shuts down Uvicorn and the Python process.
12. The packaged application includes the audited Vite output.
13. Python and Node.js do not need to be separately installed by the user.
14. Existing frontend and backend tests continue to pass.
15. Platform-specific packaged smoke tests pass.
16. User configuration and SQLite state remain outside replaceable application files.
17. Package size and startup measurements are recorded for each supported platform.

---

## 18. Final Technical Decision

OMYM2 should use a **thin pywebview desktop shell around the existing loopback FastAPI application**.

This approach preserves the current UI, backend architecture, API contract, security model, and frontend build pipeline. It also avoids introducing Chromium, Node.js at runtime, Rust, a second process architecture, or a separate desktop frontend.
