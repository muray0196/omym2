"""
Summary: Defines the single-file inspect usecase contract.
Why: Allows read adapters to share one inspection boundary later.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omym2.domain.models.file_snapshot import FileSnapshot
    from omym2.features.inspect.dto import InspectFileRequest
    from omym2.features.inspect.ports import InspectFilePorts

USECASE_DEFERRED_MESSAGE = "Inspect file behavior is deferred until the read adapter phase."


@dataclass(frozen=True, slots=True)
class InspectFileUseCase:
    """Contract for inspecting one filesystem file."""

    ports: InspectFilePorts

    def execute(self, request: InspectFileRequest) -> FileSnapshot:
        """Capture metadata and hash information for one file."""
        # Phase 3 fixes the call shape only; Phase 6 owns read adapter behavior.
        del request
        raise NotImplementedError(USECASE_DEFERRED_MESSAGE)
