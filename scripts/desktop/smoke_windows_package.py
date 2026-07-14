"""
Summary: Smokes the real frozen Windows GUI twice across replaceable application directories.
Why: Proves native WebView, HTTP, shutdown, path, browser, and persisted-state behavior.
"""
# ruff: noqa: T201 -- Standalone native smoke tooling is directly executable and reports results.

from __future__ import annotations

import argparse
import contextlib
import hashlib
import http.client
import json
import os
import platform
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast
from urllib.parse import urlsplit
from uuid import uuid4

from mutagen.flac import FLAC

if __package__:
    from scripts import config
    from scripts.desktop.audit_windows_package import (
        WindowsPackageAuditError,
        audit_windows_package,
        extract_windows_archive,
    )
    from scripts.desktop.build_windows import WindowsPackageBuildError, require_windows_x64
    from scripts.web.smoke_installed_web import PackageSmokeError, smoke_web_package
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts import config  # Direct script execution needs the repository script namespace.
    from scripts.desktop.audit_windows_package import (  # See the direct-execution path above.
        WindowsPackageAuditError,
        audit_windows_package,
        extract_windows_archive,
    )
    from scripts.desktop.build_windows import (  # See the direct-execution path above.
        WindowsPackageBuildError,
        require_windows_x64,
    )
    from scripts.web.smoke_installed_web import (  # Reuses the authoritative HTTP package smoke.
        PackageSmokeError,
        smoke_web_package,
    )

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Mapping, Sequence
    from typing import BinaryIO

    from scripts.desktop.audit_windows_package import WindowsPackageAudit

_READY_URL_PATTERN = re.compile(rb"Desktop server ready url=(http://127\.0\.0\.1:\d+/)")
_HTTP_ACCEPTED_STATUS = 202
_HTTP_BAD_REQUEST_STATUS = 400
_HTTP_FORBIDDEN_STATUS = 403
_HTTP_NOT_FOUND_STATUS = 404
_SUCCESS_STATUS_CODE = 200
_API_BOOTSTRAP_ROUTE = "/api/bootstrap"
_API_ADD_ROUTE = "/api/plans/add"
_API_CHECK_ROUTE = "/api/check/run"
_API_ORGANIZE_ROUTE = "/api/plans/organize"
_API_SETTINGS_ROUTE = "/api/settings"
_CSRF_HEADER_NAME = "X-OMYM2-CSRF-Token"
_IDEMPOTENCY_HEADER_NAME = "Idempotency-Key"
_HOSTILE_HOST_HEADER = "attacker.invalid"
_ACTIVE_OPERATION_STATUSES = frozenset({"queued", "running"})
_TERMINAL_OPERATION_STATUSES = frozenset({"succeeded", "failed", "interrupted"})
_WINDOWS_PRODUCT_TYPES = {1: "workstation", 2: "domain_controller", 3: "server"}
_WINDOWS_11_MINIMUM_BUILD = 22_000
_POWERSHELL_UTF8_PREAMBLE = "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)"
_BITS_PER_BYTE = 8
_FLAC_BYTE_ORDER = "big"
_FLAC_CHANNEL_COUNT = 1
_FLAC_CHANNEL_COUNT_BITS = 3
_FLAC_FRAME_SIZE_FIELDS_BYTES = 6
_FLAC_LAST_METADATA_BLOCK_FLAG = 0x80
_FLAC_MD5_BYTES = 16
_FLAC_SAMPLE_RATE_BITS = 20
_FLAC_SAMPLE_RATE_HZ = 8_000
_FLAC_SAMPLE_SIZE_BITS = 8
_FLAC_SAMPLE_SIZE_FIELD_BITS = 5
_FLAC_STREAMINFO_BLOCK_SIZE_SAMPLES = 4_096
_FLAC_STREAMINFO_LENGTH_BYTES = 34
_FLAC_STREAM_MARKER = b"fLaC"
_FLAC_TOTAL_SAMPLES_BITS = 36
_INDEX_DISPLAY_OFFSET = 1
_WINDOWS_CLOSE_MESSAGE = 0x0010
_WINDOW_PROBE_TYPE = r"""
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public static class OMYM2WindowProbe {
    private delegate bool EnumWindowsProc(IntPtr handle, IntPtr parameter);
    [DllImport("user32.dll")] private static extern bool EnumWindows(EnumWindowsProc callback, IntPtr parameter);
    [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr handle);
    [DllImport("user32.dll")] private static extern int GetWindowTextLength(IntPtr handle);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetWindowText(IntPtr handle, StringBuilder text, int count);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr handle, out uint processId);

    public sealed class WindowRecord {
        public long handle;
        public string title = "";
    }

    public static WindowRecord[] VisibleWindows(int expectedProcessId) {
        var windows = new List<WindowRecord>();
        EnumWindows(delegate(IntPtr handle, IntPtr parameter) {
            uint processId;
            GetWindowThreadProcessId(handle, out processId);
            if (processId == expectedProcessId && IsWindowVisible(handle)) {
                int length = GetWindowTextLength(handle);
                var title = new StringBuilder(length + 1);
                GetWindowText(handle, title, title.Capacity);
                windows.Add(new WindowRecord { handle = handle.ToInt64(), title = title.ToString() });
            }
            return true;
        }, IntPtr.Zero);
        return windows.ToArray();
    }
}
"""
_WAIT_FOR_WINDOW_SCRIPT = rf"""
param([int]$ProcessId, [string]$ExpectedTitle, [int]$TimeoutMilliseconds)
$ErrorActionPreference = 'Stop'
$null = Add-Type -TypeDefinition @'
{_WINDOW_PROBE_TYPE}
'@
$deadline = [DateTime]::UtcNow.AddMilliseconds($TimeoutMilliseconds)
do {{
  $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
  if ($null -eq $process) {{ throw 'The packaged process exited before its native window appeared.' }}
  $windows = @([OMYM2WindowProbe]::VisibleWindows($ProcessId))
  if ($windows.Count -gt 1) {{ throw "The packaged process created $($windows.Count) visible windows." }}
  if ($windows.Count -eq 1 -and $windows[0].title -eq $ExpectedTitle) {{
    @{{ windows = @($windows) }} | ConvertTo-Json -Compress -Depth 4
    exit 0
  }}
  Start-Sleep -Milliseconds 100
}} while ([DateTime]::UtcNow -lt $deadline)
throw 'Timed out waiting for the one visible OMYM2 window.'
"""
_CLOSE_WINDOW_SCRIPT = rf"""
param([long]$Handle)
$ErrorActionPreference = 'Stop'
$null = Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class OMYM2WindowCloser {{
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr handle, uint message, IntPtr wParam, IntPtr lParam);
}}
'@
$posted = [OMYM2WindowCloser]::PostMessage([IntPtr]$Handle, {_WINDOWS_CLOSE_MESSAGE}, [IntPtr]::Zero, [IntPtr]::Zero)
@{{ posted = $posted }} | ConvertTo-Json -Compress
"""
_BROWSER_SNAPSHOT_SCRIPT = rf"""
param([string]$ProcessNames)
$ErrorActionPreference = 'Stop'
$null = Add-Type -TypeDefinition @'
{_WINDOW_PROBE_TYPE}
'@
$names = @($ProcessNames.Split(',') | ForEach-Object {{ $_.Trim().ToLowerInvariant() }})
$processes = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {{ $names -contains $_.ProcessName.ToLowerInvariant() }})
$windows = @()
foreach ($process in $processes) {{
  foreach ($window in [OMYM2WindowProbe]::VisibleWindows($process.Id)) {{
    $windows += [ordered]@{{ process_id = $process.Id; process_name = $process.ProcessName; handle = $window.handle; title = $window.title }}
  }}
}}
[ordered]@{{
  processes = @($processes | ForEach-Object {{ [ordered]@{{ process_id = $_.Id; process_name = $_.ProcessName }} }})
  windows = $windows
}} | ConvertTo-Json -Compress -Depth 5
"""
_WINDOWS_HOST_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$os = Get-CimInstance -ClassName Win32_OperatingSystem
$version = Get-ItemProperty -LiteralPath 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
[ordered]@{
  architecture = [string]$os.OSArchitecture
  build_number = [string]$os.BuildNumber
  caption = [string]$os.Caption
  display_version = [string]$version.DisplayVersion
  edition_id = [string]$version.EditionID
  installation_type = [string]$version.InstallationType
  product_type = [int]$os.ProductType
  version = [string]$os.Version
} | ConvertTo-Json -Compress
"""
_NATIVE_UI_AUTOMATION_SCRIPT = r"""
param(
  [long]$Handle,
  [string]$SourcePath,
  [int]$TimeoutMilliseconds,
  [int]$PollMilliseconds,
  [int]$AriaRolePropertyId,
  [string]$RootAutomationId,
  [string]$SettingsAutomationId,
  [string]$AddSourceAutomationId,
  [string]$PrimaryNavigationJson,
  [string]$OverviewActionJson,
  [string]$AddActionsJson
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$ariaRoleProperty = [System.Windows.Automation.AutomationProperty]::LookupById($AriaRolePropertyId)
if ($null -eq $ariaRoleProperty) { throw "UI Automation property $AriaRolePropertyId is unavailable." }
$window = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$Handle)
if ($null -eq $window) { throw 'The packaged window has no UI Automation root.' }
$primaryNavigation = @($PrimaryNavigationJson | ConvertFrom-Json)
$overviewAction = @($OverviewActionJson | ConvertFrom-Json)
$addActions = @($AddActionsJson | ConvertFrom-Json)

function Get-VisibleMatches {
  param(
    [System.Windows.Automation.AutomationElement]$Root,
    [System.Windows.Automation.Condition]$Condition
  )
  $collection = $Root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $Condition)
  for ($index = 0; $index -lt $collection.Count; $index++) {
    $element = $collection.Item($index)
    if (-not $element.Current.IsOffscreen) { $element }
  }
}

