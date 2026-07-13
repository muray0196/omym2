"""
Summary: Tests bundled Web static synchronization and content auditing scripts.
Why: Prevents ignored package assets from retaining stale or CSP-unsafe output.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT_NOT_FOUND_MESSAGE = "Unable to locate project root from test file."
SYNC_SCRIPT_RELATIVE_PATH = "scripts/web/sync_web_static.py"
AUDIT_SCRIPT_RELATIVE_PATH = "scripts/web/audit_web_static.py"
VALID_INDEX_HTML = """<!doctype html>
<html lang="en">
  <head><link rel="stylesheet" href="/assets/app-abcdefgh.css"></head>
  <body>
    <img src="/assets/icon-abcdefgh.svg" alt="">
    <script type="module" src="/assets/app-abcdefgh.js"></script>
  </body>
</html>
"""


def test_static_sync_completely_replaces_destination_and_audit_passes(tmp_path: Path) -> None:
    """A staged Vite export removes stale package files and remains byte-identical."""
    source = tmp_path / "dist"
    destination = tmp_path / "static_dist"
    _write_valid_export(source)
    destination.mkdir()
    stale_file = destination / "stale.js"
    _ = stale_file.write_text("stale", encoding="utf-8")

    sync_result = _run_script(SYNC_SCRIPT_RELATIVE_PATH, "--source", str(source), "--destination", str(destination))
    audit_result = _run_script(
        AUDIT_SCRIPT_RELATIVE_PATH,
        "--source",
        str(source),
        "--destination",
        str(destination),
    )

    assert sync_result.returncode == 0, sync_result.stderr
    assert audit_result.returncode == 0, audit_result.stderr
    assert not stale_file.exists()
    assert (destination / "index.html").read_bytes() == (source / "index.html").read_bytes()


def test_static_audit_rejects_changed_packaged_content(tmp_path: Path) -> None:
    """An ignored destination file cannot drift from the current Vite build."""
    source = tmp_path / "dist"
    destination = tmp_path / "static_dist"
    _write_valid_export(source)
    sync_result = _run_script(SYNC_SCRIPT_RELATIVE_PATH, "--source", str(source), "--destination", str(destination))
    assert sync_result.returncode == 0, sync_result.stderr
    _ = (destination / "assets/app-abcdefgh.js").write_text("changed", encoding="utf-8")

    result = _run_script(
        AUDIT_SCRIPT_RELATIVE_PATH,
        "--source",
        str(source),
        "--destination",
        str(destination),
    )

    assert result.returncode != 0
    assert "content differs" in result.stderr


def test_static_audit_rejects_inline_style_attributes(tmp_path: Path) -> None:
    """The export cannot bypass the frozen CSP through inline style attributes."""
    source = tmp_path / "dist"
    destination = tmp_path / "static_dist"
    _write_valid_export(source)
    unsafe_index = VALID_INDEX_HTML.replace("<body>", '<body style="color: white">')
    _ = (source / "index.html").write_text(unsafe_index, encoding="utf-8")
    sync_result = _run_script(SYNC_SCRIPT_RELATIVE_PATH, "--source", str(source), "--destination", str(destination))
    assert sync_result.returncode == 0, sync_result.stderr

    result = _run_script(
        AUDIT_SCRIPT_RELATIVE_PATH,
        "--source",
        str(source),
        "--destination",
        str(destination),
    )

    assert result.returncode != 0
    assert "inline style attribute" in result.stderr


def test_static_audit_allows_react_error_documentation_prefix(tmp_path: Path) -> None:
    """React's inert diagnostic URL is not mistaken for a remote runtime request."""
    source = tmp_path / "dist"
    destination = tmp_path / "static_dist"
    _write_valid_export(source)
    _ = (source / "assets/app-abcdefgh.js").write_text(
        'const help = "https://react.dev/errors/" + 418;',
        encoding="utf-8",
    )
    sync_result = _run_script(SYNC_SCRIPT_RELATIVE_PATH, "--source", str(source), "--destination", str(destination))

    result = _run_script(
        AUDIT_SCRIPT_RELATIVE_PATH,
        "--source",
        str(source),
        "--destination",
        str(destination),
    )

    assert sync_result.returncode == 0, sync_result.stderr
    assert result.returncode == 0, result.stderr


def test_static_audit_rejects_remote_javascript_request(tmp_path: Path) -> None:
    """A built script cannot issue a request to a remote runtime endpoint."""
    source = tmp_path / "dist"
    destination = tmp_path / "static_dist"
    _write_valid_export(source)
    _ = (source / "assets/app-abcdefgh.js").write_text(
        'fetch("https://example.com/data");',
        encoding="utf-8",
    )
    sync_result = _run_script(SYNC_SCRIPT_RELATIVE_PATH, "--source", str(source), "--destination", str(destination))

    result = _run_script(
        AUDIT_SCRIPT_RELATIVE_PATH,
        "--source",
        str(source),
        "--destination",
        str(destination),
    )

    assert sync_result.returncode == 0, sync_result.stderr
    assert result.returncode != 0
    assert "remote URL" in result.stderr


