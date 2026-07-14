"""
Summary: Tests native-smoke path and mutable-state boundary helpers without opening a window.
Why: Keeps upgrade, Unicode, long-path, and external-state assertions platform-independent.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from omym2.adapters.desktop.server import UvicornDesktopServer
from omym2.platform.web_composition import build_web_app
from scripts import config
from scripts.desktop import smoke_windows_package as desktop_smoke
from scripts.desktop.audit_windows_package import WindowsPackageAudit
from scripts.desktop.smoke_windows_package import (
    _POWERSHELL_UTF8_PREAMBLE,  # pyright: ignore[reportPrivateUsage] -- protects localized output decoding.
    AuditedWindowsArtifact,
    NativeLaunchContext,
    WindowsPackageSmokeError,
    _artifact_transition_evidence,  # pyright: ignore[reportPrivateUsage] -- verifies retained artifact identity.
    _bootstrap_data,  # pyright: ignore[reportPrivateUsage] -- simulates the UI-backed request boundary.
    _create_safe_add_plan,  # pyright: ignore[reportPrivateUsage] -- directly verifies retained package flow.
    _delete_application_copy_and_require_state,  # pyright: ignore[reportPrivateUsage] -- verifies upgrade cleanup.
    _loaded_webview_backend,  # pyright: ignore[reportPrivateUsage] -- verifies exact log ordering.
    _optional_artifact_input,  # pyright: ignore[reportPrivateUsage] -- validates optional CLI pairing.
    _require_long_unicode_paths,  # pyright: ignore[reportPrivateUsage] -- verifies native path inputs.
    _require_mutable_state_outside_bundle,  # pyright: ignore[reportPrivateUsage] -- verifies state isolation.
    _require_tree_unchanged,  # pyright: ignore[reportPrivateUsage] -- protects the dedicated launch cwd.
    _retain_native_launch_failure,  # pyright: ignore[reportPrivateUsage] -- verifies retained failure evidence.
    _run_native_ui_automation,  # pyright: ignore[reportPrivateUsage] -- verifies the PowerShell contract boundary.
    _run_powershell,  # pyright: ignore[reportPrivateUsage] -- verifies timeout error translation.
    _start_and_poll_operation,  # pyright: ignore[reportPrivateUsage] -- simulates a successful native UI action.
    _start_native_process,  # pyright: ignore[reportPrivateUsage] -- verifies long-path process creation.
    _tree_snapshot,  # pyright: ignore[reportPrivateUsage] -- snapshots the protected launch cwd.
    _verify_persisted_plan_and_create_through_native_ui,  # pyright: ignore[reportPrivateUsage] -- checks evidence.
    _wait_for_ready_url,  # pyright: ignore[reportPrivateUsage] -- verifies fatal startup detection.
    _write_tagged_smoke_flac,  # pyright: ignore[reportPrivateUsage] -- verifies the packaged planning fixture.
)

if TYPE_CHECKING:
    from collections.abc import Mapping


def _native_ui_payload() -> dict[str, object]:
    return {
        "add_source_value_verified": True,
        "automation_framework": "Microsoft UI Automation",
        "deep_routes": ["/plans/new/add", "/plans/:planId"],
        "overview_action": config.DESKTOP_WINDOWS_SMOKE_UI_OVERVIEW_ACTION[0],
        "overview_interactive": True,
        "plan_detail_loaded": True,
        "plan_submit_action": config.DESKTOP_WINDOWS_SMOKE_UI_ADD_ACTIONS[2],
        "primary_navigation_routes": [
            route for route, _link, _heading in config.DESKTOP_WINDOWS_SMOKE_UI_PRIMARY_NAVIGATION
        ],
        "root_automation_id": config.DESKTOP_WINDOWS_SMOKE_UI_ROOT_AUTOMATION_ID,
        "settings_editor_automation_id": config.DESKTOP_WINDOWS_SMOKE_UI_SETTINGS_AUTOMATION_ID,
        "settings_loaded": True,
    }


def _package_audit(
    *,
    artifact_sha256: str,
    artifact_payload_sha256: str | None = None,
    package_version: str = "0.1.0",
) -> WindowsPackageAudit:
    return WindowsPackageAudit(
        artifact_sha256=artifact_sha256,
        artifact_payload_sha256=(artifact_sha256 if artifact_payload_sha256 is None else artifact_payload_sha256),
        artifact_size_bytes=1,
        archive_file_count=1,
        package_version=package_version,
        pe_machine="x86_64",
        pe_subsystem="windows_gui",
        runtime_distribution_count=1,
        runtime_license_file_count=1,
        verified_resource_count=1,
        webview_dll_count=0,
        webview_modules=("webview.platforms.edgechromium",),
        wheel_sha256="wheel-sha256",
    )


def _audited_artifact(
    tmp_path: Path,
    build_name: str,
    artifact_sha256: str,
) -> AuditedWindowsArtifact:
    archive = tmp_path / build_name / "OMYM2-0.1.0-windows-x86_64.zip"
    wheel = tmp_path / "omym2-0.1.0-py3-none-any.whl"
    return AuditedWindowsArtifact(
        archive=archive,
        audit=_package_audit(artifact_sha256=artifact_sha256),
        wheel=wheel,
    )


def test_artifact_transition_records_distinct_same_version_builds(tmp_path: Path) -> None:
    """Cross-build evidence retains both audited identities without claiming a version migration."""
    first = _audited_artifact(tmp_path, "build-a", "first")
    second = _audited_artifact(tmp_path, "build-b", "second")

    evidence = _artifact_transition_evidence(
        first,
        second,
        require_distinct=True,
    )

    assert evidence["kind"] == "cross_build_same_package_version"
    assert evidence["archive_sha256_changed"] is True
    assert evidence["payload_sha256_changed"] is True
    assert evidence["package_version_changed"] is False
    assert evidence["shared_local_app_data"] is True
    assert evidence["from"] == {
        "archive_filename": first.archive.name,
        "archive_sha256": "first",
        "payload_sha256": "first",
        "package_version": "0.1.0",
        "wheel_filename": first.wheel.name,
        "wheel_sha256": "wheel-sha256",
    }


def test_artifact_transition_rejects_identical_payload_as_cross_build_evidence(tmp_path: Path) -> None:
    """Supplying previous-build inputs cannot relabel the same payload as an upgrade."""
    artifact = _audited_artifact(tmp_path, "same-build", "same")

    with pytest.raises(WindowsPackageSmokeError, match="identical payloads"):
        _ = _artifact_transition_evidence(
            artifact,
            artifact,
            require_distinct=True,
        )


def test_artifact_transition_labels_same_archive_relaunch_honestly(tmp_path: Path) -> None:
    """The default two-copy smoke remains replacement evidence, not cross-build evidence."""
    artifact = _audited_artifact(tmp_path, "same-build", "same")

    evidence = _artifact_transition_evidence(
        artifact,
        artifact,
        require_distinct=False,
    )

    assert evidence["kind"] == "same_artifact_relaunch"
    assert evidence["archive_sha256_changed"] is False
    assert evidence["payload_sha256_changed"] is False


def test_artifact_transition_rejects_repacked_identical_payload(tmp_path: Path) -> None:
    """Different ZIP container bytes do not prove a different frozen application build."""
    first = _audited_artifact(tmp_path, "build-a", "first-container")
    second = AuditedWindowsArtifact(
        archive=tmp_path / "build-b" / first.archive.name,
        audit=_package_audit(
            artifact_sha256="second-container",
            artifact_payload_sha256=first.audit.artifact_payload_sha256,
        ),
        wheel=first.wheel,
    )

    with pytest.raises(WindowsPackageSmokeError, match="identical payloads"):
        _ = _artifact_transition_evidence(first, second, require_distinct=True)


def test_artifact_transition_rejects_cross_version_without_migration_contract(tmp_path: Path) -> None:
    """A version change cannot acquire migration evidence through the same-version smoke contract."""
    first = _audited_artifact(tmp_path, "build-a", "first")
    second = AuditedWindowsArtifact(
        archive=tmp_path / "build-b" / "OMYM2-0.2.0-windows-x86_64.zip",
        audit=_package_audit(artifact_sha256="second", package_version="0.2.0"),
        wheel=tmp_path / "omym2-0.2.0-py3-none-any.whl",
    )

    with pytest.raises(WindowsPackageSmokeError, match="explicit migration contract"):
        _ = _artifact_transition_evidence(first, second, require_distinct=True)


@pytest.mark.parametrize("missing", ["archive", "wheel"])
def test_previous_build_inputs_require_archive_and_wheel(tmp_path: Path, missing: str) -> None:
    """A partial previous-build identity cannot reach native artifact auditing."""
    archive = None if missing == "archive" else tmp_path / "previous.zip"
    wheel = None if missing == "wheel" else tmp_path / "previous.whl"

    with pytest.raises(WindowsPackageSmokeError, match="both --previous-archive and --previous-wheel"):
        _ = _optional_artifact_input(archive, wheel)


def test_previous_build_inputs_accept_complete_or_absent_pair(tmp_path: Path) -> None:
    """The CLI boundary distinguishes the default relaunch from explicit cross-build smoke."""
    archive = tmp_path / "previous.zip"
    wheel = tmp_path / "previous.whl"

    assert _optional_artifact_input(None, None) is None
    artifact = _optional_artifact_input(archive, wheel)
    assert artifact is not None
    assert artifact.archive == archive
    assert artifact.wheel == wheel


def test_native_smoke_accepts_unicode_paths_beyond_legacy_max_path(tmp_path: Path) -> None:
    """Both application generations and LOCALAPPDATA exceed legacy MAX_PATH with Unicode."""
    component = "x" * config.DESKTOP_WINDOWS_SMOKE_LONG_COMPONENT_CHARACTERS
    root = tmp_path / config.DESKTOP_WINDOWS_SMOKE_UNICODE_DIRECTORY_NAME
    for index in range(config.DESKTOP_WINDOWS_SMOKE_LONG_COMPONENT_COUNT):
        root /= f"{index}-{component}"
    local_app_data = root / "local-app-data"
    extraction_a = root / "application-build-a"
    extraction_b = root / "application-build-b"

    _require_long_unicode_paths(local_app_data, extraction_a, extraction_b)

    assert min(len(str(path.resolve())) for path in (local_app_data, extraction_a, extraction_b)) >= (
        config.DESKTOP_WINDOWS_SMOKE_MINIMUM_PATH_CHARACTERS
    )


def test_native_process_launch_does_not_force_long_child_working_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fully qualified long executable is explicit while the child cwd remains short."""
    executable_directory = tmp_path
    component_index = 0
    while len(str((executable_directory / config.DESKTOP_WINDOWS_EXECUTABLE_NAME).resolve())) <= (
        config.DESKTOP_WINDOWS_SMOKE_MINIMUM_PATH_CHARACTERS
    ):
        executable_directory /= f"component-{component_index:02d}-xxxxxxxxxxxxxxxx"
        component_index += 1
    executable = executable_directory / config.DESKTOP_WINDOWS_EXECUTABLE_NAME
    executable.parent.mkdir(parents=True)
    _ = executable.write_bytes(b"native executable")
    observed: list[tuple[tuple[object, ...], dict[str, object]]] = []
    sentinel = object()

    def fake_popen(*arguments: object, **keywords: object) -> object:
        observed.append((arguments, keywords))
        return sentinel

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    stdout_file = tmp_path / "stdout.log"
    stderr_file = tmp_path / "stderr.log"
    with stdout_file.open("wb") as stdout_stream, stderr_file.open("wb") as stderr_stream:
        assert (
            _start_native_process(
                executable,
                tmp_path,
                {"LOCALAPPDATA": str(tmp_path)},
                stdout_stream,
                stderr_stream,
            )
            is sentinel
        )
    arguments, keywords = observed[0]
    executable_path = str(executable.resolve())
    assert len(executable_path) > config.DESKTOP_WINDOWS_SMOKE_MINIMUM_PATH_CHARACTERS
    assert arguments == ((executable_path,),)
    assert keywords["executable"] == executable_path
    assert keywords["cwd"] == str(tmp_path.resolve())
    assert keywords["stdout"] is stdout_stream
    assert keywords["stderr"] is stderr_stream


