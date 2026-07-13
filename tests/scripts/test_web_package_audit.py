"""
Summary: Tests wheel and source-distribution Web static content auditing.
Why: Ensures declarative package-data metadata cannot hide incomplete artifacts.
"""

from __future__ import annotations

import io
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

PROJECT_ROOT_NOT_FOUND_MESSAGE = "Unable to locate project root from test file."
AUDIT_SCRIPT_RELATIVE_PATH = "scripts/web/audit_web_packages.py"
WHEEL_STATIC_PREFIX = PurePosixPath("omym2/adapters/web/static_dist")
SDIST_STATIC_PREFIX = PurePosixPath("omym2-0.1.0/src/omym2/adapters/web/static_dist")
STATIC_FILES = {
    PurePosixPath("index.html"): b"<!doctype html>",
    PurePosixPath("assets/app-abcdefgh.js"): b"export {};",
    PurePosixPath("licenses/Inter.txt"): b"Inter test license",
}


def test_package_audit_accepts_exact_wheel_and_sdist_static_trees(tmp_path: Path) -> None:
    """Both artifact formats may contain the byte-identical expected export."""
    expected_static = tmp_path / "static_dist"
    wheel = tmp_path / "omym2-0.1.0-py3-none-any.whl"
    sdist = tmp_path / "omym2-0.1.0.tar.gz"
    _write_expected_static(expected_static)
    _write_wheel(wheel, STATIC_FILES)
    _write_sdist(sdist, STATIC_FILES)

    result = _run_audit(wheel, sdist, expected_static)

    assert result.returncode == 0, result.stderr


def test_package_audit_rejects_sdist_missing_static_file(tmp_path: Path) -> None:
    """A source distribution cannot omit an asset required for Node-free rebuilding."""
    expected_static = tmp_path / "static_dist"
    wheel = tmp_path / "omym2-0.1.0-py3-none-any.whl"
    sdist = tmp_path / "omym2-0.1.0.tar.gz"
    _write_expected_static(expected_static)
    _write_wheel(wheel, STATIC_FILES)
    incomplete = {path: content for path, content in STATIC_FILES.items() if path.name != "app-abcdefgh.js"}
    _write_sdist(sdist, incomplete)

    result = _run_audit(wheel, sdist, expected_static)

    assert result.returncode != 0
    assert "sdist static tree differs" in result.stderr
    assert "assets/app-abcdefgh.js" in result.stderr


def test_package_audit_rejects_unsafe_archive_member(tmp_path: Path) -> None:
    """Archive traversal paths fail before package content is trusted."""
    expected_static = tmp_path / "static_dist"
    wheel = tmp_path / "omym2-0.1.0-py3-none-any.whl"
    sdist = tmp_path / "omym2-0.1.0.tar.gz"
    _write_expected_static(expected_static)
    _write_wheel(wheel, STATIC_FILES, unsafe_member="../escape")
    _write_sdist(sdist, STATIC_FILES)

    result = _run_audit(wheel, sdist, expected_static)

    assert result.returncode != 0
    assert "unsafe member path" in result.stderr


def _write_expected_static(root: Path) -> None:
    for relative_path, content in STATIC_FILES.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_bytes(content)


def _write_wheel(wheel: Path, files: dict[PurePosixPath, bytes], unsafe_member: str | None = None) -> None:
    with zipfile.ZipFile(wheel, mode="w") as archive:
        for relative_path, content in files.items():
            _ = archive.writestr((WHEEL_STATIC_PREFIX / relative_path).as_posix(), content)
        if unsafe_member is not None:
            _ = archive.writestr(unsafe_member, b"unsafe")


def _write_sdist(sdist: Path, files: dict[PurePosixPath, bytes]) -> None:
    with tarfile.open(sdist, mode="w:gz") as archive:
        for relative_path, content in files.items():
            member = tarfile.TarInfo((SDIST_STATIC_PREFIX / relative_path).as_posix())
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))


def _run_audit(wheel: Path, sdist: Path, expected_static: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- fixed argv invokes this repository's own script.
        (
            sys.executable,
            AUDIT_SCRIPT_RELATIVE_PATH,
            "--wheel",
            str(wheel),
            "--sdist",
            str(sdist),
            "--expected-static",
            str(expected_static),
        ),
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
