"""
Summary: Replaces the packaged Web static tree with the renewed Vite build.
Why: Prevents stale assets from surviving between clean-room frontend builds.
"""
# ruff: noqa: INP001, T201 -- Standalone build script reports concise CLI results.

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

PROJECT_ROOT_NOT_FOUND_MESSAGE = "Unable to locate the project root."
DEFAULT_WEB_BUILD_RELATIVE_PATH = Path("web-v2/dist")
DEFAULT_PACKAGED_STATIC_RELATIVE_PATH = Path("src/omym2/adapters/web/static_dist")
STATIC_INDEX_FILE_NAME = "index.html"
STAGING_DIRECTORY_PREFIX = ".omym2-static-sync-"


class StaticSyncError(RuntimeError):
    """Raised when a Web static export cannot be synchronized safely."""


class ParsedArgs(argparse.Namespace):
    """Typed command-line arguments for static synchronization."""

    def __init__(self, source: Path, destination: Path) -> None:
        super().__init__()
        self.source: Path = source
        self.destination: Path = destination


def sync_static_export(source: Path, destination: Path) -> None:
    """Replace destination with one staged copy of source."""
    source = source.resolve()
    destination = destination.resolve()
    _validate_source(source)
    if source == destination or source.is_relative_to(destination) or destination.is_relative_to(source):
        msg = "Source and destination static trees must not overlap."
        raise StaticSyncError(msg)

    _ = destination.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(prefix=STAGING_DIRECTORY_PREFIX, dir=destination.parent))
    staged_export = staging_root / destination.name
    try:
        _ = shutil.copytree(source, staged_export, symlinks=True)
        _reject_symlinks(staged_export)
        if destination.exists() or destination.is_symlink():
            if destination.is_dir() and not destination.is_symlink():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        _ = staged_export.replace(destination)
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)


def _validate_source(source: Path) -> None:
    if not source.is_dir():
        msg = f"Web build directory does not exist: {source}"
        raise StaticSyncError(msg)
    if not (source / STATIC_INDEX_FILE_NAME).is_file():
        msg = f"Web build is missing {STATIC_INDEX_FILE_NAME}: {source}"
        raise StaticSyncError(msg)
    _reject_symlinks(source)


def _reject_symlinks(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_symlink():
            msg = f"Web static trees must not contain symlinks: {path}"
            raise StaticSyncError(msg)


def _project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise StaticSyncError(PROJECT_ROOT_NOT_FOUND_MESSAGE)


def _parse_args(argv: Sequence[str] | None) -> ParsedArgs:
    root = _project_root()
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--source", type=Path, default=root / DEFAULT_WEB_BUILD_RELATIVE_PATH)
    _ = parser.add_argument("--destination", type=Path, default=root / DEFAULT_PACKAGED_STATIC_RELATIVE_PATH)
    return parser.parse_args(
        argv,
        namespace=ParsedArgs(root / DEFAULT_WEB_BUILD_RELATIVE_PATH, root / DEFAULT_PACKAGED_STATIC_RELATIVE_PATH),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Synchronize the built frontend and report a concise result."""
    args = _parse_args(argv)
    try:
        sync_static_export(args.source, args.destination)
    except StaticSyncError as exc:
        print(f"static sync failed: {exc}", file=sys.stderr)
        return 1
    print(f"static sync passed: {args.source} -> {args.destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