def test_native_smoke_rejects_relative_state_in_launch_working_directory(tmp_path: Path) -> None:
    """An accidental relative Config, database, log, or sidecar makes native evidence fail."""
    launch_working_directory = tmp_path / "launch-cwd"
    launch_working_directory.mkdir()
    expected = _tree_snapshot(launch_working_directory)
    (launch_working_directory / ".data").mkdir()
    _ = (launch_working_directory / ".data" / "omym2.sqlite3").write_bytes(b"stray state")

    with pytest.raises(WindowsPackageSmokeError, match="protected native launch working directory"):
        _require_tree_unchanged(
            launch_working_directory,
            expected,
            context="native launch working directory",
        )


def test_native_process_launch_rejects_overlong_child_working_directory(tmp_path: Path) -> None:
    """The smoke rejects an unsupported long cwd before asking CreateProcessW to launch."""
    executable = tmp_path / config.DESKTOP_WINDOWS_EXECUTABLE_NAME
    _ = executable.write_bytes(b"native executable")
    working_directory = tmp_path
    component_index = 0
    while len(str(working_directory.resolve())) <= config.DESKTOP_WINDOWS_SMOKE_MAXIMUM_LAUNCH_CWD_CHARACTERS:
        working_directory /= f"component-{component_index:02d}-xxxxxxxxxxxxxxxx"
        component_index += 1
    working_directory.mkdir(parents=True)

    stdout_file = tmp_path / "stdout.log"
    stderr_file = tmp_path / "stderr.log"
    with (
        stdout_file.open("wb") as stdout_stream,
        stderr_file.open("wb") as stderr_stream,
        pytest.raises(WindowsPackageSmokeError, match="exceeds the safe CreateProcessW limit"),
    ):
        _ = _start_native_process(executable, working_directory, {}, stdout_stream, stderr_stream)


