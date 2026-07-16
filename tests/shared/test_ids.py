"""
Summary: Tests typed ID helper behavior.
Why: Ensures stable IDs are UUIDv7-backed and path-independent.
"""

from __future__ import annotations

from uuid import UUID

from omym2.shared.ids import (
    id_to_string,
    is_uuid7,
    new_companion_asset_id,
    new_library_id,
    new_track_id,
    parse_uuid,
)

EXPECTED_UUID_VERSION = 7


def test_library_id_is_generated_by_uuid7_helper() -> None:
    """Library IDs are generated as UUIDv7 values."""
    library_id = new_library_id()

    assert isinstance(library_id, UUID)
    assert library_id.version == EXPECTED_UUID_VERSION
    assert is_uuid7(library_id)


def test_track_id_is_generated_by_uuid7_helper() -> None:
    """Track IDs are generated as UUIDv7 values."""
    track_id = new_track_id()

    assert isinstance(track_id, UUID)
    assert track_id.version == EXPECTED_UUID_VERSION
    assert is_uuid7(track_id)


def test_companion_asset_id_is_generated_by_uuid7_helper() -> None:
    """Companion asset IDs are generated independently as UUIDv7 values."""
    companion_asset_id = new_companion_asset_id()

    assert isinstance(companion_asset_id, UUID)
    assert companion_asset_id.version == EXPECTED_UUID_VERSION
    assert is_uuid7(companion_asset_id)


def test_uuid_string_round_trip_keeps_full_identifier() -> None:
    """Persisted ID strings round-trip without shortening."""
    track_id = new_track_id()

    parsed_track_id = parse_uuid(id_to_string(track_id))

    assert parsed_track_id == track_id