function Wait-ForAutomationId {
  param(
    [System.Windows.Automation.AutomationElement]$Root,
    [string]$AutomationId
  )
  $condition = [System.Windows.Automation.PropertyCondition]::new(
    [System.Windows.Automation.AutomationElement]::AutomationIdProperty,
    $AutomationId
  )
  $deadline = [DateTime]::UtcNow.AddMilliseconds($TimeoutMilliseconds)
  do {
    try {
      $matches = @(Get-VisibleMatches -Root $Root -Condition $condition)
      if ($matches.Count -eq 1) { return $matches[0] }
      if ($matches.Count -gt 1) { throw "UI Automation id '$AutomationId' matched multiple visible elements." }
    } catch [System.Windows.Automation.ElementNotAvailableException] {
    }
    Start-Sleep -Milliseconds $PollMilliseconds
  } while ([DateTime]::UtcNow -lt $deadline)
  throw "Timed out waiting for visible UI Automation id '$AutomationId'."
}

function Wait-ForHeading {
  param(
    [System.Windows.Automation.AutomationElement]$Root,
    [string]$Name
  )
  $condition = [System.Windows.Automation.AndCondition]::new(
    [System.Windows.Automation.PropertyCondition]::new(
      [System.Windows.Automation.AutomationElement]::NameProperty,
      $Name
    ),
    [System.Windows.Automation.PropertyCondition]::new(
      [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
      [System.Windows.Automation.ControlType]::Text
    )
  )
  $deadline = [DateTime]::UtcNow.AddMilliseconds($TimeoutMilliseconds)
  do {
    try {
      $matches = @(
        Get-VisibleMatches -Root $Root -Condition $condition | Where-Object {
          $_.GetCurrentPropertyValue($ariaRoleProperty, $true) -eq 'heading'
        }
      )
      if ($matches.Count -eq 1) { return $matches[0] }
      if ($matches.Count -gt 1) { throw "Heading '$Name' matched multiple visible elements." }
    } catch [System.Windows.Automation.ElementNotAvailableException] {
    }
    Start-Sleep -Milliseconds $PollMilliseconds
  } while ([DateTime]::UtcNow -lt $deadline)
  throw "Timed out waiting for heading '$Name'."
}

function Wait-ForInvokableName {
  param(
    [System.Windows.Automation.AutomationElement]$Root,
    [string]$Name
  )
  $condition = [System.Windows.Automation.PropertyCondition]::new(
    [System.Windows.Automation.AutomationElement]::NameProperty,
    $Name
  )
  $deadline = [DateTime]::UtcNow.AddMilliseconds($TimeoutMilliseconds)
  do {
    try {
      $matches = @()
      foreach ($element in @(Get-VisibleMatches -Root $Root -Condition $condition)) {
        $patternObject = $null
        if (
          $element.Current.IsEnabled -and
          $element.TryGetCurrentPattern(
            [System.Windows.Automation.InvokePattern]::Pattern,
            [ref]$patternObject
          )
        ) {
          $matches += [pscustomobject]@{ element = $element; pattern = $patternObject }
        }
      }
      if ($matches.Count -eq 1) { return $matches[0] }
      if ($matches.Count -gt 1) { throw "Action '$Name' matched multiple visible invokable elements." }
    } catch [System.Windows.Automation.ElementNotAvailableException] {
    }
    Start-Sleep -Milliseconds $PollMilliseconds
  } while ([DateTime]::UtcNow -lt $deadline)
  throw "Timed out waiting for enabled invokable action '$Name'."
}

function Invoke-NamedAction {
  param(
    [System.Windows.Automation.AutomationElement]$Root,
    [string]$Name
  )
  $match = Wait-ForInvokableName -Root $Root -Name $Name
  ([System.Windows.Automation.InvokePattern]$match.pattern).Invoke()
}

function Set-And-VerifyValue {
  param(
    [System.Windows.Automation.AutomationElement]$Root,
    [string]$AutomationId,
    [string]$Value
  )
  $element = Wait-ForAutomationId -Root $Root -AutomationId $AutomationId
  $patternObject = $null
  if (-not $element.TryGetCurrentPattern(
    [System.Windows.Automation.ValuePattern]::Pattern,
    [ref]$patternObject
  )) {
    throw "UI Automation id '$AutomationId' does not expose ValuePattern."
  }
  $pattern = [System.Windows.Automation.ValuePattern]$patternObject
  if ($pattern.Current.IsReadOnly) { throw "UI Automation id '$AutomationId' is read-only." }
  $pattern.SetValue($Value)
  $deadline = [DateTime]::UtcNow.AddMilliseconds($TimeoutMilliseconds)
  do {
    $current = Wait-ForAutomationId -Root $Root -AutomationId $AutomationId
    $currentPatternObject = $null
    if ($current.TryGetCurrentPattern(
      [System.Windows.Automation.ValuePattern]::Pattern,
      [ref]$currentPatternObject
    )) {
      $currentPattern = [System.Windows.Automation.ValuePattern]$currentPatternObject
      if ($currentPattern.Current.Value -ceq $Value) { return }
    }
    Start-Sleep -Milliseconds $PollMilliseconds
  } while ([DateTime]::UtcNow -lt $deadline)
  throw "UI Automation id '$AutomationId' did not retain its requested value."
}

$documentRoot = Wait-ForAutomationId -Root $window -AutomationId $RootAutomationId
$null = Wait-ForHeading -Root $documentRoot -Name ([string]$primaryNavigation[0][2])
Invoke-NamedAction -Root $documentRoot -Name ([string]$overviewAction[0])
$null = Wait-ForHeading -Root $documentRoot -Name ([string]$overviewAction[1])

$navigatedRoutes = @()
foreach ($route in $primaryNavigation) {
  Invoke-NamedAction -Root $documentRoot -Name ([string]$route[1])
  $null = Wait-ForHeading -Root $documentRoot -Name ([string]$route[2])
  $navigatedRoutes += [string]$route[0]
}
$null = Wait-ForAutomationId -Root $documentRoot -AutomationId $SettingsAutomationId

Invoke-NamedAction -Root $documentRoot -Name ([string]$addActions[0])
$null = Wait-ForHeading -Root $documentRoot -Name ([string]$addActions[0])
Invoke-NamedAction -Root $documentRoot -Name ([string]$addActions[1])
$null = Wait-ForHeading -Root $documentRoot -Name ([string]$addActions[1])
Set-And-VerifyValue -Root $documentRoot -AutomationId $AddSourceAutomationId -Value $SourcePath
Invoke-NamedAction -Root $documentRoot -Name ([string]$addActions[2])
$null = Wait-ForHeading -Root $documentRoot -Name ([string]$addActions[3])
$null = Wait-ForInvokableName -Root $documentRoot -Name ([string]$addActions[4])

[ordered]@{
  add_source_value_verified = $true
  automation_framework = 'Microsoft UI Automation'
  deep_routes = @('/plans/new/add', '/plans/:planId')
  overview_action = [string]$overviewAction[0]
  overview_interactive = $true
  plan_detail_loaded = $true
  plan_submit_action = [string]$addActions[2]
  primary_navigation_routes = $navigatedRoutes
  root_automation_id = $RootAutomationId
  settings_editor_automation_id = $SettingsAutomationId
  settings_loaded = $true
} | ConvertTo-Json -Compress -Depth 5
"""


class WindowsPackageSmokeError(RuntimeError):
    """Raised when a real packaged Windows GUI violates native smoke behavior."""


@dataclass(frozen=True, slots=True)
class BrowserSnapshot:
    """External browser processes and visible windows observed at one instant."""

    process_ids: tuple[int, ...]
    windows: tuple[tuple[int, int, str], ...]


@dataclass(frozen=True, slots=True)
class NativeLaunchEvidence:
    """Measured behavior from one complete packaged GUI lifecycle."""

    external_browser_process_appeared: bool
    external_browser_window_appeared: bool
    listener_terminated: bool
    process_exit_code: int
    routes: tuple[str, ...]
    security: Mapping[str, object]
    shutdown_milliseconds: int
    startup_milliseconds: int
    visible_window_count: int
    webview_backend: str


@dataclass(frozen=True, slots=True)
class NativeLaunchContext:
    """Paths and identity needed to run and diagnose one packaged GUI lifecycle."""

    diagnostic_directory: Path
    executable: Path
    launch_name: str
    launch_working_directory: Path
    local_app_data: Path
    log_file: Path

    @property
    def stdout_file(self) -> Path:
        """Return the retained standard-output path for this launch."""
        return self.diagnostic_directory / f"{self.launch_name}-stdout.log"

    @property
    def stderr_file(self) -> Path:
        """Return the retained standard-error path for this launch."""
        return self.diagnostic_directory / f"{self.launch_name}-stderr.log"

    @property
    def retained_desktop_log(self) -> Path:
        """Return the retained application-log path for this launch."""
        return self.diagnostic_directory / f"{self.launch_name}-desktop.log"

    @property
    def failure_summary_file(self) -> Path:
        """Return the human-readable failure-summary path for this launch."""
        return self.diagnostic_directory / f"{self.launch_name}-failure.txt"


@dataclass(frozen=True, slots=True)
class WindowsArtifactInput:
    """Paths required to audit and launch one frozen Windows artifact."""

    archive: Path
    wheel: Path


@dataclass(frozen=True, slots=True)
class AuditedWindowsArtifact:
    """Resolved Windows artifact paths paired with complete audit evidence."""

    archive: Path
    audit: WindowsPackageAudit
    wheel: Path


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """Raw packaged-loopback response retained for strict contract checks."""

    body: bytes
    headers: Mapping[str, str]
    status: int


class FlacTagWriter(Protocol):
    """Narrow Mutagen surface used to create one disposable tagged input."""

    def __setitem__(self, key: str, value: str) -> None:
        """Set one Vorbis-comment value."""

    def save(self) -> None:
        """Persist the generated FLAC tags."""


class ParsedArgs(argparse.Namespace):
    """Typed command-line arguments for native Windows package smoke."""

    def __init__(self, *, icon: Path, version_info: Path) -> None:
        super().__init__()
        self.archive: Path = Path()
        self.wheel: Path = Path()
        self.evidence: Path | None = None
        self.icon: Path = icon
        self.previous_archive: Path | None = None
        self.previous_wheel: Path | None = None
        self.version_info: Path = version_info


def smoke_windows_package(
    artifact: WindowsArtifactInput,
    evidence_path: Path,
    icon: Path,
    version_info: Path,
    *,
    previous_artifact: WindowsArtifactInput | None = None,
) -> None:
    """Audit, launch, replace, relaunch, and evidence one or two real Windows builds."""
    require_windows_x64(sys.platform, platform.machine(), struct.calcsize("P"))
    candidate = _audit_artifact(artifact, icon.resolve(), version_info.resolve())
    first_artifact, require_distinct_artifacts = _first_artifact(
        candidate,
        previous_artifact,
        icon.resolve(),
        version_info.resolve(),
    )
    artifact_transition = _artifact_transition_evidence(
        first_artifact,
        candidate,
        require_distinct=require_distinct_artifacts,
    )
    host_evidence = _windows_host_evidence()
    with (
        _native_diagnostic_directory(evidence_path) as diagnostic_directory,
        tempfile.TemporaryDirectory(prefix="omym2-native-smoke-") as temporary_directory,
    ):
        workspace = Path(temporary_directory).resolve()
        launch_working_directory = _create_launch_working_directory(workspace)
        launch_working_directory_snapshot = _tree_snapshot(launch_working_directory)
        path_root = _long_smoke_path_root(workspace)
        local_app_data = path_root / "local-app-data"
        library_root = path_root / "empty-library"
        incoming_root = path_root / "incoming"
        source_file = incoming_root / "smoke-track.flac"
        extraction_a = workspace / "application-build-a"
        extraction_b = workspace / "application-build-b"
        local_app_data.mkdir(parents=True)
        library_root.mkdir()
        _write_tagged_smoke_flac(source_file)
        _require_long_unicode_paths(local_app_data, library_root, incoming_root)

        bundle_a = extract_windows_archive(first_artifact.archive, extraction_a)
        executable_a = bundle_a / config.DESKTOP_WINDOWS_EXECUTABLE_NAME
        log_file = local_app_data / config.DESKTOP_WINDOWS_LOG_RELATIVE_PATH
        first_launch, planning_created = _run_native_launch(
            NativeLaunchContext(
                diagnostic_directory=diagnostic_directory,
                executable=executable_a,
                launch_name="first-launch",
                launch_working_directory=launch_working_directory,
                local_app_data=local_app_data,
                log_file=log_file,
            ),
            lambda base_url, _window_handle: _create_safe_add_plan(
                base_url,
                library_root,
                incoming_root,
                source_file,
            ),
        )
        _require_tree_unchanged(
            launch_working_directory,
            launch_working_directory_snapshot,
            context="first native launch working directory",
        )
        database_file = local_app_data / config.DESKTOP_WINDOWS_DATABASE_RELATIVE_PATH
        if not database_file.is_file():
            msg = f"First native launch did not create SQLite state: {database_file}"
            raise WindowsPackageSmokeError(msg)
        database_sha256_before_replacement = _file_sha256(database_file)
        database_size_bytes_before_replacement = database_file.stat().st_size
        config_file = _write_valid_smoke_config(local_app_data)
        _delete_application_copy_and_require_state(
            extraction_a,
            config_file,
            database_file,
            database_sha256_before_replacement,
        )

        bundle_b = extract_windows_archive(candidate.archive, extraction_b)
        executable_b = bundle_b / config.DESKTOP_WINDOWS_EXECUTABLE_NAME
        second_launch, planning_persisted = _run_native_launch(
            NativeLaunchContext(
                diagnostic_directory=diagnostic_directory,
                executable=executable_b,
                launch_name="second-launch",
                launch_working_directory=launch_working_directory,
                local_app_data=local_app_data,
                log_file=log_file,
            ),
            lambda base_url, window_handle: _verify_persisted_plan_and_create_through_native_ui(
                base_url,
                window_handle,
                planning_created,
                library_root,
                source_file,
            ),
        )
        _require_tree_unchanged(
            launch_working_directory,
            launch_working_directory_snapshot,
            context="second native launch working directory",
        )
        if config_file.read_text(encoding="utf-8") != config.DESKTOP_WINDOWS_SMOKE_CONFIG_MARKER:
            msg = "Mutable Config state did not survive application-directory replacement."
            raise WindowsPackageSmokeError(msg)
        if not database_file.is_file():
            msg = "SQLite state disappeared during second native launch."
            raise WindowsPackageSmokeError(msg)
        database_sha256_after_native_ui, database_size_bytes_after_native_ui = (
            _file_sha256(database_file),
            database_file.stat().st_size,
        )
        _require_mutable_state_outside_bundle(bundle_b)
        extracted_size_bytes = _directory_size(bundle_b)
        _delete_application_copy_and_require_state(
            extraction_b,
            config_file,
            database_file,
            database_sha256_after_native_ui,
        )

        evidence = {
            "artifact": {
                "filename": candidate.archive.name,
                "payload_sha256": candidate.audit.artifact_payload_sha256,
                "sha256": candidate.audit.artifact_sha256,
                "size_bytes": candidate.audit.artifact_size_bytes,
                "extracted_size_bytes": extracted_size_bytes,
                "pe_machine": candidate.audit.pe_machine,
                "pe_subsystem": candidate.audit.pe_subsystem,
                "wheel_filename": candidate.wheel.name,
                "wheel_sha256": candidate.audit.wheel_sha256,
            },
            "artifact_transition": artifact_transition,
            "coverage_boundary": {
                "native_ui_automation": "performed",
                "native_ui_non_destructive_plan": "performed",
                "packaged_api_non_destructive_plan": "performed",
                "reason": (
                    "Microsoft UI Automation drives the packaged WebView accessibility tree through interactive "
                    "Overview content, all six shell navigation routes, loaded Settings, and a non-destructive Add "
                    "Plan into Plan detail. HTTP probes separately cover every production SPA deep route and API "
                    "boundary; canonical Playwright E2E remains the broader browser-hosted behavior suite."
                ),
            },
            "external_browser": {
                "process_appeared": False,
                "window_appeared": False,
            },
            "host": host_evidence,
            "launches": [asdict(first_launch), asdict(second_launch)],
            "native_ui": _required_mapping(
                planning_persisted,
                "native_ui",
                context="second-copy native UI evidence",
            ),
            "packaged_api": {
                "created_on_first_copy": planning_created,
                "verified_on_second_copy": planning_persisted,
            },
            "mutable_state": {
                "config_marker_sha256": hashlib.sha256(config.DESKTOP_WINDOWS_SMOKE_CONFIG_MARKER.encode()).hexdigest(),
                "config_path": str(config_file.resolve()),
                "database_path": str(database_file.resolve()),
                "database_sha256_after_native_ui": database_sha256_after_native_ui,
                "database_sha256_before_replacement": database_sha256_before_replacement,
                "database_size_bytes_after_native_ui": database_size_bytes_after_native_ui,
                "database_size_bytes_before_replacement": database_size_bytes_before_replacement,
                "first_application_directory_deleted": True,
                "outside_replaceable_application_directory": True,
                "second_application_directory_deleted": True,
                "shared_local_app_data": str(local_app_data.resolve()),
            },
            "package_version": candidate.audit.package_version,
            "paths": {
                "extraction_a": str(extraction_a.resolve()),
                "extraction_b": str(extraction_b.resolve()),
                "local_app_data": str(local_app_data.resolve()),
                "launch_working_directory": str(launch_working_directory.resolve()),
                "launch_working_directory_characters": len(str(launch_working_directory.resolve())),
                "launch_working_directory_manifest_sha256": _tree_snapshot_sha256(launch_working_directory_snapshot),
                "launch_working_directory_unchanged": True,
                "maximum_application_executable_characters": max(
                    len(str(path.resolve())) for path in (executable_a, executable_b)
                ),
                "application_executables_below_legacy_max_path": all(
                    len(str(path.resolve())) < config.DESKTOP_WINDOWS_LEGACY_MAX_PATH_CHARACTERS
                    for path in (executable_a, executable_b)
                ),
                "maximum_characters": max(
                    len(str(path.resolve())) for path in (executable_a, executable_b, database_file)
                ),
                "exceeds_legacy_max_path": True,
                "unicode_and_long_component": True,
            },
        }
        _write_json_atomically(evidence_path, evidence)


@contextlib.contextmanager
def _native_diagnostic_directory(evidence_path: Path) -> Generator[Path]:
    """Remove stale diagnostics, retain failures, and discard successful launch captures."""
    diagnostic_directory = evidence_path.with_name(f"{evidence_path.stem}-diagnostics")
    if diagnostic_directory.exists():
        shutil.rmtree(diagnostic_directory)
    diagnostic_directory.mkdir(parents=True)
    completed = False
    try:
        yield diagnostic_directory
        completed = True
    finally:
        if completed:
            shutil.rmtree(diagnostic_directory)


def _first_artifact(
    candidate: AuditedWindowsArtifact,
    previous_artifact: WindowsArtifactInput | None,
    icon: Path,
    version_info: Path,
) -> tuple[AuditedWindowsArtifact, bool]:
    """Select and audit the optional first-build artifact."""
    if previous_artifact is None:
        return candidate, False
    return _audit_artifact(previous_artifact, icon, version_info), True


def _long_smoke_path_root(workspace: Path) -> Path:
    """Build the bounded Unicode path whose descendants exceed legacy MAX_PATH."""
    long_component = "long-" + "x" * config.DESKTOP_WINDOWS_SMOKE_LONG_COMPONENT_CHARACTERS
    path_root = workspace / config.DESKTOP_WINDOWS_SMOKE_UNICODE_DIRECTORY_NAME
    for index in range(config.DESKTOP_WINDOWS_SMOKE_LONG_COMPONENT_COUNT):
        path_root /= f"{index}-{long_component}"
    return path_root


def _create_launch_working_directory(workspace: Path) -> Path:
    """Create the dedicated short and initially empty child working directory."""
    launch_working_directory = workspace / config.DESKTOP_WINDOWS_SMOKE_LAUNCH_CWD_DIRECTORY_NAME
    launch_working_directory.mkdir()
    return launch_working_directory


def _audit_artifact(
    artifact: WindowsArtifactInput,
    icon: Path,
    version_info: Path,
) -> AuditedWindowsArtifact:
    """Resolve and completely audit one native artifact input."""
    archive = artifact.archive.resolve()
    wheel = artifact.wheel.resolve()
    audit = audit_windows_package(archive, wheel, icon, version_info)
    return AuditedWindowsArtifact(archive=archive, audit=audit, wheel=wheel)


def _optional_artifact_input(
    archive: Path | None,
    wheel: Path | None,
) -> WindowsArtifactInput | None:
    """Convert a complete optional CLI pair into one typed artifact input."""
    if (archive is None) != (wheel is None):
        msg = "Previous-build smoke requires both --previous-archive and --previous-wheel."
        raise WindowsPackageSmokeError(msg)
    if archive is None or wheel is None:
        return None
    return WindowsArtifactInput(archive=archive, wheel=wheel)


def _artifact_transition_evidence(
    first: AuditedWindowsArtifact,
    second: AuditedWindowsArtifact,
    *,
    require_distinct: bool,
) -> dict[str, object]:
    """Describe the exact artifact transition and reject fake cross-build evidence."""
    archive_sha256_changed = first.audit.artifact_sha256 != second.audit.artifact_sha256
    payload_sha256_changed = first.audit.artifact_payload_sha256 != second.audit.artifact_payload_sha256
    if require_distinct and not payload_sha256_changed:
        msg = (
            "Previous and candidate Windows archives have identical payloads; cross-build evidence requires two builds."
        )
        raise WindowsPackageSmokeError(msg)
    package_version_changed = first.audit.package_version != second.audit.package_version
    if package_version_changed:
        msg = "Cross-version smoke requires version-specific audit metadata and an explicit migration contract."
        raise WindowsPackageSmokeError(msg)
    kind = "cross_build_same_package_version" if payload_sha256_changed else "same_artifact_relaunch"
    return {
        "archive_sha256_changed": archive_sha256_changed,
        "from": _artifact_identity(first),
        "kind": kind,
        "package_version_changed": package_version_changed,
        "payload_sha256_changed": payload_sha256_changed,
        "shared_local_app_data": True,
        "to": _artifact_identity(second),
    }


def _artifact_identity(
    artifact: AuditedWindowsArtifact,
) -> dict[str, object]:
    """Return retained identity fields for one audited native artifact."""
    return {
        "archive_filename": artifact.archive.name,
        "archive_sha256": artifact.audit.artifact_sha256,
        "payload_sha256": artifact.audit.artifact_payload_sha256,
        "package_version": artifact.audit.package_version,
        "wheel_filename": artifact.wheel.name,
        "wheel_sha256": artifact.audit.wheel_sha256,
    }


def _run_native_launch(
    context: NativeLaunchContext,
    packaged_probe: Callable[[str, int], dict[str, object]],
) -> tuple[NativeLaunchEvidence, dict[str, object]]:
    try:
        with context.stdout_file.open("wb") as stdout_stream, context.stderr_file.open("wb") as stderr_stream:
            return _run_captured_native_launch(
                context,
                (stdout_stream, stderr_stream),
                packaged_probe,
            )
    except Exception as exc:
        diagnostic_message = _retain_native_launch_failure(exc, context)
        raise WindowsPackageSmokeError(diagnostic_message) from exc


def _run_captured_native_launch(
    context: NativeLaunchContext,
    output_streams: tuple[BinaryIO, BinaryIO],
    packaged_probe: Callable[[str, int], dict[str, object]],
) -> tuple[NativeLaunchEvidence, dict[str, object]]:
    """Exercise one native launch while retaining otherwise invisible GUI diagnostics."""
    baseline = _browser_snapshot()
    log_offset = context.log_file.stat().st_size if context.log_file.is_file() else 0
    environment = _packaged_environment(context.local_app_data)
    started_at = time.perf_counter()
    stdout_stream, stderr_stream = output_streams
    process = _start_native_process(
        context.executable,
        context.launch_working_directory,
        environment,
        stdout_stream,
        stderr_stream,
    )
    window_handle: int | None = None
    try:
        base_url = _wait_for_ready_url(process, context.log_file, log_offset)
        window_handle = _wait_for_one_window(process.pid)
        webview_backend = _wait_for_loaded_webview(process, context.log_file, log_offset)
        startup_milliseconds = round((time.perf_counter() - started_at) * 1000)
        smoke_web_package(base_url)
        routes = _smoke_primary_routes(base_url)
        security = _smoke_security_boundaries(base_url)
        packaged_evidence = packaged_probe(base_url, window_handle)
        active = _browser_snapshot()
        new_processes = sorted(set(active.process_ids) - set(baseline.process_ids))
        new_windows = sorted(set(active.windows) - set(baseline.windows))
        if new_processes or new_windows:
            msg = f"Packaged GUI launched an external browser: process_ids={new_processes}, windows={new_windows}"
            raise WindowsPackageSmokeError(msg)
        shutdown_started = time.perf_counter()
        _post_native_close(window_handle)
        try:
            exit_code = process.wait(timeout=config.DESKTOP_WINDOWS_SMOKE_SHUTDOWN_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            msg = "Packaged GUI did not exit after its native window received WM_CLOSE."
            raise WindowsPackageSmokeError(msg) from exc
        shutdown_milliseconds = round((time.perf_counter() - shutdown_started) * 1000)
        if exit_code != 0:
            msg = f"Packaged GUI exited with status {exit_code}."
            raise WindowsPackageSmokeError(msg)
        _require_listener_terminated(base_url)
        return (
            NativeLaunchEvidence(
                external_browser_process_appeared=False,
                external_browser_window_appeared=False,
                listener_terminated=True,
                process_exit_code=exit_code,
                routes=routes,
                security=security,
                shutdown_milliseconds=shutdown_milliseconds,
                startup_milliseconds=startup_milliseconds,
                visible_window_count=1,
                webview_backend=webview_backend,
            ),
            packaged_evidence,
        )
    finally:
        if process.poll() is None:
            if window_handle is not None:
                with contextlib.suppress(WindowsPackageSmokeError):
                    _post_native_close(window_handle)
            try:
                _ = process.wait(timeout=config.DESKTOP_WINDOWS_SMOKE_SHUTDOWN_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                _ = process.wait()


def _start_native_process(
    executable: Path,
    launch_working_directory: Path,
    environment: Mapping[str, str],
    stdout_stream: BinaryIO,
    stderr_stream: BinaryIO,
) -> subprocess.Popen[bytes]:
    """Launch the long-path executable without imposing a long child current directory."""
    executable_path = str(executable.resolve())
    working_directory = launch_working_directory.resolve()
    if not working_directory.is_dir():
        msg = f"Native launch working directory does not exist: {working_directory}"
        raise WindowsPackageSmokeError(msg)
    working_directory_path = str(working_directory)
    if len(working_directory_path) > config.DESKTOP_WINDOWS_SMOKE_MAXIMUM_LAUNCH_CWD_CHARACTERS:
        msg = (
            "Native launch working directory exceeds the safe CreateProcessW limit: "
            f"{len(working_directory_path)} characters"
        )
        raise WindowsPackageSmokeError(msg)
    return subprocess.Popen(  # noqa: S603 -- launches the audited local GUI executable under test.
        (executable_path,),
        executable=executable_path,
        cwd=working_directory_path,
        env=environment,
        stdout=stdout_stream,
        stderr=stderr_stream,
    )


def _wait_for_ready_url(process: subprocess.Popen[bytes], log_file: Path, offset: int) -> str:
    deadline = time.monotonic() + config.DESKTOP_WINDOWS_SMOKE_STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        _require_process_running(process, "loopback readiness")
        appended = _read_appended_log(log_file, offset)
        if config.DESKTOP_WINDOWS_FAILURE_LOG_MARKER.encode() in appended:
            msg = "Packaged GUI reported a fatal startup failure before loopback readiness."
            raise WindowsPackageSmokeError(msg)
        matches = tuple(_READY_URL_PATTERN.finditer(appended))
        if matches:
            return matches[-1].group(1).decode("ascii")
        time.sleep(config.DESKTOP_WINDOWS_SMOKE_POLL_INTERVAL_SECONDS)
    msg = f"Timed out waiting for packaged server URL in {log_file}."
    raise WindowsPackageSmokeError(msg)


def _retain_native_launch_failure(
    failure: Exception,
    context: NativeLaunchContext,
) -> str:
    """Persist and summarize the logs needed to diagnose a packaged GUI startup failure."""
    desktop_log_error: str | None = None
    try:
        _ = shutil.copyfile(context.log_file, context.retained_desktop_log)
    except FileNotFoundError:
        desktop_log_error = "not created"
    except OSError as exc:
        desktop_log_error = f"could not be retained: {exc}"

    lines = [
        str(failure),
        f"Native launch diagnostics retained at {context.diagnostic_directory}.",
    ]
    for label, path, unavailable_reason in (
        ("desktop log", context.retained_desktop_log, desktop_log_error),
        ("stdout", context.stdout_file, None),
        ("stderr", context.stderr_file, None),
    ):
        if unavailable_reason is not None:
            lines.append(f"{label}: <{unavailable_reason}>")
            continue
        try:
            payload = path.read_bytes()
        except OSError as exc:
            lines.append(f"{label}: <could not be read: {exc}>")
            continue
        tail = payload[-config.DESKTOP_WINDOWS_SMOKE_DIAGNOSTIC_TAIL_BYTES :]
        decoded_tail = tail.decode("utf-8", errors="replace").strip()
        lines.append(f"{label} tail:\n{decoded_tail or '<empty>'}")
    message = "\n".join(lines)
    try:
        _ = context.failure_summary_file.write_text(message + "\n", encoding="utf-8", newline="\n")
    except OSError as exc:
        message += f"\nFailure summary could not be retained at {context.failure_summary_file}: {exc}"
    return message


def _wait_for_loaded_webview(process: subprocess.Popen[bytes], log_file: Path, offset: int) -> str:
    deadline = time.monotonic() + config.DESKTOP_WINDOWS_SMOKE_STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        _require_process_running(process, "WebView2 content load")
        appended = _read_appended_log(log_file, offset)
        if backend := _loaded_webview_backend(appended):
            return backend
        time.sleep(config.DESKTOP_WINDOWS_SMOKE_POLL_INTERVAL_SECONDS)
    msg = f"Timed out waiting for exact EdgeChromium and successful content-loaded evidence in {log_file}."
    raise WindowsPackageSmokeError(msg)


def _loaded_webview_backend(appended_log: bytes) -> str | None:
    initialized_at = appended_log.find(config.DESKTOP_WINDOWS_WEBVIEW_INITIALIZED_LOG_MARKER.encode())
    loaded_at = appended_log.find(config.DESKTOP_WINDOWS_WEBVIEW_LOADED_LOG_MARKER.encode())
    if loaded_at >= 0 and (initialized_at < 0 or loaded_at < initialized_at):
        msg = "Packaged GUI reported loaded content without exact prior EdgeChromium initialization."
        raise WindowsPackageSmokeError(msg)
    return "edgechromium" if initialized_at >= 0 and loaded_at > initialized_at else None


def _wait_for_one_window(process_id: int) -> int:
    payload = _run_powershell(
        _WAIT_FOR_WINDOW_SCRIPT,
        str(process_id),
        config.DESKTOP_APPLICATION_NAME,
        str(round(config.DESKTOP_WINDOWS_SMOKE_STARTUP_TIMEOUT_SECONDS * 1000)),
        timeout=config.DESKTOP_WINDOWS_SMOKE_STARTUP_TIMEOUT_SECONDS + config.DESKTOP_WINDOWS_METADATA_TIMEOUT_SECONDS,
    )
    raw_windows = payload.get("windows")
    if not isinstance(raw_windows, list):
        msg = "Native window probe did not return exactly one window."
        raise WindowsPackageSmokeError(msg)
    windows = cast("list[object]", raw_windows)
    if len(windows) != 1 or not isinstance(windows[0], dict):
        msg = "Native window probe did not return exactly one window."
        raise WindowsPackageSmokeError(msg)
    window = cast("dict[str, object]", windows[0])
    handle = window.get("handle")
    if not isinstance(handle, int) or isinstance(handle, bool) or handle <= 0:
        msg = "Native window probe returned an invalid window handle."
        raise WindowsPackageSmokeError(msg)
    if window.get("title") != config.DESKTOP_APPLICATION_NAME:
        msg = "Native window probe returned an unexpected title."
        raise WindowsPackageSmokeError(msg)
    return handle


def _post_native_close(window_handle: int) -> None:
    payload = _run_powershell(
        _CLOSE_WINDOW_SCRIPT,
        str(window_handle),
        timeout=config.DESKTOP_WINDOWS_METADATA_TIMEOUT_SECONDS,
    )
    if payload.get("posted") is not True:
        msg = "Windows rejected the packaged window's WM_CLOSE message."
        raise WindowsPackageSmokeError(msg)


def _browser_snapshot() -> BrowserSnapshot:
    payload = _run_powershell(
        _BROWSER_SNAPSHOT_SCRIPT,
        ",".join(config.DESKTOP_WINDOWS_EXTERNAL_BROWSER_PROCESS_NAMES),
        timeout=config.DESKTOP_WINDOWS_METADATA_TIMEOUT_SECONDS,
    )
    raw_process_values = payload.get("processes")
    raw_window_values = payload.get("windows")
    if not isinstance(raw_process_values, list) or not isinstance(raw_window_values, list):
        msg = "External browser snapshot returned an invalid payload."
        raise WindowsPackageSmokeError(msg)
    raw_processes = cast("list[object]", raw_process_values)
    raw_windows = cast("list[object]", raw_window_values)
    process_ids: list[int] = []
    for raw_process in raw_processes:
        if not isinstance(raw_process, dict):
            msg = "External browser snapshot returned an invalid process record."
            raise WindowsPackageSmokeError(msg)
        process_record = cast("dict[str, object]", raw_process)
        process_id = process_record.get("process_id")
        if not isinstance(process_id, int) or isinstance(process_id, bool):
            msg = "External browser snapshot returned an invalid process record."
            raise WindowsPackageSmokeError(msg)
        process_ids.append(process_id)
    windows: list[tuple[int, int, str]] = []
    for raw_window in raw_windows:
        if not isinstance(raw_window, dict):
            msg = "External browser snapshot returned an invalid window record."
            raise WindowsPackageSmokeError(msg)
        window_record = cast("dict[str, object]", raw_window)
        process_id = window_record.get("process_id")
        handle = window_record.get("handle")
        title = window_record.get("title")
        if (
            not isinstance(process_id, int)
            or isinstance(process_id, bool)
            or not isinstance(handle, int)
            or isinstance(handle, bool)
            or not isinstance(title, str)
        ):
            msg = "External browser snapshot returned malformed window values."
            raise WindowsPackageSmokeError(msg)
        windows.append((process_id, handle, title))
    return BrowserSnapshot(process_ids=tuple(sorted(process_ids)), windows=tuple(sorted(windows)))


def _run_powershell(script: str, *arguments: str, timeout: float) -> dict[str, object]:
    try:
        result = subprocess.run(  # noqa: S603 -- fixed native probes receive only local IDs, paths, and names.
            (
                config.DESKTOP_WINDOWS_POWERSHELL_EXECUTABLE_NAME,
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                f"{_POWERSHELL_UTF8_PREAMBLE}\n& {{\n{script}\n}}",
                *arguments,
            ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        msg = f"Native Windows probe timed out after {timeout:g} seconds."
        raise WindowsPackageSmokeError(msg) from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic output"
        msg = f"Native Windows probe failed: {detail}"
        raise WindowsPackageSmokeError(msg)
    output_lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not output_lines:
        msg = "Native Windows probe returned no JSON output."
        raise WindowsPackageSmokeError(msg)
    try:
        payload = cast("object", json.loads(output_lines[-1]))
    except json.JSONDecodeError as exc:
        msg = "Native Windows probe returned invalid JSON."
        raise WindowsPackageSmokeError(msg) from exc
    if not isinstance(payload, dict):
        msg = "Native Windows probe did not return a JSON object."
        raise WindowsPackageSmokeError(msg)
    return cast("dict[str, object]", payload)


def _windows_host_evidence() -> dict[str, object]:
    payload = _run_powershell(
        _WINDOWS_HOST_SCRIPT,
        timeout=config.DESKTOP_WINDOWS_METADATA_TIMEOUT_SECONDS,
    )
    required_strings = (
        "architecture",
        "build_number",
        "caption",
        "edition_id",
        "installation_type",
        "version",
    )
    for name in required_strings:
        _ = _required_string(payload, name, context="Windows host inventory")
    build_number_text = _required_string(payload, "build_number", context="Windows host inventory")
    try:
        build_number = int(build_number_text)
    except ValueError as exc:
        msg = f"Windows host inventory returned invalid build number {build_number_text!r}."
        raise WindowsPackageSmokeError(msg) from exc
    product_type = payload.get("product_type")
    if (
        not isinstance(product_type, int)
        or isinstance(product_type, bool)
        or product_type not in _WINDOWS_PRODUCT_TYPES
    ):
        msg = f"Windows host inventory returned invalid ProductType {product_type!r}."
        raise WindowsPackageSmokeError(msg)
    return {
        **payload,
        "environment_class": _WINDOWS_PRODUCT_TYPES[product_type],
        "is_windows_11_workstation": product_type == 1 and build_number >= _WINDOWS_11_MINIMUM_BUILD,
        "platform_machine": platform.machine(),
        "platform_platform": platform.platform(),
        "pointer_bits": struct.calcsize("P") * _BITS_PER_BYTE,
    }


def _smoke_primary_routes(base_url: str) -> tuple[str, ...]:
    root_body: bytes | None = None
    for route in config.DESKTOP_WINDOWS_SMOKE_PRIMARY_ROUTES:
        response = _request_loopback(base_url, "GET", route, headers={"Accept": "text/html"})
        if response.status != _SUCCESS_STATUS_CODE:
            msg = f"Packaged primary route {route} returned HTTP {response.status}."
            raise WindowsPackageSmokeError(msg)
        if root_body is None:
            root_body = response.body
        elif response.body != root_body:
            msg = f"Packaged primary route {route} did not return the shared SPA entry."
            raise WindowsPackageSmokeError(msg)
    return config.DESKTOP_WINDOWS_SMOKE_PRIMARY_ROUTES


def _smoke_security_boundaries(base_url: str) -> dict[str, object]:
    missing_csrf = _request_loopback(
        base_url,
        "POST",
        _API_CHECK_ROUTE,
        body=b"{}",
        headers={
            "Content-Type": "application/json",
            _IDEMPOTENCY_HEADER_NAME: str(uuid4()),
        },
    )
    _require_status(missing_csrf, _HTTP_FORBIDDEN_STATUS, context="missing-CSRF mutation")
    csrf_error_code = _first_error_code(missing_csrf, context="missing-CSRF mutation")
    if csrf_error_code != "csrf_invalid":
        msg = f"Missing-CSRF mutation returned unexpected error code {csrf_error_code!r}."
        raise WindowsPackageSmokeError(msg)

    hostile_host = _request_loopback(
        base_url,
        "GET",
        _API_BOOTSTRAP_ROUTE,
        headers={"Host": _HOSTILE_HOST_HEADER},
    )
    _require_status(hostile_host, _HTTP_NOT_FOUND_STATUS, context="hostile API Host request")
    hostile_host_error_code = _first_error_code(hostile_host, context="hostile API Host request")
    if hostile_host_error_code != "api_not_found":
        msg = f"Hostile API Host request returned unexpected error code {hostile_host_error_code!r}."
        raise WindowsPackageSmokeError(msg)

    bootstrap = _bootstrap_data(base_url, require_valid_config=True)
    csrf_token = _required_string(bootstrap, "csrf_token", context="Bootstrap")
    malformed_json = _request_loopback(
        base_url,
        "POST",
        _API_CHECK_ROUTE,
        body=b"{",
        headers={
            "Content-Type": "application/json",
            _CSRF_HEADER_NAME: csrf_token,
            _IDEMPOTENCY_HEADER_NAME: str(uuid4()),
        },
    )
    _require_status(malformed_json, _HTTP_BAD_REQUEST_STATUS, context="malformed JSON mutation")
    malformed_error_code = _first_error_code(malformed_json, context="malformed JSON mutation")
    if malformed_error_code != "invalid_json":
        msg = f"Malformed JSON mutation returned unexpected error code {malformed_error_code!r}."
        raise WindowsPackageSmokeError(msg)
    lowered_error_body = malformed_json.body.lower()
    internal_markers = (b"traceback", b"site-packages", b'file "')
    if any(marker in lowered_error_body for marker in internal_markers):
        msg = "Malformed JSON response exposed an internal traceback or installation path."
        raise WindowsPackageSmokeError(msg)
    return {
        "hostile_host_rejected": True,
        "hostile_host_error_code": hostile_host_error_code,
        "hostile_host_status": hostile_host.status,
        "malformed_json_error_code": malformed_error_code,
        "malformed_json_internal_detail_absent": True,
        "malformed_json_status": malformed_json.status,
        "missing_csrf_error_code": csrf_error_code,
        "missing_csrf_rejected": True,
        "missing_csrf_status": missing_csrf.status,
    }


def _write_tagged_smoke_flac(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_bytes(_minimal_flac_bytes())
    audio = cast("FlacTagWriter", FLAC(path))
    audio["title"] = "Packaged Smoke Track"
    audio["artist"] = "OMYM2 Smoke Artist"
    audio["albumartist"] = "OMYM2 Smoke Artist"
    audio["album"] = "Packaged Smoke Album"
    audio["date"] = "2026"
    audio["tracknumber"] = "1/1"
    audio["discnumber"] = "1/1"
    audio.save()
    remaining_bytes = config.DESKTOP_WINDOWS_SMOKE_AUDIO_FILE_BYTES - path.stat().st_size
    if remaining_bytes < 0:
        msg = f"Generated tagged FLAC exceeds its configured size: {path.stat().st_size} bytes."
        raise WindowsPackageSmokeError(msg)
    with path.open("ab") as stream:
        _ = stream.write(bytes(remaining_bytes))


def _minimal_flac_bytes() -> bytes:
    stream_info = _FLAC_STREAMINFO_BLOCK_SIZE_SAMPLES.to_bytes(2, _FLAC_BYTE_ORDER) * 2
    stream_info += bytes(_FLAC_FRAME_SIZE_FIELDS_BYTES)
    sample_rate_shift = _FLAC_CHANNEL_COUNT_BITS + _FLAC_SAMPLE_SIZE_FIELD_BITS + _FLAC_TOTAL_SAMPLES_BITS
    channel_count_shift = _FLAC_SAMPLE_SIZE_FIELD_BITS + _FLAC_TOTAL_SAMPLES_BITS
    sample_size_shift = _FLAC_TOTAL_SAMPLES_BITS
    packed_audio_properties = (
        _FLAC_SAMPLE_RATE_HZ << sample_rate_shift
        | (_FLAC_CHANNEL_COUNT - _INDEX_DISPLAY_OFFSET) << channel_count_shift
        | (_FLAC_SAMPLE_SIZE_BITS - _INDEX_DISPLAY_OFFSET) << sample_size_shift
    )
    packed_property_bytes = (
        _FLAC_SAMPLE_RATE_BITS + _FLAC_CHANNEL_COUNT_BITS + _FLAC_SAMPLE_SIZE_FIELD_BITS + _FLAC_TOTAL_SAMPLES_BITS
    ) // _BITS_PER_BYTE
    stream_info += packed_audio_properties.to_bytes(packed_property_bytes, _FLAC_BYTE_ORDER)
    stream_info += bytes(_FLAC_MD5_BYTES)
    block_header = bytes((_FLAC_LAST_METADATA_BLOCK_FLAG, 0, 0, _FLAC_STREAMINFO_LENGTH_BYTES))
    return _FLAC_STREAM_MARKER + block_header + stream_info


def _create_safe_add_plan(
    base_url: str,
    library_root: Path,
    incoming_root: Path,
    source_file: Path,
) -> dict[str, object]:
    incoming_snapshot = _tree_snapshot(incoming_root)
    library_snapshot = _tree_snapshot(library_root)
    bootstrap = _bootstrap_data(base_url, require_valid_config=True)
    organize_operation_id, organize = _start_and_poll_operation(
        base_url,
        _API_ORGANIZE_ROUTE,
        {"library_root": str(library_root.resolve())},
        _required_string(bootstrap, "csrf_token", context="Bootstrap"),
    )
    organize_result = _required_mapping(organize, "result", context="Organize Operation")
    if organize_result.get("kind") != "registered_without_plan" or organize_result.get("track_count") != 0:
        msg = f"Empty-Library Organize returned unexpected result: {organize_result}"
        raise WindowsPackageSmokeError(msg)
    library_id = _required_string(organize_result, "library_id", context="Organize result")

    refreshed_bootstrap = _bootstrap_data(base_url, require_valid_config=True)
    active_library = _required_mapping(refreshed_bootstrap, "active_library", context="Bootstrap")
    if active_library.get("library_id") != library_id:
        msg = "Bootstrap did not select the Library registered by packaged Organize."
        raise WindowsPackageSmokeError(msg)
    add_operation_id, add = _start_and_poll_operation(
        base_url,
        _API_ADD_ROUTE,
        {"library_id": library_id, "source_path": str(incoming_root.resolve())},
        _required_string(refreshed_bootstrap, "csrf_token", context="Bootstrap"),
    )
    add_result = _required_mapping(add, "result", context="Add Operation")
    if add_result.get("kind") != "plan_created":
        msg = f"Tagged-input Add did not create a reviewable Plan: {add_result}"
        raise WindowsPackageSmokeError(msg)
    plan_id = _required_string(add_result, "plan_id", context="Add result")
    plan_status = _verify_plan_detail(base_url, plan_id, library_id)
    if _tree_snapshot(incoming_root) != incoming_snapshot:
        msg = "Packaged API Add planning changed its disposable incoming tree."
        raise WindowsPackageSmokeError(msg)
    if _tree_snapshot(library_root) != library_snapshot:
        msg = "Packaged API Add planning changed its disposable Library tree."
        raise WindowsPackageSmokeError(msg)
    return {
        "add_operation_id": add_operation_id,
        "add_result_kind": "plan_created",
        "filesystem_mutation_performed": False,
        "incoming_tree_manifest_sha256": _tree_snapshot_sha256(incoming_snapshot),
        "library_id": library_id,
        "library_tree_manifest_sha256": _tree_snapshot_sha256(library_snapshot),
        "organize_operation_id": organize_operation_id,
        "organize_result_kind": "registered_without_plan",
        "plan_id": plan_id,
        "plan_status": plan_status,
        "source_fixture_sha256": _file_sha256(source_file),
        "source_fixture_size_bytes": source_file.stat().st_size,
        "track_count": 0,
    }


def _verify_persisted_plan_and_config(base_url: str, plan_id: str, library_id: str) -> dict[str, object]:
    bootstrap = _bootstrap_data(base_url, require_valid_config=True)
    active_library = _required_mapping(bootstrap, "active_library", context="Bootstrap")
    if active_library.get("library_id") != library_id:
        msg = "Second application copy did not restore the registered Library."
        raise WindowsPackageSmokeError(msg)
    settings_response = _request_loopback(base_url, "GET", _API_SETTINGS_ROUTE)
    _require_status(settings_response, _SUCCESS_STATUS_CODE, context="Settings read")
    settings_data = _envelope_data(settings_response, context="Settings read")
    settings_validation = _required_mapping(settings_data, "validation", context="Settings read")
    if settings_validation.get("valid") is not True or settings_validation.get("errors") != []:
        msg = f"Persisted minimal Config loaded with Settings recovery errors: {settings_validation}"
        raise WindowsPackageSmokeError(msg)
    plan_status = _verify_plan_detail(base_url, plan_id, library_id)
    return {
        "bootstrap_config_errors": [],
        "bootstrap_config_valid": True,
        "library_id": library_id,
        "plan_id": plan_id,
        "plan_status": plan_status,
        "settings_errors": [],
        "settings_validation_valid": True,
    }


def _verify_persisted_plan_and_create_through_native_ui(
    base_url: str,
    window_handle: int,
    created_planning: Mapping[str, object],
    library_root: Path,
    source_file: Path,
) -> dict[str, object]:
    persisted_plan_id = _required_string(created_planning, "plan_id", context="created planning evidence")
    library_id = _required_string(created_planning, "library_id", context="created planning evidence")
    persisted = _verify_persisted_plan_and_config(base_url, persisted_plan_id, library_id)
    plan_ids_before = _ready_add_plan_ids(base_url, library_id)
    source_sha256 = _file_sha256(source_file)
    source_size_bytes = source_file.stat().st_size
    incoming_snapshot = _tree_snapshot(source_file.parent)
    library_snapshot = _tree_snapshot(library_root)
    native_ui = _run_native_ui_automation(window_handle, source_file.parent)
    plan_ids_after = _ready_add_plan_ids(base_url, library_id)
    created_plan_ids = sorted(plan_ids_after - plan_ids_before)
    if len(created_plan_ids) != 1:
        msg = (
            "Native Add interaction did not create exactly one new ready Add Plan: "
            f"before={sorted(plan_ids_before)}, after={sorted(plan_ids_after)}"
        )
        raise WindowsPackageSmokeError(msg)
    native_plan_id = created_plan_ids[0]
    native_plan_status = _verify_plan_detail(base_url, native_plan_id, library_id)
    if native_plan_status != "ready":
        msg = f"Native Add interaction created Plan {native_plan_id} with status {native_plan_status!r}."
        raise WindowsPackageSmokeError(msg)
    if _tree_snapshot(source_file.parent) != incoming_snapshot:
        msg = "Native Add planning interaction changed its disposable incoming tree."
        raise WindowsPackageSmokeError(msg)
    if _tree_snapshot(library_root) != library_snapshot:
        msg = "Native Add planning interaction changed its disposable Library tree."
        raise WindowsPackageSmokeError(msg)
    native_ui.update(
        {
            "filesystem_mutation_performed": False,
            "incoming_tree_manifest_sha256": _tree_snapshot_sha256(incoming_snapshot),
            "library_id": library_id,
            "library_tree_manifest_sha256": _tree_snapshot_sha256(library_snapshot),
            "plan_id": native_plan_id,
            "plan_status": native_plan_status,
            "source_fixture_sha256": source_sha256,
            "source_fixture_size_bytes": source_size_bytes,
        }
    )
    return {**persisted, "native_ui": native_ui}


def _run_native_ui_automation(window_handle: int, incoming_root: Path) -> dict[str, object]:
    payload = _run_powershell(
        _NATIVE_UI_AUTOMATION_SCRIPT,
        str(window_handle),
        str(incoming_root.resolve()),
        str(round(config.DESKTOP_WINDOWS_SMOKE_STARTUP_TIMEOUT_SECONDS * 1000)),
        str(round(config.DESKTOP_WINDOWS_SMOKE_POLL_INTERVAL_SECONDS * 1000)),
        str(config.DESKTOP_WINDOWS_UIA_ARIA_ROLE_PROPERTY_ID),
        config.DESKTOP_WINDOWS_SMOKE_UI_ROOT_AUTOMATION_ID,
        config.DESKTOP_WINDOWS_SMOKE_UI_SETTINGS_AUTOMATION_ID,
        config.DESKTOP_WINDOWS_SMOKE_UI_ADD_SOURCE_AUTOMATION_ID,
        json.dumps(config.DESKTOP_WINDOWS_SMOKE_UI_PRIMARY_NAVIGATION, separators=(",", ":")),
        json.dumps(config.DESKTOP_WINDOWS_SMOKE_UI_OVERVIEW_ACTION, separators=(",", ":")),
        json.dumps(config.DESKTOP_WINDOWS_SMOKE_UI_ADD_ACTIONS, separators=(",", ":")),
        timeout=config.DESKTOP_WINDOWS_SMOKE_UI_AUTOMATION_TIMEOUT_SECONDS,
    )
    expected_routes = tuple(route for route, _link, _heading in config.DESKTOP_WINDOWS_SMOKE_UI_PRIMARY_NAVIGATION)
    if _required_string_sequence(payload, "primary_navigation_routes", context="native UI") != expected_routes:
        msg = "Native UI automation did not report the complete ordered primary navigation route set."
        raise WindowsPackageSmokeError(msg)
    if _required_string_sequence(payload, "deep_routes", context="native UI") != (
        "/plans/new/add",
        "/plans/:planId",
    ):
        msg = "Native UI automation did not report its Add and Plan-detail deep routes."
        raise WindowsPackageSmokeError(msg)
    expected_strings = {
        "automation_framework": "Microsoft UI Automation",
        "overview_action": config.DESKTOP_WINDOWS_SMOKE_UI_OVERVIEW_ACTION[0],
        "plan_submit_action": config.DESKTOP_WINDOWS_SMOKE_UI_ADD_ACTIONS[2],
        "root_automation_id": config.DESKTOP_WINDOWS_SMOKE_UI_ROOT_AUTOMATION_ID,
        "settings_editor_automation_id": config.DESKTOP_WINDOWS_SMOKE_UI_SETTINGS_AUTOMATION_ID,
    }
    for key, expected in expected_strings.items():
        if payload.get(key) != expected:
            msg = f"Native UI automation returned unexpected {key}: {payload.get(key)!r}."
            raise WindowsPackageSmokeError(msg)
    for key in (
        "add_source_value_verified",
        "overview_interactive",
        "plan_detail_loaded",
        "settings_loaded",
    ):
        if payload.get(key) is not True:
            msg = f"Native UI automation did not prove {key}."
            raise WindowsPackageSmokeError(msg)
    return payload


def _ready_add_plan_ids(base_url: str, library_id: str) -> frozenset[str]:
    response = _request_loopback(base_url, "GET", "/api/plans?status=ready&type=add&limit=100")
    _require_status(response, _SUCCESS_STATUS_CODE, context="ready Add Plans")
    data = _envelope_data(response, context="ready Add Plans")
    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        msg = "Ready Add Plan listing has no items array."
        raise WindowsPackageSmokeError(msg)
    plan_ids: set[str] = set()
    for raw_item in cast("list[object]", raw_items):
        if not isinstance(raw_item, dict):
            msg = f"Ready Add Plan listing returned a malformed item: {raw_item!r}."
            raise WindowsPackageSmokeError(msg)
        item = cast("dict[str, object]", raw_item)
        if item.get("plan_type") != "add" or item.get("status") != "ready":
            msg = f"Ready Add Plan listing ignored its requested filters: {item}."
            raise WindowsPackageSmokeError(msg)
        if item.get("library_id") != library_id:
            msg = f"Isolated native smoke returned a Plan for another Library: {item}."
            raise WindowsPackageSmokeError(msg)
        plan_ids.add(_required_string(item, "plan_id", context="ready Add Plan"))
    return frozenset(plan_ids)


def _start_and_poll_operation(
    base_url: str,
    route: str,
    body: Mapping[str, object],
    csrf_token: str,
) -> tuple[str, dict[str, object]]:
    response = _request_loopback(
        base_url,
        "POST",
        route,
        body=json.dumps(body, separators=(",", ":"), sort_keys=True).encode(),
        headers={
            "Content-Type": "application/json",
            _CSRF_HEADER_NAME: csrf_token,
            _IDEMPOTENCY_HEADER_NAME: str(uuid4()),
        },
    )
    if response.status not in {_HTTP_ACCEPTED_STATUS, _SUCCESS_STATUS_CODE}:
        msg = f"Packaged Operation start {route} returned HTTP {response.status}: {response.body!r}"
        raise WindowsPackageSmokeError(msg)
    operation_ref = _envelope_data(response, context=f"Operation start {route}")
    operation_id = _required_string(operation_ref, "operation_id", context=f"Operation start {route}")
    status_url = _required_string(operation_ref, "status_url", context=f"Operation start {route}")
    if response.headers.get("location") != status_url:
        msg = f"Packaged Operation start {route} did not return its status URL in Location."
        raise WindowsPackageSmokeError(msg)
    return operation_id, _poll_operation(base_url, status_url, operation_id)


def _poll_operation(base_url: str, status_url: str, operation_id: str) -> dict[str, object]:
    deadline = time.monotonic() + config.DESKTOP_WINDOWS_SMOKE_STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        response = _request_loopback(base_url, "GET", status_url)
        _require_status(response, _SUCCESS_STATUS_CODE, context=f"Operation {operation_id}")
        operation = _envelope_data(response, context=f"Operation {operation_id}")
        if operation.get("operation_id") != operation_id:
            msg = f"Operation status URL returned a different Operation: {operation}"
            raise WindowsPackageSmokeError(msg)
        status = _required_string(operation, "status", context=f"Operation {operation_id}")
        if status in _ACTIVE_OPERATION_STATUSES:
            time.sleep(config.DESKTOP_WINDOWS_SMOKE_POLL_INTERVAL_SECONDS)
            continue
        if status not in _TERMINAL_OPERATION_STATUSES:
            msg = f"Operation {operation_id} returned unknown status {status!r}."
            raise WindowsPackageSmokeError(msg)
        if status != "succeeded":
            msg = f"Packaged Operation {operation_id} ended {status}: {operation.get('error')}"
            raise WindowsPackageSmokeError(msg)
        return operation
    msg = f"Timed out waiting for packaged Operation {operation_id}."
    raise WindowsPackageSmokeError(msg)


def _verify_plan_detail(base_url: str, plan_id: str, library_id: str) -> str:
    response = _request_loopback(base_url, "GET", f"/api/plans/{plan_id}")
    _require_status(response, _SUCCESS_STATUS_CODE, context=f"Plan {plan_id}")
    detail = _envelope_data(response, context=f"Plan {plan_id}")
    plan = _required_mapping(detail, "plan", context=f"Plan {plan_id}")
    if plan.get("plan_id") != plan_id or plan.get("library_id") != library_id:
        msg = f"Packaged Plan detail differs from the created Plan identity: {plan}"
        raise WindowsPackageSmokeError(msg)
    return _required_string(plan, "status", context=f"Plan {plan_id}")


def _bootstrap_data(base_url: str, *, require_valid_config: bool) -> dict[str, object]:
    response = _request_loopback(base_url, "GET", _API_BOOTSTRAP_ROUTE)
    _require_status(response, _SUCCESS_STATUS_CODE, context="Bootstrap")
    data = _envelope_data(response, context="Bootstrap")
    _ = _required_string(data, "csrf_token", context="Bootstrap")
    validation = _required_mapping(data, "config_validation", context="Bootstrap")
    if require_valid_config and (validation.get("valid") is not True or validation.get("errors") != []):
        msg = f"Packaged Bootstrap reported Config recovery errors: {validation}"
        raise WindowsPackageSmokeError(msg)
    return data


def _envelope_data(response: HttpResponse, *, context: str) -> dict[str, object]:
    payload = _json_object(response.body, context=context)
    if payload.get("errors") != []:
        msg = f"{context} returned API errors: {payload.get('errors')}"
        raise WindowsPackageSmokeError(msg)
    return _required_mapping(payload, "data", context=context)


def _first_error_code(response: HttpResponse, *, context: str) -> str:
    payload = _json_object(response.body, context=context)
    errors = payload.get("errors")
    if not isinstance(errors, list):
        msg = f"{context} did not return one structured API error: {errors}"
        raise WindowsPackageSmokeError(msg)
    error_values = cast("list[object]", errors)
    if len(error_values) != 1 or not isinstance(error_values[0], dict):
        msg = f"{context} did not return one structured API error: {errors}"
        raise WindowsPackageSmokeError(msg)
    return _required_string(cast("dict[str, object]", error_values[0]), "code", context=context)


def _json_object(body: bytes, *, context: str) -> dict[str, object]:
    try:
        payload = cast("object", json.loads(body))
    except json.JSONDecodeError as exc:
        msg = f"{context} did not return valid JSON."
        raise WindowsPackageSmokeError(msg) from exc
    if not isinstance(payload, dict):
        msg = f"{context} did not return a JSON object."
        raise WindowsPackageSmokeError(msg)
    return cast("dict[str, object]", payload)


def _required_mapping(value: Mapping[str, object], key: str, *, context: str) -> dict[str, object]:
    field = value.get(key)
    if not isinstance(field, dict):
        msg = f"{context} has no object field {key!r}."
        raise WindowsPackageSmokeError(msg)
    return cast("dict[str, object]", field)


def _required_string(value: Mapping[str, object], key: str, *, context: str) -> str:
    field = value.get(key)
    if not isinstance(field, str) or not field:
        msg = f"{context} has no non-empty string field {key!r}."
        raise WindowsPackageSmokeError(msg)
    return field


def _required_string_sequence(value: Mapping[str, object], key: str, *, context: str) -> tuple[str, ...]:
    field = value.get(key)
    if not isinstance(field, list):
        msg = f"{context} has no non-empty string array field {key!r}."
        raise WindowsPackageSmokeError(msg)
    items = cast("list[object]", field)
    if any(not isinstance(item, str) or not item for item in items):
        msg = f"{context} has no non-empty string array field {key!r}."
        raise WindowsPackageSmokeError(msg)
    return tuple(cast("list[str]", items))


def _require_status(response: HttpResponse, expected: int, *, context: str) -> None:
    if response.status != expected:
        msg = f"{context} returned HTTP {response.status}, expected {expected}: {response.body!r}"
        raise WindowsPackageSmokeError(msg)


def _request_loopback(
    base_url: str,
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    headers: Mapping[str, str] | None = None,
) -> HttpResponse:
    parsed = urlsplit(base_url)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port is None:
        msg = f"Packaged base URL is not loopback HTTP: {base_url!r}"
        raise WindowsPackageSmokeError(msg)
    if not path.startswith("/"):
        msg = f"Packaged request path is not absolute: {path!r}"
        raise WindowsPackageSmokeError(msg)
    connection = http.client.HTTPConnection(
        parsed.hostname,
        parsed.port,
        timeout=config.DESKTOP_WINDOWS_METADATA_TIMEOUT_SECONDS,
    )
    try:
        connection.request(method, path, body=body, headers={} if headers is None else dict(headers))
        response = connection.getresponse()
        response_body = response.read()
        response_headers = {name.casefold(): value for name, value in response.getheaders()}
    except (OSError, http.client.HTTPException, TimeoutError) as exc:
        msg = f"Unable to call packaged route {method} {path}: {exc}"
        raise WindowsPackageSmokeError(msg) from exc
    finally:
        connection.close()
    return HttpResponse(body=response_body, headers=response_headers, status=response.status)


def _require_listener_terminated(base_url: str) -> None:
    parsed = urlsplit(base_url)
    if parsed.hostname is None or parsed.port is None:
        msg = f"Unable to parse packaged listener URL: {base_url!r}"
        raise WindowsPackageSmokeError(msg)
    deadline = time.monotonic() + config.DESKTOP_WINDOWS_SMOKE_SHUTDOWN_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(
                (parsed.hostname, parsed.port),
                timeout=config.DESKTOP_WINDOWS_SMOKE_POLL_INTERVAL_SECONDS,
            ):
                pass
        except OSError:
            return
        time.sleep(config.DESKTOP_WINDOWS_SMOKE_POLL_INTERVAL_SECONDS)
    msg = f"Packaged listener remained reachable after process exit: {base_url}"
    raise WindowsPackageSmokeError(msg)


def _require_long_unicode_paths(local_app_data: Path, extraction_a: Path, extraction_b: Path) -> None:
    paths = (local_app_data.resolve(), extraction_a.resolve(), extraction_b.resolve())
    if not all(config.DESKTOP_WINDOWS_SMOKE_UNICODE_DIRECTORY_NAME in str(path) for path in paths):
        msg = "Native smoke paths do not contain the configured Unicode component."
        raise WindowsPackageSmokeError(msg)
    lengths = [len(str(path)) for path in paths]
    if min(lengths) < config.DESKTOP_WINDOWS_SMOKE_MINIMUM_PATH_CHARACTERS:
        msg = f"Native smoke paths are not sufficiently long: {lengths}"
        raise WindowsPackageSmokeError(msg)
    if max(lengths) > config.DESKTOP_WINDOWS_SMOKE_MAXIMUM_PATH_CHARACTERS:
        msg = f"Native smoke paths exceed the configured path-length ceiling: {lengths}"
        raise WindowsPackageSmokeError(msg)


def _require_mutable_state_outside_bundle(bundle: Path) -> None:
    forbidden = (
        bundle / ".config" / "config.toml",
        bundle / ".data" / "omym2.sqlite3",
        bundle / config.DESKTOP_WINDOWS_CONFIG_RELATIVE_PATH,
        bundle / config.DESKTOP_WINDOWS_DATABASE_RELATIVE_PATH,
    )
    if present := [str(path) for path in forbidden if path.exists()]:
        msg = f"Replaceable application files contain mutable OMYM2 state: {present}"
        raise WindowsPackageSmokeError(msg)


def _delete_application_copy_and_require_state(
    extraction: Path,
    config_file: Path,
    database_file: Path,
    database_sha256: str,
) -> None:
    shutil.rmtree(extraction)
    if extraction.exists():
        msg = f"Replaceable application directory could not be deleted: {extraction}"
        raise WindowsPackageSmokeError(msg)
    if config_file.read_text(encoding="utf-8") != config.DESKTOP_WINDOWS_SMOKE_CONFIG_MARKER:
        msg = "Mutable Config state was damaged while deleting a replaceable application copy."
        raise WindowsPackageSmokeError(msg)
    if not database_file.is_file() or _file_sha256(database_file) != database_sha256:
        msg = "SQLite state was damaged while deleting a replaceable application copy."
        raise WindowsPackageSmokeError(msg)


def _write_valid_smoke_config(local_app_data: Path) -> Path:
    config_file = local_app_data / config.DESKTOP_WINDOWS_CONFIG_RELATIVE_PATH
    config_file.parent.mkdir(parents=True, exist_ok=True)
    _ = config_file.write_text(
        config.DESKTOP_WINDOWS_SMOKE_CONFIG_MARKER,
        encoding="utf-8",
        newline="\n",
    )
    return config_file


def _packaged_environment(local_app_data: Path) -> dict[str, str]:
    environment = os.environ.copy()
    for name in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"):
        _ = environment.pop(name, None)
    no_runtime_tools = local_app_data.parent / "no-python-or-node-runtime"
    no_runtime_tools.mkdir(exist_ok=True)
    environment.update(
        {
            "LOCALAPPDATA": str(local_app_data),
            "PATH": str(no_runtime_tools),
            "PYTHONNOUSERSITE": "1",
            "PYTHONSAFEPATH": "1",
        }
    )
    return environment


def _read_appended_log(log_file: Path, offset: int) -> bytes:
    try:
        payload = log_file.read_bytes()
    except FileNotFoundError:
        return b""
    except OSError as exc:
        msg = f"Unable to read packaged desktop log {log_file}: {exc}"
        raise WindowsPackageSmokeError(msg) from exc
    return payload[offset:]


def _require_process_running(process: subprocess.Popen[bytes], phase: str) -> None:
    if (exit_code := process.poll()) is not None:
        msg = f"Packaged GUI exited with status {exit_code} during {phase}."
        raise WindowsPackageSmokeError(msg)


def _directory_size(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def _file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _tree_snapshot(root: Path) -> tuple[tuple[str, str, int, str], ...]:
    if root.is_symlink() or not root.is_dir():
        msg = f"Native smoke tree root is not a directory: {root}"
        raise WindowsPackageSmokeError(msg)
    entries: list[tuple[str, str, int, str]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative_path = path.relative_to(root).as_posix()
        if path.is_symlink():
            entries.append((relative_path, "symlink", 0, str(path.readlink())))
        elif path.is_dir():
            entries.append((relative_path, "directory", 0, ""))
        elif path.is_file():
            entries.append((relative_path, "file", path.stat().st_size, _file_sha256(path)))
        else:
            msg = f"Native smoke tree contains an unsupported entry: {path}"
            raise WindowsPackageSmokeError(msg)
    return tuple(entries)


def _tree_snapshot_sha256(snapshot: tuple[tuple[str, str, int, str], ...]) -> str:
    payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _require_tree_unchanged(
    root: Path,
    expected: tuple[tuple[str, str, int, str], ...],
    *,
    context: str,
) -> None:
    """Reject persistent writes anywhere in a protected smoke directory."""
    if _tree_snapshot(root) != expected:
        msg = f"Packaged application changed the protected {context}."
        raise WindowsPackageSmokeError(msg)


def _write_json_atomically(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        _ = temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        _ = temporary.replace(path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        msg = f"Unable to write native smoke evidence {path}: {exc}"
        raise WindowsPackageSmokeError(msg) from exc


def _project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    msg = "Unable to locate the project root."
    raise WindowsPackageSmokeError(msg)


def _parse_args(argv: Sequence[str] | None) -> ParsedArgs:
    root = _project_root()
    default_icon = root / config.DESKTOP_WINDOWS_ICON_RELATIVE_PATH
    default_version = root / config.DESKTOP_WINDOWS_VERSION_RELATIVE_PATH
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--archive", type=Path, required=True)
    _ = parser.add_argument("--wheel", type=Path, required=True)
    _ = parser.add_argument("--evidence", type=Path)
    _ = parser.add_argument("--icon", type=Path, default=default_icon)
    _ = parser.add_argument("--previous-archive", type=Path)
    _ = parser.add_argument("--previous-wheel", type=Path)
    _ = parser.add_argument("--version-info", type=Path, default=default_version)
    return parser.parse_args(argv, namespace=ParsedArgs(icon=default_icon, version_info=default_version))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the real Windows native package smoke and report its evidence path."""
    args = _parse_args(argv)
    evidence_path = (
        args.archive.with_name(f"{args.archive.stem}-smoke.json") if args.evidence is None else args.evidence
    )
    try:
        previous_artifact = _optional_artifact_input(args.previous_archive, args.previous_wheel)
        smoke_windows_package(
            WindowsArtifactInput(archive=args.archive, wheel=args.wheel),
            evidence_path,
            args.icon,
            args.version_info,
            previous_artifact=previous_artifact,
        )
    except (
        OSError,
        PackageSmokeError,
        WindowsPackageAuditError,
        WindowsPackageBuildError,
        WindowsPackageSmokeError,
    ) as exc:
        print(f"Windows package smoke failed: {exc}", file=sys.stderr)
        return 1
    print(f"Windows package smoke passed: {evidence_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
