"""
Summary: Resolves English or Latin artist names through MusicBrainz.
Why: Keeps HTTP, parsing, and rate limiting behind a feature port.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, Self, cast
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from omym2.config import (
    MUSICBRAINZ_API_BASE_URL,
    MUSICBRAINZ_ARTIST_SEARCH_LIMIT,
    MUSICBRAINZ_RATE_LIMIT_SECONDS,
    MUSICBRAINZ_TIMEOUT_SECONDS,
    MUSICBRAINZ_USER_AGENT,
)

type UrlOpen = Callable[[Request, float], "_HttpResponse"]
type Clock = Callable[[], float]
type Sleeper = Callable[[float], None]


class _HttpResponse(Protocol):
    """Minimum HTTP response surface used by the adapter."""

    def __enter__(self) -> Self:
        """Enter response context."""
        ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        """Exit response context."""
        ...

    def read(self) -> bytes:
        """Return response bytes."""
        ...


def _urlopen(request: Request, timeout: float) -> _HttpResponse:
    return cast("_HttpResponse", urlopen(request, timeout=timeout))  # noqa: S310 - URL is built from the MusicBrainz HTTPS base URL.


@dataclass(slots=True)
class MusicBrainzArtistLookup:
    """Look up artist names using the MusicBrainz web service."""

    base_url: str = MUSICBRAINZ_API_BASE_URL
    user_agent: str = MUSICBRAINZ_USER_AGENT
    timeout_seconds: float = MUSICBRAINZ_TIMEOUT_SECONDS
    rate_limit_seconds: float = MUSICBRAINZ_RATE_LIMIT_SECONDS
    search_limit: int = MUSICBRAINZ_ARTIST_SEARCH_LIMIT
    url_open: UrlOpen = _urlopen
    clock: Clock = time.monotonic
    sleeper: Sleeper = time.sleep
    _last_request_at: float | None = field(default=None, init=False)

    def english_or_latin_name(self, source_artist: str) -> str | None:
        """Return the best English or Latin artist name MusicBrainz provides."""
        query = source_artist.strip()
        if query == "":
            return None
        try:
            payload = self._request_artist_search(query)
        except OSError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError:
            return None
        return _select_artist_name(payload)

    def _request_artist_search(self, source_artist: str) -> object:
        self._rate_limit()
        query = urlencode({"query": source_artist, "fmt": "json", "limit": str(self.search_limit)})
        request = Request(  # noqa: S310 - URL is built from the MusicBrainz HTTPS base URL.
            f"{self.base_url.rstrip('/')}/artist?{query}",
            headers={"User-Agent": self.user_agent, "Accept": "application/json"},
        )
        with self.url_open(request, self.timeout_seconds) as response:
            raw_payload = response.read()
        self._last_request_at = self.clock()
        return cast("object", json.loads(raw_payload.decode("utf-8")))

    def _rate_limit(self) -> None:
        if self._last_request_at is None:
            return
        elapsed = self.clock() - self._last_request_at
        remaining = self.rate_limit_seconds - elapsed
        if remaining > 0:
            self.sleeper(remaining)


def _select_artist_name(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    payload_mapping = cast("dict[str, object]", payload)
    artists = payload_mapping.get("artists")
    if not isinstance(artists, list):
        return None
    artist_items = cast("list[object]", artists)
    for artist_item in artist_items:
        if not isinstance(artist_item, dict):
            continue
        artist = cast("dict[str, object]", artist_item)
        alias_name = _select_alias_name(artist.get("aliases"))
        if alias_name is not None:
            return alias_name
        for key in ("name", "sort-name"):
            value = artist.get(key)
            if _is_latin_name(value):
                return cast("str", value)
    return None


def _select_alias_name(aliases: object) -> str | None:
    if not isinstance(aliases, list):
        return None
    alias_items = cast("list[object]", aliases)
    for alias_item in alias_items:
        if not isinstance(alias_item, dict):
            continue
        alias = cast("dict[str, object]", alias_item)
        name = alias.get("name")
        locale = alias.get("locale")
        if isinstance(locale, str) and locale.lower().startswith("en") and _is_latin_name(name):
            return cast("str", name)
    for alias_item in alias_items:
        if not isinstance(alias_item, dict):
            continue
        alias = cast("dict[str, object]", alias_item)
        name = alias.get("name")
        if _is_latin_name(name):
            return cast("str", name)
    return None


def _is_latin_name(value: object) -> bool:
    return isinstance(value, str) and value.strip() != "" and value.isascii()
