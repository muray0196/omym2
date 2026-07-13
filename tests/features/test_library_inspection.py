"""
Summary: Tests backend-authoritative Library readiness inspection.
Why: Prevents Web Library resources from treating root paths as identity or stale policies as ready.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

import pytest

from omym2.adapters.config.default_config import default_app_config
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.services.config_fingerprint import calculate_path_policy_fingerprint
from omym2.features.common_ports import ConfigSnapshot, ConfigSnapshotState
from omym2.features.libraries.dto import InspectLibrariesRequest
from omym2.features.libraries.ports import LibraryInspectionPorts
from omym2.features.libraries.usecases.inspect_libraries import (
    InspectLibrariesUseCase,
    LibraryNotFoundError,
)
from omym2.shared.ids import LibraryId
from tests.fakes.in_memory_repositories import InMemoryUnitOfWork

if TYPE_CHECKING:
    from omym2.domain.models.app_config import AppConfig

NOW = datetime(2026, 7, 13, tzinfo=UTC)
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345601"))
SECOND_LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345602"))


def test_inspect_libraries_projects_current_and_stale_status_without_mutation() -> None:
    """Registered Libraries become stale only when their stored policy differs from current Config."""
    config = default_app_config()
    current_fingerprint = calculate_path_policy_fingerprint(
        config.path_policy,
        config.artist_ids,
        config.metadata.album_year_resolution,
    )
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID, current_fingerprint))
    uow.libraries.save(_library(SECOND_LIBRARY_ID, "old-policy"))
    usecase = InspectLibrariesUseCase(
        LibraryInspectionPorts(uow=uow, config_snapshot_reader=StaticConfigSnapshotReader(config))
    )

    result = usecase.execute(InspectLibrariesRequest())

    assert tuple(item.library.library_id for item in result) == (LIBRARY_ID, SECOND_LIBRARY_ID)
    assert result[0].effective_status is LibraryStatus.REGISTERED
    assert result[0].is_path_policy_current is True
    assert result[1].effective_status is LibraryStatus.STALE
    assert result[1].is_path_policy_current is False
    assert uow.commit_count == 0


def test_inspect_one_library_uses_stable_id_and_rejects_unknown_id() -> None:
    """Detail lookup selects by Library ID and reports an unknown stable identity."""
    config = default_app_config()
    uow = InMemoryUnitOfWork()
    usecase = InspectLibrariesUseCase(
        LibraryInspectionPorts(uow=uow, config_snapshot_reader=StaticConfigSnapshotReader(config))
    )

    with pytest.raises(LibraryNotFoundError):
        _ = usecase.execute(InspectLibrariesRequest(library_id=LIBRARY_ID))


class StaticConfigSnapshotReader:
    """Return one deterministic valid Config snapshot."""

    def __init__(self, config: AppConfig) -> None:
        self._config: AppConfig = config

    def read_snapshot(self) -> ConfigSnapshot:
        return ConfigSnapshot(
            state=ConfigSnapshotState.VALID,
            config=self._config,
            config_revision="test-revision",
        )


def _library(library_id: LibraryId, path_policy_hash: str) -> Library:
    return Library(
        library_id=library_id,
        root_path=f"/music/{library_id}",
        path_policy_hash=path_policy_hash,
        registered_at=NOW,
        status=LibraryStatus.REGISTERED,
        created_at=NOW,
        updated_at=NOW,
    )