def test_native_readiness_fails_immediately_on_desktop_fatal_log(tmp_path: Path) -> None:
    """A modal startup failure is reported from its log instead of becoming a readiness timeout."""

    class RunningProcess:
        def poll(self) -> None:
            return None

    log_file = tmp_path / "omym2-desktop.log"
    _ = log_file.write_text(
        f"level=ERROR {config.DESKTOP_WINDOWS_FAILURE_LOG_MARKER}\ntraceback",
        encoding="utf-8",
    )
    process = cast("subprocess.Popen[bytes]", cast("object", RunningProcess()))

    with pytest.raises(WindowsPackageSmokeError, match="fatal startup failure"):
        _ = _wait_for_ready_url(process, log_file, 0)


def test_native_launch_failure_retains_bounded_process_and_desktop_logs(tmp_path: Path) -> None:
    """A failing GUI leaves an artifact summary containing each otherwise hidden diagnostic stream."""
    diagnostics = tmp_path / "diagnostics"
    diagnostics.mkdir()
    desktop_log = tmp_path / "desktop.log"
    stdout_file = diagnostics / "first-launch-stdout.log"
    stderr_file = diagnostics / "first-launch-stderr.log"
    prefix = "x" * config.DESKTOP_WINDOWS_SMOKE_DIAGNOSTIC_TAIL_BYTES
    _ = desktop_log.write_text(prefix + "desktop-tail", encoding="utf-8")
    _ = stdout_file.write_text("stdout-tail", encoding="utf-8")
    _ = stderr_file.write_text("stderr-tail", encoding="utf-8")

    message = _retain_native_launch_failure(
        WindowsPackageSmokeError("startup failed"),
        NativeLaunchContext(
            diagnostic_directory=diagnostics,
            executable=tmp_path / config.DESKTOP_WINDOWS_EXECUTABLE_NAME,
            launch_name="first-launch",
            launch_working_directory=tmp_path,
            local_app_data=tmp_path,
            log_file=desktop_log,
        ),
    )

    assert "startup failed" in message
    assert "desktop-tail" in message
    assert "stdout-tail" in message
    assert "stderr-tail" in message
    assert prefix not in message
    assert (diagnostics / "first-launch-desktop.log").read_text(encoding="utf-8").endswith("desktop-tail")
    assert (diagnostics / "first-launch-failure.txt").read_text(encoding="utf-8") == message + "\n"


