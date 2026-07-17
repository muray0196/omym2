"""
Summary: Classifies changed repository paths for conservative CI routing.
Why: Documentation-only changes should not consume full cross-platform validation.
"""
# ruff: noqa: INP001, T201 -- Standalone CI routing reports one machine-readable scope.

from __future__ import annotations

import sys
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

if __package__:
    from scripts import config
else:
    sys.path.insert(0, str(PurePosixPath(__file__).parents[1]))
    from scripts import config  # Direct script execution needs the repository script namespace.

if TYPE_CHECKING:
    from collections.abc import Iterable


def classify_paths(paths: Iterable[str]) -> str:
    """Return the docs scope only when every non-empty path is explicitly safe."""
    changed_paths = tuple(path.strip() for path in paths if path.strip())
    if not changed_paths:
        return config.CI_SCOPE_FULL
    if all(_is_fast_path(path) for path in changed_paths):
        return config.CI_SCOPE_DOCS
    return config.CI_SCOPE_FULL


def _is_fast_path(path: str) -> bool:
    normalized = PurePosixPath(path).as_posix()
    if any(normalized.startswith(prefix) for prefix in config.CI_FAST_PATH_PREFIXES):
        return True
    candidate = PurePosixPath(normalized)
    return len(candidate.parts) == 1 and candidate.suffix.lower() in config.CI_FAST_PATH_ROOT_SUFFIXES


def main() -> int:
    """Classify newline-delimited paths from standard input."""
    print(classify_paths(sys.stdin))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
