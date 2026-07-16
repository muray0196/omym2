"""
Summary: Provides deterministic content-only observation fakes.
Why: Lets companion planning tests control inventories, snapshots, and failures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from os import fspath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from omym2.domain.models.file_snapshot import FileContentSnapshot
    from omym2.features.common_ports import FileSystemPath, SourceInventoryEntry, SourceInventoryRequest


def _empty_content_results() -> dict[str, FileContentSnapshot | BaseException]:
    """Return a typed empty content-observation mapping."""
    return {}


@dataclass(slots=True)
class StaticSourceInventoryReader:
    """Return one deterministic inventory while recording requested roots."""

    entries: tuple[SourceInventoryEntry, ...] = ()
    requests: list[SourceInventoryRequest] = field(default_factory=list)

    def scan(self, request: SourceInventoryRequest) -> tuple[SourceInventoryEntry, ...]:
        """Record and return the configured inventory."""
        self.requests.append(request)
        return self.entries


@dataclass(slots=True)
class MappingFileContentSnapshotReader:
    """Capture configured content snapshots or raise configured failures by path."""

    results: Mapping[str, FileContentSnapshot | BaseException] = field(default_factory=_empty_content_results)
    captures: list[tuple[str, str]] = field(default_factory=list)

    def capture(self, path: FileSystemPath, *, root: FileSystemPath) -> FileContentSnapshot:
        """Return one configured path result and retain the exact call."""
        path_text = fspath(path)
        root_text = fspath(root)
        self.captures.append((path_text, root_text))
        result = self.results.get(path_text)
        if result is None:
            raise FileNotFoundError(path_text)
        if isinstance(result, BaseException):
            raise result
        return result


@dataclass(slots=True)
class StaticFilePresence:
    """Report configured exact paths as existing."""

    existing_paths: set[str] = field(default_factory=set)
    checked_paths: list[str] = field(default_factory=list)

    def exists(self, path: FileSystemPath) -> bool:
        """Record and test one path without filesystem I/O."""
        path_text = fspath(path)
        self.checked_paths.append(path_text)
        return path_text in self.existing_paths
