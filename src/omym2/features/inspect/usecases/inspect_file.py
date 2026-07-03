"""
Summary: Implements the single-file inspect usecase.
Why: Gives CLI and later UI a read-only metadata/hash/canonical-path boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.domain.services.path_policy import PathPolicy
from omym2.features.inspect.dto import InspectFileResult

if TYPE_CHECKING:
    from omym2.features.inspect.dto import InspectFileRequest
    from omym2.features.inspect.ports import InspectFilePorts


@dataclass(frozen=True, slots=True)
class InspectFileUseCase:
    """Inspect one filesystem file without creating or applying Plans."""

    ports: InspectFilePorts

    def execute(self, request: InspectFileRequest) -> InspectFileResult:
        """Capture metadata, hashes, and current canonical-path projection."""
        config = self.ports.config_store.load()
        snapshot = self.ports.file_snapshot_reader.capture(request.path)

        try:
            canonical_path = PathPolicy.from_app_config(config).canonical_path(
                snapshot.metadata,
                snapshot.file_extension,
            )
        except ValueError as exc:
            # Missing title or bad suffix is inspection data, not a mutation-time
            # failure, so the caller receives the snapshot plus the path error.
            return InspectFileResult(snapshot=snapshot, canonical_path=None, canonical_path_error=str(exc))

        return InspectFileResult(snapshot=snapshot, canonical_path=canonical_path)