def test_windows_desktop_workflow_propagates_smoke_failure_and_uploads_diagnostics() -> None:
    """The Windows job preserves the smoke exit code and still uploads retained diagnostics."""
    workflow = (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    native_step = workflow.split("- name: Build and smoke native desktop archive", maxsplit=1)[1].split(
        "- name: Upload native desktop evidence and diagnostics", maxsplit=1
    )[0]
    upload_step = workflow.split("- name: Upload native desktop evidence and diagnostics", maxsplit=1)[1]

    expected_native_failure_checks = 2
    assert native_step.count("if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }") == expected_native_failure_checks
    assert "if: ${{ !cancelled() }}" in upload_step
    assert "build/desktop/*-diagnostics/**" in upload_step
    assert "if-no-files-found: warn" in upload_step


def test_native_smoke_rejects_mutable_database_inside_replaceable_bundle(tmp_path: Path) -> None:
    """Upgrade smoke fails if SQLite state appears under extracted application files."""
    database = tmp_path / ".data" / "omym2.sqlite3"
    database.parent.mkdir()
    _ = database.write_bytes(b"state")

    with pytest.raises(WindowsPackageSmokeError, match="mutable OMYM2 state"):
        _require_mutable_state_outside_bundle(tmp_path)


def test_native_smoke_deletes_each_application_copy_without_deleting_state(tmp_path: Path) -> None:
    """Explicit copy cleanup preserves the valid Config marker and exact SQLite bytes."""
    extraction = tmp_path / "replaceable-application"
    extraction.mkdir()
    _ = (extraction / "OMYM2.exe").write_bytes(b"application")
    config_file = tmp_path / "local-app-data" / "config.toml"
    database_file = tmp_path / "local-app-data" / "omym2.sqlite3"
    config_file.parent.mkdir()
    _ = config_file.write_text(config.DESKTOP_WINDOWS_SMOKE_CONFIG_MARKER, encoding="utf-8")
    _ = database_file.write_bytes(b"durable state")
    database_sha256 = hashlib.sha256(database_file.read_bytes()).hexdigest()

    _delete_application_copy_and_require_state(extraction, config_file, database_file, database_sha256)

    assert not extraction.exists()
    assert tomllib.loads(config_file.read_text(encoding="utf-8"))["version"] == 1
    assert database_file.is_file()


def test_native_smoke_requires_edgechromium_initialization_before_content_loaded() -> None:
    """A loaded callback is accepted only after the exact guarded renderer marker."""
    initialized = config.DESKTOP_WINDOWS_WEBVIEW_INITIALIZED_LOG_MARKER.encode()
    loaded = config.DESKTOP_WINDOWS_WEBVIEW_LOADED_LOG_MARKER.encode()

    assert _loaded_webview_backend(initialized + b"\n" + loaded) == "edgechromium"
    assert _loaded_webview_backend(initialized) is None
    with pytest.raises(WindowsPackageSmokeError, match="without exact prior EdgeChromium"):
        _ = _loaded_webview_backend(loaded)


def test_packaged_api_probe_creates_non_destructive_add_plan(tmp_path: Path) -> None:
    """The retained native-smoke API flow creates and reads one real reviewable Plan."""
    library_root = tmp_path / "library"
    incoming_root = tmp_path / "incoming"
    source_file = incoming_root / "smoke-track.flac"
    library_root.mkdir()
    _write_tagged_smoke_flac(source_file)
    server = UvicornDesktopServer(build_web_app(tmp_path / "config.toml", tmp_path / "state.sqlite3"))
    base_url = server.start()
    try:
        evidence = _create_safe_add_plan(base_url, library_root, incoming_root, source_file)
    finally:
        server.stop()

    assert evidence["add_result_kind"] == "plan_created"
    assert evidence["organize_result_kind"] == "registered_without_plan"
    assert evidence["plan_status"] == "ready"
    assert evidence["filesystem_mutation_performed"] is False
    assert isinstance(evidence["incoming_tree_manifest_sha256"], str)
    assert isinstance(evidence["library_tree_manifest_sha256"], str)
    assert source_file.is_file()


@pytest.mark.parametrize(
    ("tree_name", "expected_message"),
    [("incoming", "incoming tree"), ("library", "Library tree")],
)
def test_packaged_api_plan_evidence_rejects_disposable_tree_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tree_name: str,
    expected_message: str,
) -> None:
    """The packaged-API setup Plan also rejects changes anywhere in either music tree."""
    library_root = tmp_path / "library"
    incoming_root = tmp_path / "incoming"
    source_file = incoming_root / "smoke-track.flac"
    library_root.mkdir()
    _write_tagged_smoke_flac(source_file)
    server = UvicornDesktopServer(build_web_app(tmp_path / "config.toml", tmp_path / "state.sqlite3"))
    base_url = server.start()
    original_start = _start_and_poll_operation

    def mutating_start(
        operation_base_url: str,
        route: str,
        body: Mapping[str, object],
        csrf_token: str,
    ) -> tuple[str, dict[str, object]]:
        result = original_start(operation_base_url, route, body, csrf_token)
        if route == "/api/plans/add":
            mutation_root = incoming_root if tree_name == "incoming" else library_root
            _ = (mutation_root / "unexpected-sidecar.txt").write_text("mutation", encoding="utf-8")
        return result

    monkeypatch.setattr(desktop_smoke, "_start_and_poll_operation", mutating_start)
    try:
        with pytest.raises(WindowsPackageSmokeError, match=expected_message):
            _ = _create_safe_add_plan(base_url, library_root, incoming_root, source_file)
    finally:
        server.stop()


