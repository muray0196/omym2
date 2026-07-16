"""
Summary: Tests Track listing, facet, and group-by usecase behavior.
Why: Protects read-only Track browsing before Web routes render it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.track import Track, TrackGrouping, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.features.tracks.dto import GroupTracksRequest, ListTracksRequest, TrackStatusFacetsRequest
from omym2.features.tracks.ports import TracksPorts
from omym2.features.tracks.usecases.get_track_status_facets import GetTrackStatusFacetsUseCase
from omym2.features.tracks.usecases.group_tracks import GroupTracksUseCase
from omym2.features.tracks.usecases.list_tracks import ListTracksUseCase
from omym2.shared.ids import LibraryId, TrackId
from omym2.shared.pagination import PageRequest
from tests.fakes.in_memory_repositories import InMemoryUnitOfWork

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CONTENT_HASH = "content"
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
SECOND_LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345679"))
TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345680"))
SECOND_TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345681"))
THIRD_TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345682"))
FOURTH_TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345683"))
METADATA_HASH = "metadata"
TWO_ITEM_LIMIT = 2
ALL_LIBRARY_TRACK_TOTAL = 3
PAGINATED_TRACK_TOTAL = 4
STATUS_FACET_TRACK_TOTAL = 3
GROUPED_TRACK_GROUP_TOTAL = 3
KEYSET_GROUP_TOTAL = 2
HIERARCHY_ARTIST = "Library Artist"
HIERARCHY_ALBUM = "Library Album"
HIERARCHY_YEAR = 2026
HIERARCHY_DISC_NUMBER = 1
HIERARCHY_ARTIST_KEY = '["Library Artist"]'
HIERARCHY_ALBUM_KEY = '["Library Artist","Library Album",2026]'
HIERARCHY_DISC_KEY = '["Library Artist","Library Album",2026,1]'
HIERARCHY_UNNUMBERED_DISC_KEY = '["Library Artist","Library Album",2026,"(unknown)"]'
HIERARCHY_TRACK_COUNT = 2
FOUR_TRACK_GROUP_TOTAL = 4
ASCII_WHITESPACE_FALLBACK_ARTIST = "Whitespace Fallback"
ASCII_WHITESPACE_ARTIST_KEY = '["Whitespace Fallback"]'
ASCII_WHITESPACE_UNKNOWN_ALBUM_KEY = '["Whitespace Fallback","(unknown)",null]'


def test_list_tracks_returns_all_known_tracks_in_display_order_without_commit() -> None:
    """All-library listing reads through query_page and never commits."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID))
    uow.libraries.save(_library(SECOND_LIBRARY_ID))
    uow.tracks.save(_track(SECOND_TRACK_ID, LIBRARY_ID, current_path="Beta/Title.flac"))
    uow.tracks.save(_track(TRACK_ID, LIBRARY_ID, current_path="Alpha/Title.flac"))
    uow.tracks.save(_track(THIRD_TRACK_ID, SECOND_LIBRARY_ID, current_path="Gamma/Title.flac"))

    page = ListTracksUseCase(TracksPorts(uow)).execute(ListTracksRequest())

    assert tuple(track.track_id for track in page.items) == (TRACK_ID, SECOND_TRACK_ID, THIRD_TRACK_ID)
    assert page.total == ALL_LIBRARY_TRACK_TOTAL
    assert page.next_cursor_key is None
    assert uow.commit_count == 0


def test_list_tracks_filters_by_library() -> None:
    """Library-scoped listing only returns Tracks owned by that Library."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID))
    uow.libraries.save(_library(SECOND_LIBRARY_ID))
    uow.tracks.save(_track(TRACK_ID, LIBRARY_ID, current_path="Alpha/Title.flac"))
    uow.tracks.save(_track(SECOND_TRACK_ID, SECOND_LIBRARY_ID, current_path="Beta/Title.flac"))

    page = ListTracksUseCase(TracksPorts(uow)).execute(ListTracksRequest(library_id=SECOND_LIBRARY_ID))

    assert tuple(track.track_id for track in page.items) == (SECOND_TRACK_ID,)
    assert page.total == 1
    assert uow.commit_count == 0


def test_list_tracks_filters_by_status() -> None:
    """Status filtering only returns Tracks with a matching status."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID))
    uow.tracks.save(_track(TRACK_ID, LIBRARY_ID, current_path="Alpha/Title.flac", status=TrackStatus.ACTIVE))
    uow.tracks.save(_track(SECOND_TRACK_ID, LIBRARY_ID, current_path="Beta/Title.flac", status=TrackStatus.REMOVED))

    page = ListTracksUseCase(TracksPorts(uow)).execute(ListTracksRequest(status=TrackStatus.REMOVED))

    assert tuple(track.track_id for track in page.items) == (SECOND_TRACK_ID,)
    assert page.total == 1


