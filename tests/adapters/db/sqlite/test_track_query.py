"""
Summary: Tests SQLiteTrackRepository keyset paging, search, facets, and group-by SQL.
Why: Protects the tracks browsing SQL contract (ordering, keyset math, LIKE escaping).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.db.sqlite.unit_of_work import SQLiteUnitOfWork
from omym2.domain.models.library import Library, LibraryStatus
from omym2.domain.models.track import Track, TrackGrouping, TrackStatus
from omym2.domain.models.track_metadata import TrackMetadata
from omym2.shared.ids import LibraryId, TrackId
from omym2.shared.pagination import PageRequest

if TYPE_CHECKING:
    from pathlib import Path

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)
CONTENT_HASH = "content"
METADATA_HASH = "metadata"
LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345678"))
SECOND_LIBRARY_ID = LibraryId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345679"))
TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345680"))
SECOND_TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345681"))
THIRD_TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345682"))
FOURTH_TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345683"))
FIFTH_TRACK_ID = TrackId(UUID("018f6a4f-3c2d-7b8a-9abc-def012345684"))
TWO_ITEM_LIMIT = 2
FIVE_TRACK_TOTAL = 5
TWO_GROUP_TOTAL = 2
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


def test_query_page_walks_every_track_exactly_once_with_keyset_cursor(tmp_path: Path) -> None:
    """A limit=2 keyset walk over 5 Tracks visits every Track once, in (current_path, track_id) order."""
    database_file = default_application_paths(tmp_path).database_file
    track_ids = (TRACK_ID, SECOND_TRACK_ID, THIRD_TRACK_ID, FOURTH_TRACK_ID, FIFTH_TRACK_ID)
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(LIBRARY_ID))
        for index, track_id in enumerate(track_ids):
            uow.tracks.save(_track(track_id, LIBRARY_ID, current_path=f"{index}/Title.flac"))
        uow.commit()

    visited: list[TrackId] = []
    cursor: tuple[str, ...] | None = None
    with SQLiteUnitOfWork(database_file) as uow:
        for _ in range(len(track_ids)):
            page = uow.tracks.query_page(
                None,
                track_id=None,
                search=None,
                status=None,
                grouping=None,
                group_key=None,
                page=PageRequest(limit=TWO_ITEM_LIMIT, cursor_key=cursor),
            )
            visited.extend(track.track_id for track in page.items)
            assert page.total == FIVE_TRACK_TOTAL
            if page.next_cursor_key is None:
                break
            cursor = page.next_cursor_key

    assert visited == list(track_ids)
    assert len(visited) == len(set(visited))


def test_query_page_scopes_by_library(tmp_path: Path) -> None:
    """query_page(library_id=...) only returns Tracks owned by that Library."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(LIBRARY_ID))
        uow.libraries.save(_library(SECOND_LIBRARY_ID))
        uow.tracks.save(_track(TRACK_ID, LIBRARY_ID, current_path="A/1.flac"))
        uow.tracks.save(_track(SECOND_TRACK_ID, SECOND_LIBRARY_ID, current_path="B/1.flac"))
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        page = uow.tracks.query_page(
            SECOND_LIBRARY_ID,
            track_id=None,
            search=None,
            status=None,
            grouping=None,
            group_key=None,
            page=PageRequest(),
        )

    assert tuple(track.track_id for track in page.items) == (SECOND_TRACK_ID,)
    assert page.total == 1


def test_query_page_filters_by_status(tmp_path: Path) -> None:
    """query_page(status=...) only returns Tracks with a matching status."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(LIBRARY_ID))
        uow.tracks.save(_track(TRACK_ID, LIBRARY_ID, current_path="A/1.flac", status=TrackStatus.ACTIVE))
        uow.tracks.save(_track(SECOND_TRACK_ID, LIBRARY_ID, current_path="B/1.flac", status=TrackStatus.REMOVED))
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        page = uow.tracks.query_page(
            None,
            track_id=None,
            search=None,
            status=TrackStatus.REMOVED,
            grouping=None,
            group_key=None,
            page=PageRequest(),
        )

    assert tuple(track.track_id for track in page.items) == (SECOND_TRACK_ID,)


def test_query_page_filters_by_track_id(tmp_path: Path) -> None:
    """query_page(track_id=...) returns only the exact Track ID match."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(LIBRARY_ID))
        uow.tracks.save(_track(TRACK_ID, LIBRARY_ID, current_path="A/1.flac"))
        uow.tracks.save(_track(SECOND_TRACK_ID, LIBRARY_ID, current_path="B/1.flac"))
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        page = uow.tracks.query_page(
            None,
            track_id=SECOND_TRACK_ID,
            search=None,
            status=None,
            grouping=None,
            group_key=None,
            page=PageRequest(),
        )

    assert tuple(track.track_id for track in page.items) == (SECOND_TRACK_ID,)
    assert page.total == 1