def test_static_audit_rejects_inline_script_outside_index(tmp_path: Path) -> None:
    """A secondary markup asset cannot hide a CSP-blocked inline script."""
    source = tmp_path / "dist"
    destination = tmp_path / "static_dist"
    _write_valid_export(source)
    _ = (source / "assets/unsafe-abcdefgh.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        encoding="utf-8",
    )
    sync_result = _run_script(SYNC_SCRIPT_RELATIVE_PATH, "--source", str(source), "--destination", str(destination))

    result = _run_script(
        AUDIT_SCRIPT_RELATIVE_PATH,
        "--source",
        str(source),
        "--destination",
        str(destination),
    )

    assert sync_result.returncode == 0, sync_result.stderr
    assert result.returncode != 0
    assert "inline script" in result.stderr


def test_static_audit_rejects_server_artifacts_and_unexpected_locations(tmp_path: Path) -> None:
    """Only the narrow Vite runtime and license tree may enter the package."""
    source = tmp_path / "dist"
    destination = tmp_path / "static_dist"
    _write_valid_export(source)
    _ = (source / "server.py").write_text("raise SystemExit", encoding="utf-8")
    sync_result = _run_script(SYNC_SCRIPT_RELATIVE_PATH, "--source", str(source), "--destination", str(destination))

    result = _run_script(
        AUDIT_SCRIPT_RELATIVE_PATH,
        "--source",
        str(source),
        "--destination",
        str(destination),
    )

    assert sync_result.returncode == 0, sync_result.stderr
    assert result.returncode != 0
    assert "unexpected file location or type" in result.stderr


def test_static_audit_scans_license_text_for_secret_markers(tmp_path: Path) -> None:
    """The license exception never becomes an unchecked secret-text channel."""
    source = tmp_path / "dist"
    destination = tmp_path / "static_dist"
    _write_valid_export(source)
    _ = (source / "licenses/Inter.txt").write_text("BEGIN PRIVATE KEY", encoding="utf-8")
    sync_result = _run_script(SYNC_SCRIPT_RELATIVE_PATH, "--source", str(source), "--destination", str(destination))

    result = _run_script(
        AUDIT_SCRIPT_RELATIVE_PATH,
        "--source",
        str(source),
        "--destination",
        str(destination),
    )

    assert sync_result.returncode == 0, sync_result.stderr
    assert result.returncode != 0
    assert "BEGIN PRIVATE KEY" in result.stderr


def test_static_audit_rejects_asset_names_the_server_cannot_serve(tmp_path: Path) -> None:
    """Audited asset names use the same final-hyphen hash form as production serving."""
    source = tmp_path / "dist"
    destination = tmp_path / "static_dist"
    _write_valid_export(source)
    _ = (source / "assets/extra.abcdefgh.js").write_text("export {};", encoding="utf-8")
    sync_result = _run_script(SYNC_SCRIPT_RELATIVE_PATH, "--source", str(source), "--destination", str(destination))

    result = _run_script(
        AUDIT_SCRIPT_RELATIVE_PATH,
        "--source",
        str(source),
        "--destination",
        str(destination),
    )

    assert sync_result.returncode == 0, sync_result.stderr
    assert result.returncode != 0
    assert "unhashed asset" in result.stderr


def _write_valid_export(root: Path) -> None:
    assets = root / "assets"
    licenses = root / "licenses"
    assets.mkdir(parents=True)
    licenses.mkdir()
    _ = (root / "index.html").write_text(VALID_INDEX_HTML, encoding="utf-8")
    _ = (assets / "app-abcdefgh.css").write_text("body { color: #f4f4f6; }", encoding="utf-8")
    _ = (assets / "app-abcdefgh.js").write_text("globalThis.OMYM2 = true;", encoding="utf-8")
    _ = (assets / "icon-abcdefgh.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0h1v1z"/></svg>',
        encoding="utf-8",
    )
    _ = (assets / "inter-abcdefgh.woff2").write_bytes(b"test-font")
    _ = (assets / "jetbrains-mono-abcdefgh.woff2").write_bytes(b"test-mono-font")
    _ = (licenses / "Inter.txt").write_text("Inter test license", encoding="utf-8")
    _ = (licenses / "Inter-OFL.txt").write_text("Inter test license", encoding="utf-8")
    _ = (licenses / "JetBrains-Mono-OFL.txt").write_text("JetBrains test license", encoding="utf-8")


def _run_script(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- fixed argv invokes this repository's own script.
        (sys.executable, script, *args),
        cwd=_project_root(),
        capture_output=True,
        text=True,
        check=False,
    )


def _project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError(PROJECT_ROOT_NOT_FOUND_MESSAGE)