def test_list_tracks_search_matches_metadata_case_insensitively() -> None:
    """Search matches title/artist/album substrings, case-insensitive."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID))
    uow.tracks.save(
        _track(
            TRACK_ID,
            LIBRARY_ID,
            current_path="Alpha/Title.flac",
            metadata=TrackMetadata(title="Sunrise", artist="Nova", album="Dawn"),
        )
    )
    uow.tracks.save(
        _track(
            SECOND_TRACK_ID,
            LIBRARY_ID,
            current_path="Beta/Title.flac",
            metadata=TrackMetadata(title="Sunset", artist="Echo", album="Dusk"),
        )
    )

    page = ListTracksUseCase(TracksPorts(uow)).execute(ListTracksRequest(search="nova"))

    assert tuple(track.track_id for track in page.items) == (TRACK_ID,)
    assert page.total == 1


def test_list_tracks_paginates_forward_with_keyset_cursor() -> None:
    """A limit=2 keyset walk over 4 Tracks visits every Track exactly once, then terminates."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID))
    for track_id, path in (
        (TRACK_ID, "A/Title.flac"),
        (SECOND_TRACK_ID, "B/Title.flac"),
        (THIRD_TRACK_ID, "C/Title.flac"),
        (FOURTH_TRACK_ID, "D/Title.flac"),
    ):
        uow.tracks.save(_track(track_id, LIBRARY_ID, current_path=path))

    usecase = ListTracksUseCase(TracksPorts(uow))
    visited: list[TrackId] = []
    cursor: tuple[str, ...] | None = None
    for _ in range(3):
        page = usecase.execute(ListTracksRequest(page=PageRequest(limit=TWO_ITEM_LIMIT, cursor_key=cursor)))
        visited.extend(track.track_id for track in page.items)
        assert page.total == PAGINATED_TRACK_TOTAL
        if page.next_cursor_key is None:
            break
        cursor = page.next_cursor_key

    assert visited == [TRACK_ID, SECOND_TRACK_ID, THIRD_TRACK_ID, FOURTH_TRACK_ID]


def test_get_track_status_facets_orders_count_desc_then_value_asc_and_sums_to_total() -> None:
    """Status facets are ordered count DESC then value ASC; total sums the facet counts."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID))
    uow.tracks.save(_track(TRACK_ID, LIBRARY_ID, current_path="A/Title.flac", status=TrackStatus.ACTIVE))
    uow.tracks.save(_track(SECOND_TRACK_ID, LIBRARY_ID, current_path="B/Title.flac", status=TrackStatus.ACTIVE))
    uow.tracks.save(_track(THIRD_TRACK_ID, LIBRARY_ID, current_path="C/Title.flac", status=TrackStatus.REMOVED))

    result = GetTrackStatusFacetsUseCase(TracksPorts(uow)).execute(TrackStatusFacetsRequest())

    assert [(facet.value, facet.count) for facet in result.facets] == [
        (TrackStatus.ACTIVE.value, 2),
        (TrackStatus.REMOVED.value, 1),
    ]
    assert result.total == STATUS_FACET_TRACK_TOTAL


def test_group_tracks_orders_count_desc_then_key_asc_with_unknown_fallback() -> None:
    """Artist groups are ordered count DESC, key ASC with an unknown fallback."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID))
    uow.tracks.save(
        _track(
            TRACK_ID,
            LIBRARY_ID,
            current_path="A/1.flac",
            metadata=TrackMetadata(artist="Nova", album="Dawn"),
        )
    )
    uow.tracks.save(
        _track(
            SECOND_TRACK_ID,
            LIBRARY_ID,
            current_path="A/2.flac",
            metadata=TrackMetadata(artist="Nova", album="Dawn"),
        )
    )
    uow.tracks.save(
        _track(
            THIRD_TRACK_ID,
            LIBRARY_ID,
            current_path="B/1.flac",
            metadata=TrackMetadata(album_artist="Echo Collective", artist="Echo", album="Dusk"),
        )
    )
    uow.tracks.save(
        _track(
            FOURTH_TRACK_ID,
            LIBRARY_ID,
            current_path="C/1.flac",
            metadata=TrackMetadata(),
        )
    )

    page = GroupTracksUseCase(TracksPorts(uow)).execute(GroupTracksRequest(grouping=TrackGrouping.ARTIST))

    assert [(group.key, group.label, group.count) for group in page.items] == [
        ('["Nova"]', "Nova", 2),
        ('["(unknown)"]', "(unknown)", 1),
        ('["Echo Collective"]', "Echo Collective", 1),
    ]
    assert page.total == GROUPED_TRACK_GROUP_TOTAL


