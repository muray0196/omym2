"""
Summary: Normalizes CLI path arguments.
Why: Keeps inbound adapters free of filesystem resolution details.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.features.common_ports import FileSystemPath


def normalize_cli_path(raw_path: FileSystemPath) -> str:
    """Expand and resolve a CLI path using filesystem context."""
    return str(Path(raw_path).expanduser().resolve(strict=False))