def test_query_page_search_treats_like_wildcards_as_literal(tmp_path: Path) -> None:
    """Search escapes SQL LIKE wildcards (%, _) so user input matches literally."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(LIBRARY_ID))
        uow.tracks.save(
            _track(
                TRACK_ID,
                LIBRARY_ID,
                current_path="A/1.flac",
                metadata=TrackMetadata(title="50% Off_Deal", artist="Artist", album="Album"),
            )
        )
        uow.tracks.save(
            _track(
                SECOND_TRACK_ID,
                LIBRARY_ID,
                current_path="B/1.flac",
                metadata=TrackMetadata(title="50X OffXDeal", artist="Artist", album="Album"),
            )
        )
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        literal_page = uow.tracks.query_page(
            None,
            track_id=None,
            search="50% Off_Deal",
            status=None,
            grouping=None,
            group_key=None,
            page=PageRequest(),
        )
        wildcard_page = uow.tracks.query_page(
            None,
            track_id=None,
            search="50X OffXDeal",
            status=None,
            grouping=None,
            group_key=None,
            page=PageRequest(),
        )

    assert tuple(track.track_id for track in literal_page.items) == (TRACK_ID,)
    assert tuple(track.track_id for track in wildcard_page.items) == (SECOND_TRACK_ID,)


def test_status_facets_orders_count_desc_then_value_asc(tmp_path: Path) -> None:
    """status_facets is ordered count DESC, then value ASC, scoped by an optional Library."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(LIBRARY_ID))
        uow.tracks.save(_track(TRACK_ID, LIBRARY_ID, current_path="A/1.flac", status=TrackStatus.ACTIVE))
        uow.tracks.save(_track(SECOND_TRACK_ID, LIBRARY_ID, current_path="B/1.flac", status=TrackStatus.ACTIVE))
        uow.tracks.save(_track(THIRD_TRACK_ID, LIBRARY_ID, current_path="C/1.flac", status=TrackStatus.REMOVED))
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        facets = uow.tracks.status_facets(LIBRARY_ID)

    assert [(facet.value, facet.count) for facet in facets] == [
        (TrackStatus.ACTIVE.value, 2),
        (TrackStatus.REMOVED.value, 1),
    ]