def test_native_ui_probe_uses_uia_patterns_and_validates_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Linux-testable boundary passes selectors to a UIA-only script and checks its JSON."""
    calls: list[tuple[str, tuple[str, ...], float]] = []

    def fake_run_powershell(script: str, *arguments: str, timeout: float) -> dict[str, object]:
        calls.append((script, arguments, timeout))
        return _native_ui_payload()

    monkeypatch.setattr(desktop_smoke, "_run_powershell", fake_run_powershell)
    incoming = tmp_path / config.DESKTOP_WINDOWS_SMOKE_UNICODE_DIRECTORY_NAME / "incoming"
    incoming.mkdir(parents=True)

    evidence = _run_native_ui_automation(42, incoming)

    assert evidence == _native_ui_payload()
    assert len(calls) == 1
    script, arguments, timeout = calls[0]
    assert "UIAutomationClient" in script
    assert "AutomationElement]::FromHandle" in script
    assert "InvokePattern" in script
    assert "ValuePattern" in script
    assert "$documentRoot = Wait-ForAutomationId -Root $window" in script
    assert "Invoke-NamedAction -Root $documentRoot" in script
    assert "Set-And-VerifyValue -Root $documentRoot" in script
    assert "remote-debugging" not in script.casefold()
    assert "evaluate_js" not in script
    assert arguments[0] == "42"
    assert arguments[1] == str(incoming.resolve())
    assert int(arguments[2]) == round(config.DESKTOP_WINDOWS_SMOKE_STARTUP_TIMEOUT_SECONDS * 1000)
    assert int(arguments[3]) > 0
    assert int(arguments[4]) == config.DESKTOP_WINDOWS_UIA_ARIA_ROLE_PROPERTY_ID
    assert json.loads(arguments[8]) == [list(item) for item in config.DESKTOP_WINDOWS_SMOKE_UI_PRIMARY_NAVIGATION]
    assert timeout == config.DESKTOP_WINDOWS_SMOKE_UI_AUTOMATION_TIMEOUT_SECONDS


def test_powershell_timeout_uses_native_smoke_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A stalled native probe preserves the smoke CLI's concise domain-error boundary."""

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        command = "powershell.exe"
        raise subprocess.TimeoutExpired(command, 1)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(WindowsPackageSmokeError, match="timed out after 1 seconds"):
        _ = _run_powershell("exit 0", timeout=1)


