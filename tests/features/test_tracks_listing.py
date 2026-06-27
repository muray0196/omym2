"""
Summary: Tests Track listing usecase behavior.
Why: Protects read-only Track listing before Web routes render it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.track import Track, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.features.tracks.dto import ListTracksRequest
from omym2.features.tracks.ports import TracksPorts
from omym2.features.tracks.usecases.list_tracks import ListTracksUseCase
from omym2.shared.ids import LibraryId, TrackId
from tests.fakes.in_memory_repositories import InMemoryUnitOfWork

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CONTENT_HASH = "content"
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
SECOND_LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345679"))
TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345680"))
SECOND_TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345681"))
THIRD_TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345682"))
METADATA_HASH = "metadata"


def test_list_tracks_returns_all_known_tracks_in_display_order_without_commit() -> None:
    """All-library listing reads through repositories and never commits."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID))
    uow.libraries.save(_library(SECOND_LIBRARY_ID))
    uow.tracks.save(_track(SECOND_TRACK_ID, LIBRARY_ID, current_path="Beta/Title.flac"))
    uow.tracks.save(_track(TRACK_ID, LIBRARY_ID, current_path="Alpha/Title.flac"))
    uow.tracks.save(_track(THIRD_TRACK_ID, SECOND_LIBRARY_ID, current_path="Gamma/Title.flac"))

    tracks = ListTracksUseCase(TracksPorts(uow)).execute(ListTracksRequest())

    assert tuple(track.track_id for track in tracks) == (TRACK_ID, SECOND_TRACK_ID, THIRD_TRACK_ID)
    assert uow.commit_count == 0


def test_list_tracks_filters_by_library() -> None:
    """Library-scoped listing only returns Tracks owned by that Library."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID))
    uow.libraries.save(_library(SECOND_LIBRARY_ID))
    uow.tracks.save(_track(TRACK_ID, LIBRARY_ID, current_path="Alpha/Title.flac"))
    uow.tracks.save(_track(SECOND_TRACK_ID, SECOND_LIBRARY_ID, current_path="Beta/Title.flac"))

    tracks = ListTracksUseCase(TracksPorts(uow)).execute(ListTracksRequest(library_id=SECOND_LIBRARY_ID))

    assert tuple(track.track_id for track in tracks) == (SECOND_TRACK_ID,)
    assert uow.commit_count == 0


def _library(library_id: LibraryId) -> Library:
    return Library(
        library_id=library_id,
        root_path="/music/library",
        path_policy_hash="config",
        registered_at=BASE_TIME,
        status=LibraryStatus.REGISTERED,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def _track(track_id: TrackId, library_id: LibraryId, *, current_path: str) -> Track:
    return Track(
        track_id=track_id,
        library_id=library_id,
        current_path=current_path,
        canonical_path=current_path,
        content_hash=CONTENT_HASH,
        metadata_hash=METADATA_HASH,
        metadata=TrackMetadata(title="Title", artist="Artist", album="Album"),
        status=TrackStatus.ACTIVE,
        first_seen_at=BASE_TIME,
        last_seen_at=BASE_TIME,
        updated_at=BASE_TIME,
    )
