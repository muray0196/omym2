"""
Summary: Tests exact persisted Track detail lookup.
Why: Keeps the Library detail route read-only and identity-based.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from omym2.domain.models.track import Track, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.features.tracks.dto import GetTrackRequest
from omym2.features.tracks.ports import TracksPorts
from omym2.features.tracks.usecases.get_track import GetTrackUseCase, TrackNotFoundError
from omym2.shared.ids import LibraryId, TrackId
from tests.fakes.in_memory_repositories import InMemoryUnitOfWork

NOW = datetime(2026, 7, 13, tzinfo=UTC)
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345670"))
TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345671"))


def test_get_track_returns_exact_persisted_resource_without_committing() -> None:
    """Track detail is an identity lookup and performs no mutation."""
    uow = InMemoryUnitOfWork()
    expected = _track()
    uow.tracks.save(expected)

    actual = GetTrackUseCase(TracksPorts(uow)).execute(GetTrackRequest(TRACK_ID))

    assert actual == expected
    assert uow.commit_count == 0


def test_get_track_rejects_unknown_identity() -> None:
    """Missing Tracks remain distinct from empty Track metadata."""
    usecase = GetTrackUseCase(TracksPorts(InMemoryUnitOfWork()))

    with pytest.raises(TrackNotFoundError, match="Track was not found"):
        _ = usecase.execute(GetTrackRequest(TRACK_ID))


def _track() -> Track:
    return Track(
        track_id=TRACK_ID,
        library_id=LIBRARY_ID,
        current_path="Artist/Album/01 Title.flac",
        canonical_path="Artist/Album/01 Title.flac",
        content_hash="content",
        metadata_hash="metadata",
        size=1,
        mtime=NOW,
        metadata=TrackMetadata(title="Title", artist="Artist", album="Album"),
        status=TrackStatus.ACTIVE,
        first_seen_at=NOW,
        last_seen_at=NOW,
        updated_at=NOW,
    )
