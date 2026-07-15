"""
Summary: Projects persisted Libraries against the current PathPolicy fingerprint.
Why: Prevents Web routes from inferring effective Library readiness.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.domain.models.library import LibraryStatus
from omym2.domain.services.config_fingerprint import calculate_path_policy_fingerprint
from omym2.features.common_ports import ConfigSnapshotState
from omym2.features.libraries.dto import LibraryInspection

if TYPE_CHECKING:
    from omym2.domain.models.library import Library
    from omym2.features.common_ports import ConfigSnapshot
    from omym2.features.libraries.dto import InspectLibrariesRequest
    from omym2.features.libraries.ports import LibraryInspectionPorts

LIBRARY_NOT_FOUND_MESSAGE = "Library was not found."


@dataclass(frozen=True, slots=True)
class InspectLibrariesUseCase:
    """Return effective readiness for every Library or one stable Library ID."""

    ports: LibraryInspectionPorts

    def execute(self, request: InspectLibrariesRequest) -> tuple[LibraryInspection, ...]:
        """Return Library readiness without changing Config or managed state."""
        config_snapshot = self.ports.config_snapshot_reader.read_snapshot()
        with self.ports.uow as uow:
            if request.library_id is None:
                libraries = tuple(uow.libraries.list_all())
            else:
                library = uow.libraries.get(request.library_id)
                if library is None:
                    raise LibraryNotFoundError(LIBRARY_NOT_FOUND_MESSAGE)
                libraries = (library,)
        return tuple(_inspection(library, config_snapshot) for library in libraries)


class LibraryNotFoundError(ValueError):
    """Raised when one requested stable Library ID is not persisted."""


def _inspection(library: Library, config_snapshot: ConfigSnapshot) -> LibraryInspection:
    path_policy_current = _is_path_policy_current(library, config_snapshot)
    effective_status = (
        LibraryStatus.STALE
        if library.status is LibraryStatus.REGISTERED and not path_policy_current
        else library.status
    )
    return LibraryInspection(
        library=library,
        effective_status=effective_status,
        is_registered=library.registered_at is not None,
        is_path_policy_current=path_policy_current,
    )


def _is_path_policy_current(library: Library, config_snapshot: ConfigSnapshot) -> bool:
    if config_snapshot.state is ConfigSnapshotState.INVALID:
        return False
    config = config_snapshot.config
    return library.path_policy_hash == calculate_path_policy_fingerprint(
        config.path_policy,
        config.artist_ids,
        config.metadata.album_year_resolution,
        config.artist_names,
    )
