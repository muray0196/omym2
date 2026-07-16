"""
Summary: Validates recorded source-root layouts for unprocessed file moves.
Why: Prevents collection and reversal actions from escaping or relabelling their reviewed paths.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from omym2.domain.models.app_config import UnprocessedConfig


@dataclass(frozen=True, slots=True)
class UnprocessedPathLayout:
    """One validated collection layout recorded entirely in a PlanAction."""

    directory: str
    source_relative_path: str


def validate_unprocessed_path_layout(
    source_root: str,
    source_path: str,
    target_path: str,
    *,
    excluded_root: str | None = None,
) -> UnprocessedPathLayout | None:
    """Return the recorded collection layout only when every path is exact and rooted."""
    root = _normalized_absolute_path(source_root)
    source = _normalized_absolute_path(source_path)
    target = _normalized_absolute_path(target_path)
    if root is None or source is None or target is None:
        return None
    if excluded_root is not None:
        excluded = _normalized_absolute_path(excluded_root)
        if excluded is None or _is_within(source, excluded) or _is_within(target, excluded):
            return None

    try:
        relative_source = source.relative_to(root)
        relative_target = target.relative_to(root)
    except ValueError:
        return None

    source_parts = relative_source.parts
    target_parts = relative_target.parts
    if len(source_parts) == 0 or len(target_parts) != len(source_parts) + 1 or target_parts[1:] != source_parts:
        return None

    try:
        _ = UnprocessedConfig(directory=target_parts[0])
    except ValueError:
        return None

    return UnprocessedPathLayout(
        directory=target_parts[0],
        source_relative_path=relative_source.as_posix(),
    )


def _normalized_absolute_path(raw_path: str) -> Path | None:
    """Return one lexical absolute path without accepting parent traversal."""
    path = Path(raw_path).expanduser()
    if not path.is_absolute() or ".." in path.parts:
        return None
    normalized = Path(os.path.abspath(path))  # noqa: PTH100  # Lexical only; never follows filesystem links.
    return normalized if os.fspath(path) == os.fspath(normalized) else None


def _is_within(path: Path, root: Path) -> bool:
    try:
        _ = path.relative_to(root)
    except ValueError:
        return False
    return True