def test_powershell_probe_forces_utf8_before_localized_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Japanese Windows inventory values must reach the strict UTF-8 decoder intact."""
    observed_commands: list[tuple[str, ...]] = []

    def fake_run(command: tuple[str, ...], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        observed_commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout='{"architecture":"64 bit"}\n', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert _run_powershell("Write-Output '{}'", timeout=1) == {"architecture": "64 bit"}
    assert observed_commands[0][5].startswith(f"{_POWERSHELL_UTF8_PREAMBLE}\n& {{\n")


def test_native_ui_plan_evidence_requires_one_new_ready_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Native evidence is accepted only when its UI action yields one distinct non-mutating Plan."""
    library_root = tmp_path / "library"
    incoming_root = tmp_path / "incoming"
    source_file = incoming_root / "smoke-track.flac"
    library_root.mkdir()
    _write_tagged_smoke_flac(source_file)
    server = UvicornDesktopServer(build_web_app(tmp_path / "config.toml", tmp_path / "state.sqlite3"))
    base_url = server.start()
    try:
        persisted = _create_safe_add_plan(base_url, library_root, incoming_root, source_file)
        library_id = str(persisted["library_id"])

        def fake_native_ui(_window_handle: int, source_root: Path) -> dict[str, object]:
            bootstrap = _bootstrap_data(
                base_url,
                require_valid_config=True,
            )
            _, operation = _start_and_poll_operation(
                base_url,
                "/api/plans/add",
                {"library_id": library_id, "source_path": str(source_root.resolve())},
                str(bootstrap["csrf_token"]),
            )
            assert operation["status"] == "succeeded"
            return _native_ui_payload()

        monkeypatch.setattr(desktop_smoke, "_run_native_ui_automation", fake_native_ui)
        evidence = _verify_persisted_plan_and_create_through_native_ui(
            base_url,
            42,
            persisted,
            library_root,
            source_file,
        )
    finally:
        server.stop()

    native_ui = evidence["native_ui"]
    assert isinstance(native_ui, dict)
    assert native_ui["plan_id"] != persisted["plan_id"]
    assert native_ui["plan_status"] == "ready"
    assert native_ui["filesystem_mutation_performed"] is False
    assert isinstance(native_ui["incoming_tree_manifest_sha256"], str)
    assert isinstance(native_ui["library_tree_manifest_sha256"], str)
    assert source_file.is_file()


