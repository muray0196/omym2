"""
Summary: Centralizes standalone repository-script tunables.
Why: Keeps lifecycle-hook timeouts and output bounds out of control flow.
"""
# ruff: noqa: INP001 -- Standalone repository-script configuration is not an importable package layer.

CODEX_STOP_HOOK_GIT_TIMEOUT_SECONDS = 30  # timeout for one Git inspection command, seconds, >= 1
CODEX_STOP_HOOK_GATE_TIMEOUT_SECONDS = 120  # timeout for scripts/checks.sh completion, seconds, >= 1
CODEX_STOP_HOOK_DIAGNOSTIC_MAX_CHARACTERS = 8_000  # maximum returned gate diagnostics, characters, >= 1
CODEX_STOP_HOOK_FINGERPRINT_CHUNK_BYTES = 1_048_576  # untracked-file hashing chunk, bytes, >= 1

DESKTOP_APPLICATION_NAME = "OMYM2"  # packaged desktop application name, text, non-empty
DESKTOP_WINDOWS_PLATFORM_NAME = "win32"  # required sys.platform for native builds, text, exact
DESKTOP_WINDOWS_MACHINE_NAMES = ("amd64", "x86_64")  # accepted platform.machine values, lowercase names
DESKTOP_WINDOWS_POINTER_BYTES = 8  # required interpreter pointer width, bytes, exactly 8
DESKTOP_WINDOWS_EXECUTABLE_NAME = "OMYM2.exe"  # packaged GUI executable name, Windows file name
DESKTOP_WINDOWS_ARTIFACT_TAG = "windows-x86_64"  # release artifact platform tag, text, exact
DESKTOP_WINDOWS_DEFAULT_OUTPUT_RELATIVE_PATH = "build/desktop"  # default artifact directory, repo-relative path
DESKTOP_WINDOWS_ICON_RELATIVE_PATH = "assets/desktop/omym2.ico"  # committed icon, repo-relative path
DESKTOP_WINDOWS_VERSION_RELATIVE_PATH = "assets/desktop/windows_version_info.txt"  # PE metadata, repo-relative path
DESKTOP_WINDOWS_SPEC_RELATIVE_PATH = "scripts/desktop/omym2_windows.spec"  # PyInstaller spec, repo-relative path
DESKTOP_WINDOWS_POWERSHELL_EXECUTABLE_NAME = "powershell.exe"  # Windows metadata and native-window probe program
DESKTOP_WINDOWS_POWERSHELL_PROBE_FILENAME = "omym2-probe.ps1"  # temporary native-probe script filename
DESKTOP_PYINSTALLER_REQUIREMENT = "pyinstaller==6.21.0"  # isolated build tool requirement, PEP 508 string
DESKTOP_PYINSTALLER_CONTENTS_DIRECTORY_NAME = "_internal"  # onedir support-file directory, one path component
DESKTOP_PYINSTALLER_PROVENANCE_FILE_NAME = "omym2-freeze-provenance.json"  # bundled freeze manifest name
DESKTOP_PYINSTALLER_RUNTIME_HOOK_POLICY = "pywebview-x64-resource-alias"  # exact frozen runtime hook policy
DESKTOP_RUNTIME_INVENTORY_FILE_NAME = "omym2-third-party-inventory.json"  # bundled runtime license inventory name
DESKTOP_PYTHON_RUNTIME_LICENSE_FILE_NAME = "PYTHON-LICENSE.txt"  # bundled CPython runtime license file name
DESKTOP_PYINSTALLER_SOURCE_DATE_EPOCH = "315532800"  # reproducible build epoch, Unix seconds, 1980-01-01 UTC
DESKTOP_PYINSTALLER_EXCLUDED_MODULES = (  # prohibited optional renderer modules, import names
    "cefpython3",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "qtpy",
    "webview.platforms.android",
    "webview.platforms.cef",
    "webview.platforms.cocoa",
    "webview.platforms.gtk",
    "webview.platforms.mshtml",
    "webview.platforms.qt",
)
DESKTOP_PYINSTALLER_HIDDEN_IMPORTS = (  # required dynamic Windows desktop modules, import names
    "msvcrt",
    "webview",
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
    "winreg",
)
DESKTOP_PYINSTALLER_REQUIRED_BUILTIN_MODULES = (  # Windows modules embedded in the collected CPython runtime
    "msvcrt",
    "winreg",
)
DESKTOP_PYINSTALLER_REQUIRED_WEBVIEW_MODULES = (  # required modules observed in the frozen PYZ manifest
    "webview",
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
)
DESKTOP_PYWEBVIEW_X64_RUNTIME_DIRECTORY_NAME = "win-x64"  # retained pywebview native loader directory name
DESKTOP_PYWEBVIEW_UNUSED_RUNTIME_DIRECTORY_NAMES = (  # pywebview probes aliased to retained x64 loader
    "win-arm64",
    "win-x86",
)
DESKTOP_WINDOWS_ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)  # committed ICO images, pixels, ascending
DESKTOP_ARCHIVE_TIMESTAMP = (1980, 1, 1, 0, 0, 0)  # deterministic ZIP member timestamp, local date-time tuple
DESKTOP_ARCHIVE_COMPRESSION_LEVEL = 9  # deterministic ZIP deflate level, integer, 0..9
DESKTOP_ARCHIVE_IO_CHUNK_BYTES = 1_048_576  # archive hashing and copy chunk, bytes, >= 1
DESKTOP_WINDOWS_METADATA_TIMEOUT_SECONDS = 30  # PE metadata inspection timeout, seconds, >= 1
DESKTOP_WINDOWS_SMOKE_STARTUP_TIMEOUT_SECONDS = 60  # native window startup timeout, seconds, >= 1
DESKTOP_WINDOWS_SMOKE_SHUTDOWN_TIMEOUT_SECONDS = 30  # graceful process shutdown timeout, seconds, >= 1
DESKTOP_WINDOWS_SMOKE_POLL_INTERVAL_SECONDS = 0.1  # log and process polling interval, seconds, > 0
DESKTOP_WINDOWS_SMOKE_DIAGNOSTIC_TAIL_BYTES = 8_000  # maximum printed bytes per native failure stream, >= 1
DESKTOP_WINDOWS_SMOKE_UI_AUTOMATION_TIMEOUT_SECONDS = 300  # complete native UI evidence timeout, seconds, >= startup
DESKTOP_WINDOWS_SMOKE_AUDIO_FILE_BYTES = 4_096  # synthetic tagged FLAC input size, bytes, >= metadata size
DESKTOP_WINDOWS_SMOKE_UNICODE_DIRECTORY_NAME = "音楽-パッケージ"  # Unicode segment used by native path smoke
DESKTOP_WINDOWS_SMOKE_LONG_COMPONENT_CHARACTERS = 110  # long-path smoke segment length, characters, 32..240
DESKTOP_WINDOWS_SMOKE_LONG_COMPONENT_COUNT = 2  # nested long-path smoke components, components, >= 2
DESKTOP_WINDOWS_SMOKE_LAUNCH_CWD_DIRECTORY_NAME = "launch-cwd"  # isolated short child cwd, one path component
DESKTOP_WINDOWS_LEGACY_MAX_PATH_CHARACTERS = 260  # Win32 MAX_PATH boundary including terminator, characters
DESKTOP_WINDOWS_SMOKE_MAXIMUM_LAUNCH_CWD_CHARACTERS = 258  # CreateProcessW child cwd limit, characters, 1..258
DESKTOP_WINDOWS_SMOKE_MINIMUM_PATH_CHARACTERS = 280  # minimum observed smoke path length, characters, > 260
DESKTOP_WINDOWS_SMOKE_MAXIMUM_PATH_CHARACTERS = 480  # bounded smoke path ceiling, characters, >= minimum
DESKTOP_WINDOWS_WEBVIEW_INITIALIZED_LOG_MARKER = (  # exact successful EdgeChromium selection log text
    "Desktop WebView initialized backend=edgechromium"
)
DESKTOP_WINDOWS_WEBVIEW_LOADED_LOG_MARKER = "Desktop WebView content loaded"  # post-navigation loaded log text
DESKTOP_WINDOWS_FAILURE_LOG_MARKER = "Desktop process failed"  # fatal desktop startup log text, exact substring
DESKTOP_WINDOWS_LOG_RELATIVE_PATH = "OMYM2/.data/logs/omym2-desktop.log"  # LOCALAPPDATA-relative desktop log
DESKTOP_WINDOWS_CONFIG_RELATIVE_PATH = "OMYM2/.config/config.toml"  # LOCALAPPDATA-relative mutable Config file
DESKTOP_WINDOWS_DATABASE_RELATIVE_PATH = "OMYM2/.data/omym2.sqlite3"  # LOCALAPPDATA-relative mutable SQLite file
DESKTOP_WINDOWS_SMOKE_CONFIG_MARKER = (  # valid minimal Config used as a persistence marker, TOML text
    "# OMYM2 packaged-smoke persistence marker\nversion = 1\n"
)
DESKTOP_WINDOWS_SMOKE_PRIMARY_ROUTES = (  # production SPA routes exercised through the packaged listener
    "/",
    "/plans",
    "/plans/new/add",
    "/plans/new/organize",
    "/plans/new/refresh",
    "/library",
    "/health",
    "/history",
    "/settings",
)
DESKTOP_WINDOWS_SMOKE_UI_ROOT_AUTOMATION_ID = "RootWebArea"  # Edge document UIA identifier, text, exact
DESKTOP_WINDOWS_SMOKE_UI_SETTINGS_AUTOMATION_ID = (  # loaded Settings field UIA identifier, text, exact
    "settings-paths-library"
)
DESKTOP_WINDOWS_SMOKE_UI_ADD_SOURCE_AUTOMATION_ID = "add-source"  # Add source field UIA identifier, text, exact
DESKTOP_WINDOWS_SMOKE_UI_PRIMARY_NAVIGATION = (  # route, visible link, and route heading, ordered tuples
    ("/", "Overview", "Operations overview"),
    ("/plans", "Plans", "Plans"),
    ("/library", "Library", "Library"),
    ("/health", "Health", "Health"),
    ("/history", "History", "History"),
    ("/settings", "Settings", "Settings"),
)
DESKTOP_WINDOWS_SMOKE_UI_OVERVIEW_ACTION = ("Open Health", "Health")  # action and expected heading, text
DESKTOP_WINDOWS_SMOKE_UI_ADD_ACTIONS = (  # Command Center, route, submit, detail, and ready-control labels
    "Command Center",
    "Add music",
    "Scan and create Plan",
    "Plan detail",
    "Cancel Plan",
)
DESKTOP_WINDOWS_EXTERNAL_BROWSER_PROCESS_NAMES = (  # forbidden externally launched browser process names
    "brave",
    "chrome",
    "firefox",
    "msedge",
    "opera",
)
DESKTOP_WINDOWS_FORBIDDEN_ARCHIVE_BASENAMES = (  # forbidden bundled runtime file names, lowercase names
    "chrome.exe",
    "chrome_elf.dll",
    "chromium.exe",
    "electron.exe",
    "libcef.dll",
    "node.exe",
    "npm.cmd",
    "npx.cmd",
    "resources.pak",
    "snapshot_blob.bin",
    "v8_context_snapshot.bin",
)
DESKTOP_WINDOWS_FORBIDDEN_ARCHIVE_FRAGMENTS = (  # forbidden bundled framework path fragments, lowercase text
    "cefpython",
    "node_modules",
    "pyqt5",
    "pyqt6",
    "pyside2",
    "pyside6",
    "qt5",
    "qt6",
    "qtwebengine",
)
DESKTOP_WINDOWS_FORBIDDEN_WEBVIEW_RESOURCES = (  # prohibited architecture or renderer resource fragments, lowercase text
    "/runtimes/win-arm64/",
    "/runtimes/win-x86/",
    "/webbrowserinterop.x64.dll",
    "/webbrowserinterop.x86.dll",
    ".jar",
)
DESKTOP_WINDOWS_REQUIRED_WEBVIEW_DLL_RELATIVE_PATHS = (  # exact pywebview EdgeChromium DLL payload, POSIX paths
    "webview/lib/Microsoft.Web.WebView2.Core.dll",
    "webview/lib/Microsoft.Web.WebView2.WinForms.dll",
    "webview/lib/runtimes/win-x64/native/WebView2Loader.dll",
)
DESKTOP_WINDOWS_SOURCE_TREE_MEMBER_NAMES = (".git", "src", "tests")  # forbidden source-tree archive components
