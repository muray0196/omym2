"""
Summary: Defines pure keyset pagination primitives shared by Web API list routes.
Why: Gives every list endpoint the same page request/response shape and cursor encoding
without duplicating pagination logic per route or per feature.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Sequence

DEFAULT_PAGE_LIMIT = 100
MAX_PAGE_LIMIT = 500
MIN_PAGE_LIMIT = 1
GROUP_CURSOR_KEY_LENGTH = 2  # a group-by cursor key is always a (count, key) 2-tuple

INVALID_CURSOR_MESSAGE = "Invalid cursor."
LIMIT_TOO_LOW_MESSAGE = f"limit must be >= {MIN_PAGE_LIMIT}"


@dataclass(frozen=True, slots=True)
class PageRequest:
    """Requested page shape for a keyset-paginated list."""

    limit: int = DEFAULT_PAGE_LIMIT
    cursor_key: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class Page[T]:
    """A returned page of items plus the cursor for the next page."""

    items: tuple[T, ...]
    next_cursor_key: tuple[str, ...] | None
    total: int


@dataclass(frozen=True, slots=True)
class GroupCount:
    """A single grouped row for a group-by list endpoint."""

    key: str
    label: str
    count: int


@dataclass(frozen=True, slots=True)
class FacetValue:
    """A single value/count pair for a facet endpoint."""

    value: str
    count: int


class CursorDecodeError(ValueError):
    """Raised when an opaque cursor string cannot be decoded to a keyset key."""


def encode_cursor(key: tuple[str, ...]) -> str:
    """Encode a decoded keyset key as an opaque base64url cursor string.

    The wire format is base64url (no padding) of the UTF-8 JSON encoding of
    `key` as a JSON array of strings. `decode_cursor` is the exact inverse.
    """
    payload = json.dumps(list(key), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def decode_cursor(text: str) -> tuple[str, ...]:
    """Decode an opaque cursor string produced by `encode_cursor`.

    Raises `CursorDecodeError` when `text` is not valid base64url, does not
    decode to valid UTF-8 JSON, or the JSON value is not a non-empty list of
    strings.
    """
    padding = "=" * (-len(text) % 4)
    try:
        payload = base64.urlsafe_b64decode(text + padding)
    except (binascii.Error, ValueError) as error:
        raise CursorDecodeError(INVALID_CURSOR_MESSAGE) from error

    try:
        decoded = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CursorDecodeError(INVALID_CURSOR_MESSAGE) from error

    try:
        parsed = cast("object", json.loads(decoded))
    except json.JSONDecodeError as error:
        raise CursorDecodeError(INVALID_CURSOR_MESSAGE) from error

    if not isinstance(parsed, list) or not parsed:
        raise CursorDecodeError(INVALID_CURSOR_MESSAGE)
    parsed_items = cast("list[object]", parsed)
    if not all(isinstance(part, str) for part in parsed_items):
        raise CursorDecodeError(INVALID_CURSOR_MESSAGE)

    return tuple(cast("list[str]", parsed_items))


def paginate_group_counts(groups: Sequence[GroupCount], page: PageRequest) -> Page[GroupCount]:
    """Paginate an in-memory sequence of GroupCounts with (count DESC, key ASC) keyset semantics.

    Mirrors the SQL group-by keyset contract (see `docs/contracts/web-api.md`
    Group Envelope) for callers that must compute groups in Python instead of
    SQL, e.g. because deriving the group key is a business rule. `groups` is
    sorted internally; callers do not need to pre-sort it. Raises
    `CursorDecodeError` for a malformed or wrong-arity `page.cursor_key`.
    """
    ordered = sorted(groups, key=lambda group: (-group.count, group.key))
    total = len(ordered)

    if page.cursor_key is not None:
        if len(page.cursor_key) != GROUP_CURSOR_KEY_LENGTH:
            raise CursorDecodeError(INVALID_CURSOR_MESSAGE)
        cursor_count_text, cursor_key_text = page.cursor_key
        try:
            cursor_count = int(cursor_count_text)
        except ValueError as error:
            raise CursorDecodeError(INVALID_CURSOR_MESSAGE) from error
        ordered = [
            group
            for group in ordered
            if group.count < cursor_count or (group.count == cursor_count and group.key > cursor_key_text)
        ]

    page_items = tuple(ordered[: page.limit])
    has_more = len(ordered) > page.limit
    next_cursor_key = (str(page_items[-1].count), page_items[-1].key) if has_more else None
    return Page(items=page_items, next_cursor_key=next_cursor_key, total=total)


def clamp_limit(raw: int | None) -> int:
    """Resolve a requested page limit to an effective, in-range limit.

    `None` resolves to `DEFAULT_PAGE_LIMIT`. Values from `MIN_PAGE_LIMIT` to
    `MAX_PAGE_LIMIT` are returned unchanged. Values above `MAX_PAGE_LIMIT` are
    clamped down to `MAX_PAGE_LIMIT`. Values below `MIN_PAGE_LIMIT` raise
    `ValueError`; callers at the route layer translate that into an HTTP 400
    response rather than silently substituting a default.
    """
    if raw is None:
        return DEFAULT_PAGE_LIMIT
    if raw < MIN_PAGE_LIMIT:
        raise ValueError(LIMIT_TOO_LOW_MESSAGE)
    if raw > MAX_PAGE_LIMIT:
        return MAX_PAGE_LIMIT
    return raw