@pytest.mark.parametrize(
    ("tree_name", "expected_message"),
    [("incoming", "incoming tree"), ("library", "Library tree")],
)
def test_native_ui_plan_evidence_rejects_disposable_tree_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tree_name: str,
    expected_message: str,
) -> None:
    """Sidecars in either disposable music tree invalidate non-destructive UI evidence."""
    library_root = tmp_path / "library"
    incoming_root = tmp_path / "incoming"
    source_file = incoming_root / "smoke-track.flac"
    library_root.mkdir()
    _write_tagged_smoke_flac(source_file)
    server = UvicornDesktopServer(build_web_app(tmp_path / "config.toml", tmp_path / "state.sqlite3"))
    base_url = server.start()
    try:
        persisted = _create_safe_add_plan(base_url, library_root, incoming_root, source_file)
        library_id = str(persisted["library_id"])

        def fake_native_ui(_window_handle: int, source_root: Path) -> dict[str, object]:
            bootstrap = _bootstrap_data(base_url, require_valid_config=True)
            _, operation = _start_and_poll_operation(
                base_url,
                "/api/plans/add",
                {"library_id": library_id, "source_path": str(source_root.resolve())},
                str(bootstrap["csrf_token"]),
            )
            assert operation["status"] == "succeeded"
            mutation_root = source_root if tree_name == "incoming" else library_root
            _ = (mutation_root / "unexpected-sidecar.txt").write_text("mutation", encoding="utf-8")
            return _native_ui_payload()

        monkeypatch.setattr(desktop_smoke, "_run_native_ui_automation", fake_native_ui)
        with pytest.raises(WindowsPackageSmokeError, match=expected_message):
            _ = _verify_persisted_plan_and_create_through_native_ui(
                base_url,
                42,
                persisted,
                library_root,
                source_file,
            )
    finally:
        server.stop()
