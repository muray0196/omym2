"""
Summary: Tests the keyset pagination primitives.
Why: Ensures cursor encoding round-trips, malformed cursors are rejected, and limit
clamping matches the documented Web API contract before routes depend on it.
"""

from __future__ import annotations

import base64

import pytest

from omym2.shared.pagination import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    MIN_PAGE_LIMIT,
    CursorDecodeError,
    FacetValue,
    GroupCount,
    Page,
    PageRequest,
    clamp_limit,
    decode_cursor,
    encode_cursor,
)

MID_RANGE_LIMIT = 50
PAGE_ITEM_COUNT = 2

SIMPLE_KEY = ("2026-07-09T00:00:00+00:00", "01ARZ3NDEKTSV4RRFFQ69G5FAV")
UNICODE_KEY = ("米津玄師/アルバム", "曲名")
SLASH_KEY = ("Artist/With/Slashes", "track-1")
EMPTY_STRING_ELEMENT_KEY = ("", "non-empty")


@pytest.mark.parametrize("key", [SIMPLE_KEY, UNICODE_KEY, SLASH_KEY, EMPTY_STRING_ELEMENT_KEY])
def test_cursor_round_trips_through_encode_and_decode(key: tuple[str, ...]) -> None:
    """encode_cursor followed by decode_cursor returns the original key."""
    cursor = encode_cursor(key)

    assert decode_cursor(cursor) == key


def test_encode_cursor_produces_url_safe_text() -> None:
    """Encoded cursors contain only URL-safe base64 characters (no padding)."""
    cursor = encode_cursor(SLASH_KEY)

    assert "=" not in cursor
    assert all(char.isalnum() or char in "-_" for char in cursor)


def test_decode_cursor_rejects_invalid_base64() -> None:
    """Text that is not valid base64url raises CursorDecodeError."""
    with pytest.raises(CursorDecodeError):
        _ = decode_cursor("not base64!!! url safe???")


def test_decode_cursor_rejects_non_json_payload() -> None:
    """Valid base64 that does not decode to JSON raises CursorDecodeError."""
    garbage = base64.urlsafe_b64encode(b"not json at all").rstrip(b"=").decode("ascii")

    with pytest.raises(CursorDecodeError):
        _ = decode_cursor(garbage)


def test_decode_cursor_rejects_json_that_is_not_a_string_list() -> None:
    """JSON values that are not a list of strings raise CursorDecodeError."""
    not_a_list = base64.urlsafe_b64encode(b'{"a": 1}').rstrip(b"=").decode("ascii")
    list_of_numbers = base64.urlsafe_b64encode(b"[1, 2]").rstrip(b"=").decode("ascii")

    with pytest.raises(CursorDecodeError):
        _ = decode_cursor(not_a_list)
    with pytest.raises(CursorDecodeError):
        _ = decode_cursor(list_of_numbers)


def test_decode_cursor_rejects_empty_list() -> None:
    """An encoded empty array raises CursorDecodeError."""
    empty_list = base64.urlsafe_b64encode(b"[]").rstrip(b"=").decode("ascii")

    with pytest.raises(CursorDecodeError):
        _ = decode_cursor(empty_list)


def test_clamp_limit_returns_default_for_none() -> None:
    """A missing limit resolves to DEFAULT_PAGE_LIMIT."""
    assert clamp_limit(None) == DEFAULT_PAGE_LIMIT


def test_clamp_limit_keeps_in_range_values_unchanged() -> None:
    """Values within [MIN_PAGE_LIMIT, MAX_PAGE_LIMIT] pass through unchanged."""
    assert clamp_limit(MIN_PAGE_LIMIT) == MIN_PAGE_LIMIT
    assert clamp_limit(MID_RANGE_LIMIT) == MID_RANGE_LIMIT
    assert clamp_limit(MAX_PAGE_LIMIT) == MAX_PAGE_LIMIT


def test_clamp_limit_clamps_values_above_maximum() -> None:
    """Values above MAX_PAGE_LIMIT are clamped down instead of rejected."""
    assert clamp_limit(MAX_PAGE_LIMIT + 1) == MAX_PAGE_LIMIT
    assert clamp_limit(1_000_000) == MAX_PAGE_LIMIT


def test_clamp_limit_rejects_values_below_minimum() -> None:
    """Values below MIN_PAGE_LIMIT raise ValueError for the route layer to translate."""
    with pytest.raises(ValueError, match="limit"):
        _ = clamp_limit(0)
    with pytest.raises(ValueError, match="limit"):
        _ = clamp_limit(-1)


def test_page_request_defaults_to_first_page() -> None:
    """A default PageRequest asks for the first page at the default limit."""
    request = PageRequest()

    assert request.limit == DEFAULT_PAGE_LIMIT
    assert request.cursor_key is None


def test_page_holds_items_next_cursor_key_and_total() -> None:
    """Page stores its items, the next cursor key, and the filtered total."""
    page: Page[str] = Page(items=("a", "b"), next_cursor_key=("b",), total=PAGE_ITEM_COUNT)

    assert page.items == ("a", "b")
    assert page.next_cursor_key == ("b",)
    assert page.total == PAGE_ITEM_COUNT


def test_group_count_and_facet_value_are_plain_field_holders() -> None:
    """GroupCount and FacetValue expose their documented fields."""
    group = GroupCount(key="artist-a", label="Artist A", count=3)
    facet = FacetValue(value="active", count=7)

    assert (group.key, group.label, group.count) == ("artist-a", "Artist A", 3)
    assert (facet.value, facet.count) == ("active", 7)
