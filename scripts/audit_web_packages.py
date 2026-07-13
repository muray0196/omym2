"""
Summary: Audits wheel and sdist copies of the bundled Web export.
Why: Proves Python artifacts contain exactly the already-audited static tree.
"""
# ruff: noqa: INP001, T201 -- Standalone audit script reports concise CLI results.

from __future__ import annotations

import argparse
import hashlib
import stat
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

PROJECT_ROOT_NOT_FOUND_MESSAGE = "Unable to locate the project root."
DEFAULT_PACKAGED_STATIC_RELATIVE_PATH = Path("src/omym2/adapters/web/static_dist")
WHEEL_STATIC_PREFIX = PurePosixPath("omym2/adapters/web/static_dist")
SDIST_STATIC_SUFFIX = PurePosixPath("src/omym2/adapters/web/static_dist")
STATIC_INDEX_FILE_NAME = PurePosixPath("index.html")


class PackageAuditError(RuntimeError):
    """Raised when built Python packages violate the static distribution contract."""


class ParsedArgs(argparse.Namespace):
    """Typed command-line arguments for package auditing."""

    def __init__(self, expected_static: Path) -> None:
        super().__init__()
        self.wheel: Path = Path()
        self.sdist: Path = Path()
        self.expected_static: Path = expected_static


def audit_packages(wheel: Path, sdist: Path, expected_static: Path) -> None:
    """Require both artifacts to contain the expected static tree exactly."""
    expected = _directory_digests(expected_static)
    if STATIC_INDEX_FILE_NAME not in expected:
        msg = f"Expected static tree is missing {STATIC_INDEX_FILE_NAME.as_posix()}."
        raise PackageAuditError(msg)

    wheel_files = _wheel_static_digests(wheel)
    sdist_files = _sdist_static_digests(sdist)
    _require_equal("wheel", expected, wheel_files)
    _require_equal("sdist", expected, sdist_files)


def _directory_digests(root: Path) -> dict[PurePosixPath, str]:
    root = root.resolve()
    if not root.is_dir():
        msg = f"Expected static directory does not exist: {root}"
        raise PackageAuditError(msg)
    result: dict[PurePosixPath, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            msg = f"Expected static tree contains a symlink: {path}"
            raise PackageAuditError(msg)
        if path.is_file():
            relative_path = PurePosixPath(path.relative_to(root).as_posix())
            with path.open("rb") as stream:
                result[relative_path] = hashlib.file_digest(stream, "sha256").hexdigest()
    return result


def _wheel_static_digests(wheel: Path) -> dict[PurePosixPath, str]:
    if not wheel.is_file():
        msg = f"Wheel does not exist: {wheel}"
        raise PackageAuditError(msg)
    try:
        with zipfile.ZipFile(wheel) as archive:
            result: dict[PurePosixPath, str] = {}
            seen: set[PurePosixPath] = set()
            for info in archive.infolist():
                member = _safe_member_path(info.filename)
                if member in seen:
                    msg = f"Wheel contains a duplicate member: {member.as_posix()}"
                    raise PackageAuditError(msg)
                seen.add(member)
                if info.is_dir() or not member.is_relative_to(WHEEL_STATIC_PREFIX):
                    continue
                if stat.S_ISLNK(info.external_attr >> 16):
                    msg = f"Wheel static tree contains a symlink: {member.as_posix()}"
                    raise PackageAuditError(msg)
                relative_path = member.relative_to(WHEEL_STATIC_PREFIX)
                result[relative_path] = hashlib.sha256(archive.read(info)).hexdigest()
    except (OSError, zipfile.BadZipFile) as exc:
        msg = f"Unable to read wheel {wheel}: {exc}"
        raise PackageAuditError(msg) from exc
    return result


def _sdist_static_digests(sdist: Path) -> dict[PurePosixPath, str]:
    if not sdist.is_file():
        msg = f"Source distribution does not exist: {sdist}"
        raise PackageAuditError(msg)
    result: dict[PurePosixPath, str] = {}
    seen: set[PurePosixPath] = set()
    try:
        with tarfile.open(sdist, mode="r:*") as archive:
            for member_info in archive.getmembers():
                member = _safe_member_path(member_info.name)
                if member in seen:
                    msg = f"Source distribution contains a duplicate member: {member.as_posix()}"
                    raise PackageAuditError(msg)
                seen.add(member)
                relative_path = _relative_to_suffix(member, SDIST_STATIC_SUFFIX)
                if relative_path is None:
                    continue
                if member_info.issym() or member_info.islnk():
                    msg = f"Source distribution static tree contains a link: {member.as_posix()}"
                    raise PackageAuditError(msg)
                if not member_info.isfile():
                    continue
                stream = archive.extractfile(member_info)
                if stream is None:
                    msg = f"Unable to read source distribution member: {member.as_posix()}"
                    raise PackageAuditError(msg)
                result[relative_path] = hashlib.sha256(stream.read()).hexdigest()
    except (OSError, tarfile.TarError) as exc:
        msg = f"Unable to read source distribution {sdist}: {exc}"
        raise PackageAuditError(msg) from exc
    return result


def _safe_member_path(raw_path: str) -> PurePosixPath:
    path = PurePosixPath(raw_path)
    if (
        path.is_absolute()
        or not path.parts
        or ".." in path.parts
        or "\\" in raw_path
        or "\x00" in raw_path
        or path.parts[0].endswith(":")
    ):
        msg = f"Archive contains an unsafe member path: {raw_path}"
        raise PackageAuditError(msg)
    return path


def _relative_to_suffix(path: PurePosixPath, suffix: PurePosixPath) -> PurePosixPath | None:
    suffix_parts = suffix.parts
    path_parts = path.parts
    for offset in range(len(path_parts) - len(suffix_parts) + 1):
        if path_parts[offset : offset + len(suffix_parts)] == suffix_parts:
            remaining = path_parts[offset + len(suffix_parts) :]
            return PurePosixPath(*remaining) if remaining else PurePosixPath(".")
    return None


def _require_equal(label: str, expected: Mapping[PurePosixPath, str], actual: Mapping[PurePosixPath, str]) -> None:
    if expected.keys() != actual.keys():
        missing = sorted(path.as_posix() for path in expected.keys() - actual.keys())
        extra = sorted(path.as_posix() for path in actual.keys() - expected.keys())
        msg = f"{label} static tree differs; missing={missing}, extra={extra}"
        raise PackageAuditError(msg)
    changed = sorted(path.as_posix() for path in expected if expected[path] != actual[path])
    if changed:
        msg = f"{label} static file content differs: {changed}"
        raise PackageAuditError(msg)


def _project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise PackageAuditError(PROJECT_ROOT_NOT_FOUND_MESSAGE)


def _parse_args(argv: Sequence[str] | None) -> ParsedArgs:
    root = _project_root()
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--wheel", type=Path, required=True)
    _ = parser.add_argument("--sdist", type=Path, required=True)
    _ = parser.add_argument(
        "--expected-static",
        type=Path,
        default=root / DEFAULT_PACKAGED_STATIC_RELATIVE_PATH,
    )
    return parser.parse_args(argv, namespace=ParsedArgs(root / DEFAULT_PACKAGED_STATIC_RELATIVE_PATH))


def main(argv: Sequence[str] | None = None) -> int:
    """Audit wheel and sdist static content and report a concise result."""
    args = _parse_args(argv)
    try:
        audit_packages(args.wheel, args.sdist, args.expected_static)
    except PackageAuditError as exc:
        print(f"package audit failed: {exc}", file=sys.stderr)
        return 1
    print(f"package audit passed: {args.wheel} and {args.sdist}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