def test_search_and_status_scope_track_facets_and_hierarchy_groups(tmp_path: Path) -> None:
    """Query-scoped facets and groups use the same search/status predicates as Track lists."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(LIBRARY_ID))
        uow.tracks.save(
            _track(
                TRACK_ID,
                LIBRARY_ID,
                current_path="A/Match.flac",
                metadata=TrackMetadata(title="Match", artist="First", album="Album"),
            )
        )
        uow.tracks.save(
            _track(
                SECOND_TRACK_ID,
                LIBRARY_ID,
                current_path="B/Match.flac",
                status=TrackStatus.REMOVED,
                metadata=TrackMetadata(title="Match", artist="Second", album="Album"),
            )
        )
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        facets = uow.tracks.status_facets(LIBRARY_ID, search="Match")
        groups = uow.tracks.group_page(
            LIBRARY_ID,
            TrackGrouping.ARTIST,
            None,
            PageRequest(),
            search="Match",
            status=TrackStatus.REMOVED,
        )

    assert [(facet.value, facet.count) for facet in facets] == [
        (TrackStatus.ACTIVE.value, 1),
        (TrackStatus.REMOVED.value, 1),
    ]
    assert [(group.label, group.count) for group in groups.items] == [("Second", 1)]


def test_group_page_orders_and_paginates_with_count_then_key_keyset(tmp_path: Path) -> None:
    """group_page orders count DESC/key ASC and its (count, key) keyset visits every group once."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(LIBRARY_ID))
        uow.tracks.save(
            _track(TRACK_ID, LIBRARY_ID, current_path="A/1.flac", metadata=TrackMetadata(artist="Nova", album="Dawn"))
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
        uow.commit()

    visited_keys: list[str] = []
    visited_labels: list[str] = []
    cursor: tuple[str, ...] | None = None
    with SQLiteUnitOfWork(database_file) as uow:
        for _ in range(TWO_GROUP_TOTAL):
            page = uow.tracks.group_page(
                None,
                TrackGrouping.ARTIST_ALBUM,
                None,
                PageRequest(limit=1, cursor_key=cursor),
            )
            visited_keys.extend(group.key for group in page.items)
            visited_labels.extend(group.label for group in page.items)
            assert page.total == TWO_GROUP_TOTAL
            if page.next_cursor_key is None:
                break
            cursor = page.next_cursor_key

    assert visited_keys == ["Nova\x1fDawn", "Echo Collective\x1fDusk"]
    assert visited_labels == ["Nova — Dawn", "Echo Collective — Dusk"]


def test_hierarchy_group_page_uses_json_keys_metadata_fallbacks_and_parent_scope(tmp_path: Path) -> None:
    """Artist, album, and disc groups use stored metadata with opaque JSON parent keys."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
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
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        artist_page = uow.tracks.group_page(None, TrackGrouping.ARTIST, None, PageRequest())
        album_page = uow.tracks.group_page(
            None,
            TrackGrouping.ALBUM,
            HIERARCHY_ARTIST_KEY,
            PageRequest(),
        )
        disc_page = uow.tracks.group_page(
            None,
            TrackGrouping.DISC,
            HIERARCHY_ALBUM_KEY,
            PageRequest(),
        )

    artist_groups = {group.key: group for group in artist_page.items}
    album_groups = {group.key: group for group in album_page.items}
    disc_groups = {group.key: group for group in disc_page.items}
    assert artist_groups[HIERARCHY_ARTIST_KEY].label == HIERARCHY_ARTIST
    assert artist_groups[HIERARCHY_ARTIST_KEY].count == HIERARCHY_TRACK_COUNT
    assert album_groups[HIERARCHY_ALBUM_KEY].label == f"{HIERARCHY_ALBUM} — {HIERARCHY_YEAR}"
    assert album_groups[HIERARCHY_ALBUM_KEY].count == HIERARCHY_TRACK_COUNT
    assert disc_groups[HIERARCHY_DISC_KEY].label == f"Disc {HIERARCHY_DISC_NUMBER}"
    assert disc_groups[HIERARCHY_UNNUMBERED_DISC_KEY].label == "Unnumbered disc"


def test_group_member_query_uses_exact_json_key_and_music_order_keyset(tmp_path: Path) -> None:
    """A disc member query uses exact metadata membership and paginates in track-number order."""
    database_file = default_application_paths(tmp_path).database_file
    metadata_values = (
        (TRACK_ID, "A/2.flac", "Zulu", 2),
        (SECOND_TRACK_ID, "A/1.flac", "Beta", 1),
        (THIRD_TRACK_ID, "A/0.flac", "Alpha", 0),
        (FOURTH_TRACK_ID, "A/missing.flac", "Aardvark", None),
    )
    with SQLiteUnitOfWork(database_file) as uow:
        uow.libraries.save(_library(LIBRARY_ID))
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
        uow.tracks.save(
            _track(
                FIFTH_TRACK_ID,
                LIBRARY_ID,
                current_path="Other/1.flac",
                metadata=TrackMetadata(
                    title="Excluded",
                    artist=HIERARCHY_ARTIST,
                    album=HIERARCHY_ALBUM,
                    year=HIERARCHY_YEAR,
                    disc_number=2,
                    track_number=1,
                ),
            )
        )
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        first_page = uow.tracks.query_page(
            None,
            track_id=None,
            search=None,
            status=None,
            grouping=TrackGrouping.DISC,
            group_key=HIERARCHY_DISC_KEY,
            page=PageRequest(limit=TWO_ITEM_LIMIT),
        )
        second_page = uow.tracks.query_page(
            None,
            track_id=None,
            search=None,
            status=None,
            grouping=TrackGrouping.DISC,
            group_key=HIERARCHY_DISC_KEY,
            page=PageRequest(limit=TWO_ITEM_LIMIT, cursor_key=first_page.next_cursor_key),
        )

    assert tuple(track.track_id for track in first_page.items) == (SECOND_TRACK_ID, TRACK_ID)
    assert tuple(track.track_id for track in second_page.items) == (FOURTH_TRACK_ID, THIRD_TRACK_ID)
    assert first_page.total == FOUR_TRACK_GROUP_TOTAL
    assert second_page.next_cursor_key is None


def test_hierarchy_group_page_treats_ascii_tabs_and_newlines_as_blank_metadata(tmp_path: Path) -> None:
    """SQLite hierarchy grouping matches the shared ASCII whitespace blank-value contract."""
    database_file = default_application_paths(tmp_path).database_file
    with SQLiteUnitOfWork(database_file) as uow:
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
        uow.commit()

    with SQLiteUnitOfWork(database_file) as uow:
        artist_page = uow.tracks.group_page(None, TrackGrouping.ARTIST, None, PageRequest())
        album_page = uow.tracks.group_page(
            None,
            TrackGrouping.ALBUM,
            ASCII_WHITESPACE_ARTIST_KEY,
            PageRequest(),
        )

    assert [(group.key, group.label) for group in artist_page.items] == [
        (ASCII_WHITESPACE_ARTIST_KEY, ASCII_WHITESPACE_FALLBACK_ARTIST)
    ]
    assert [(group.key, group.label) for group in album_page.items] == [
        (ASCII_WHITESPACE_UNKNOWN_ALBUM_KEY, "(unknown)")
    ]


def _library(library_id: LibraryId) -> Library:
    return Library(
        library_id=library_id,
        root_path=f"/music/{library_id}",
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