def test_group_tracks_paginates_with_count_then_key_keyset() -> None:
    """A limit=1 keyset walk over Track groups visits every group exactly once in order."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID))
    uow.tracks.save(_track(TRACK_ID, LIBRARY_ID, current_path="A/1.flac", metadata=TrackMetadata(artist="Nova")))
    uow.tracks.save(_track(SECOND_TRACK_ID, LIBRARY_ID, current_path="A/2.flac", metadata=TrackMetadata(artist="Nova")))
    uow.tracks.save(_track(THIRD_TRACK_ID, LIBRARY_ID, current_path="B/1.flac", metadata=TrackMetadata(artist="Echo")))

    usecase = GroupTracksUseCase(TracksPorts(uow))
    visited_keys: list[str] = []
    cursor: tuple[str, ...] | None = None
    for _ in range(3):
        page = usecase.execute(
            GroupTracksRequest(
                grouping=TrackGrouping.ARTIST,
                page=PageRequest(limit=1, cursor_key=cursor),
            )
        )
        visited_keys.extend(group.key for group in page.items)
        assert page.total == KEYSET_GROUP_TOTAL
        if page.next_cursor_key is None:
            break
        cursor = page.next_cursor_key

    assert visited_keys == ['["Nova"]', '["Echo"]']


def test_group_tracks_hierarchy_derives_metadata_keys_labels_and_parent_scopes() -> None:
    """Artist, album, and disc groups use persisted metadata and their opaque parent keys."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID))
    uow.tracks.save(
        _track(
            TRACK_ID,
            LIBRARY_ID,
            current_path="A/1.flac",
            metadata=TrackMetadata(
                album_artist="   ",
                artist=HIERARCHY_ARTIST,
                album=HIERARCHY_ALBUM,
                year=HIERARCHY_YEAR,
                disc_number=HIERARCHY_DISC_NUMBER,
            ),
        )
    )
    uow.tracks.save(
        _track(
            SECOND_TRACK_ID,
            LIBRARY_ID,
            current_path="A/2.flac",
            metadata=TrackMetadata(
                artist=HIERARCHY_ARTIST,
                album=HIERARCHY_ALBUM,
                year=HIERARCHY_YEAR,
                disc_number=0,
            ),
        )
    )
    uow.tracks.save(
        _track(
            THIRD_TRACK_ID,
            LIBRARY_ID,
            current_path="B/1.flac",
            metadata=TrackMetadata(artist="Other Artist", album="Other Album", disc_number=1),
        )
    )
    usecase = GroupTracksUseCase(TracksPorts(uow))

    artist_page = usecase.execute(GroupTracksRequest(grouping=TrackGrouping.ARTIST))
    album_page = usecase.execute(GroupTracksRequest(grouping=TrackGrouping.ALBUM, parent_key=HIERARCHY_ARTIST_KEY))
    disc_page = usecase.execute(GroupTracksRequest(grouping=TrackGrouping.DISC, parent_key=HIERARCHY_ALBUM_KEY))

    artist_groups = {group.key: group for group in artist_page.items}
    album_groups = {group.key: group for group in album_page.items}
    disc_groups = {group.key: group for group in disc_page.items}
    assert artist_groups[HIERARCHY_ARTIST_KEY].label == HIERARCHY_ARTIST
    assert artist_groups[HIERARCHY_ARTIST_KEY].count == HIERARCHY_TRACK_COUNT
    assert album_groups[HIERARCHY_ALBUM_KEY].label == f"{HIERARCHY_ALBUM} — {HIERARCHY_YEAR}"
    assert album_groups[HIERARCHY_ALBUM_KEY].count == HIERARCHY_TRACK_COUNT
    assert disc_groups[HIERARCHY_DISC_KEY].label == f"Disc {HIERARCHY_DISC_NUMBER}"
    assert disc_groups[HIERARCHY_UNNUMBERED_DISC_KEY].label == "Unnumbered disc"


def test_group_tracks_rejects_invalid_hierarchy_parents() -> None:
    """Only album and disc levels accept the opaque parent key their hierarchy requires."""
    usecase = GroupTracksUseCase(TracksPorts(InMemoryUnitOfWork()))

    with pytest.raises(ValueError, match="does not accept parent_key"):
        _ = usecase.execute(GroupTracksRequest(grouping=TrackGrouping.ARTIST, parent_key=HIERARCHY_ARTIST_KEY))
    with pytest.raises(ValueError, match="requires parent_key"):
        _ = usecase.execute(GroupTracksRequest(grouping=TrackGrouping.ALBUM))
    with pytest.raises(ValueError, match="requires parent_key"):
        _ = usecase.execute(GroupTracksRequest(grouping=TrackGrouping.DISC))


def test_group_tracks_treats_ascii_tabs_and_newlines_as_blank_metadata() -> None:
    """The in-memory fake shares the hierarchy blank-value semantics used by SQLite."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID))
    uow.tracks.save(
        _track(
            TRACK_ID,
            LIBRARY_ID,
            current_path="Whitespace/1.flac",
            metadata=TrackMetadata(
                album_artist="\t",
                artist=ASCII_WHITESPACE_FALLBACK_ARTIST,
                album="\n",
            ),
        )
    )
    usecase = GroupTracksUseCase(TracksPorts(uow))

    artist_page = usecase.execute(GroupTracksRequest(grouping=TrackGrouping.ARTIST))
    album_page = usecase.execute(
        GroupTracksRequest(grouping=TrackGrouping.ALBUM, parent_key=ASCII_WHITESPACE_ARTIST_KEY)
    )

    assert [(group.key, group.label) for group in artist_page.items] == [
        (ASCII_WHITESPACE_ARTIST_KEY, ASCII_WHITESPACE_FALLBACK_ARTIST)
    ]
    assert [(group.key, group.label) for group in album_page.items] == [
        (ASCII_WHITESPACE_UNKNOWN_ALBUM_KEY, "(unknown)")
    ]


def test_list_tracks_group_members_use_music_order_and_require_a_group_filter_pair() -> None:
    """Disc members paginate by positive track number, title, track ID, and reject unpaired filters."""
    uow = InMemoryUnitOfWork()
    uow.libraries.save(_library(LIBRARY_ID))
    metadata_values = (
        (TRACK_ID, "A/2.flac", "Zulu", 2),
        (SECOND_TRACK_ID, "A/1.flac", "Beta", 1),
        (THIRD_TRACK_ID, "A/0.flac", "Alpha", 0),
        (FOURTH_TRACK_ID, "A/missing.flac", "Aardvark", None),
    )
    for track_id, path, title, track_number in metadata_values:
        uow.tracks.save(
            _track(
                track_id,
                LIBRARY_ID,
                current_path=path,
                metadata=TrackMetadata(
                    title=title,
                    artist=HIERARCHY_ARTIST,
                    album=HIERARCHY_ALBUM,
                    year=HIERARCHY_YEAR,
                    disc_number=HIERARCHY_DISC_NUMBER,
                    track_number=track_number,
                ),
            )
        )
    usecase = ListTracksUseCase(TracksPorts(uow))

    first_page = usecase.execute(
        ListTracksRequest(
            grouping=TrackGrouping.DISC,
            group_key=HIERARCHY_DISC_KEY,
            page=PageRequest(limit=TWO_ITEM_LIMIT),
        )
    )
    second_page = usecase.execute(
        ListTracksRequest(
            grouping=TrackGrouping.DISC,
            group_key=HIERARCHY_DISC_KEY,
            page=PageRequest(limit=TWO_ITEM_LIMIT, cursor_key=first_page.next_cursor_key),
        )
    )

    assert tuple(track.track_id for track in first_page.items) == (SECOND_TRACK_ID, TRACK_ID)
    assert tuple(track.track_id for track in second_page.items) == (FOURTH_TRACK_ID, THIRD_TRACK_ID)
    assert first_page.total == FOUR_TRACK_GROUP_TOTAL
    assert second_page.next_cursor_key is None
    with pytest.raises(ValueError, match="grouping and group_key"):
        _ = usecase.execute(ListTracksRequest(grouping=TrackGrouping.DISC))


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


def _track(
    track_id: TrackId,
    library_id: LibraryId,
    *,
    current_path: str,
    status: TrackStatus = TrackStatus.ACTIVE,
    metadata: TrackMetadata | None = None,
) -> Track:
    return Track(
        track_id=track_id,
        library_id=library_id,
        current_path=current_path,
        canonical_path=current_path,
        content_hash=CONTENT_HASH,
        metadata_hash=METADATA_HASH,
        size=None,
        mtime=None,
        metadata=TrackMetadata(title="Title", artist="Artist", album="Album") if metadata is None else metadata,
        status=status,
        first_seen_at=BASE_TIME,
        last_seen_at=BASE_TIME,
        updated_at=BASE_TIME,
    )
