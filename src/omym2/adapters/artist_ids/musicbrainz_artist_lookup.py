"""
Summary: Adapts MusicBrainz artist searches to raw naming-provider facts.
Why: Keeps HTTP, schema parsing, and rate limiting outside naming decisions.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from http.client import HTTPException
from math import isfinite
from typing import Protocol, Self, cast
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import UUID

from omym2.config import (
    DEFAULT_MUSICBRAINZ_RETRY_LIMIT,
    MUSICBRAINZ_API_BASE_URL,
    MUSICBRAINZ_ARTIST_SEARCH_LIMIT,
    MUSICBRAINZ_RATE_LIMIT_SECONDS,
    MUSICBRAINZ_TIMEOUT_SECONDS,
    MUSICBRAINZ_USER_AGENT,
)
from omym2.features.artist_names.dto import (
    ArtistNameAliasCandidate,
    ArtistNameProviderCandidate,
    ArtistNameSearchResult,
)

type UrlOpen = Callable[[Request, float], "_HttpResponse"]
type Clock = Callable[[], float]
type Sleeper = Callable[[float], None]

RATE_LIMIT_BELOW_PROVIDER_MINIMUM_MESSAGE = "MusicBrainz rate limiting must be at least the provider minimum."
INVALID_TIMEOUT_MESSAGE = "MusicBrainz timeout must be positive."
INVALID_RETRY_LIMIT_MESSAGE = "MusicBrainz retry limit must be non-negative."
INVALID_USER_AGENT_MESSAGE = "MusicBrainz user agent must not be empty."
RETRY_LOOP_EXHAUSTED_MESSAGE = "MusicBrainz retry loop exhausted without a result."
RETRYABLE_PROVIDER_ERRORS = (OSError, TimeoutError, HTTPException)


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


class ProviderRequestCadence(Protocol):
    """Coordinate the minimum delay between provider requests."""

    def wait_for_request(self, minimum_interval_seconds: float) -> None:
        """Wait until and reserve the next permitted provider request."""
        ...


def _urlopen(request: Request, timeout: float) -> _HttpResponse:
    return cast("_HttpResponse", urlopen(request, timeout=timeout))  # noqa: S310 - URL is built from the MusicBrainz HTTPS base URL.


@dataclass(slots=True)
class MusicBrainzArtistLookup:
    """Return raw MusicBrainz artist candidates without accepting a match."""

    base_url: str = MUSICBRAINZ_API_BASE_URL
    user_agent: str = MUSICBRAINZ_USER_AGENT
    timeout_seconds: float = MUSICBRAINZ_TIMEOUT_SECONDS
    retry_limit: int = DEFAULT_MUSICBRAINZ_RETRY_LIMIT
    rate_limit_seconds: float = MUSICBRAINZ_RATE_LIMIT_SECONDS
    search_limit: int = MUSICBRAINZ_ARTIST_SEARCH_LIMIT
    url_open: UrlOpen = _urlopen
    clock: Clock = time.monotonic
    sleeper: Sleeper = time.sleep
    request_cadence: ProviderRequestCadence | None = None
    _last_request_at: float | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        """Reject invalid provider identity and bounded request controls."""
        if self.user_agent.strip() == "":
            raise ValueError(INVALID_USER_AGENT_MESSAGE)
        if not isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError(INVALID_TIMEOUT_MESSAGE)
        if self.retry_limit < 0:
            raise ValueError(INVALID_RETRY_LIMIT_MESSAGE)
        if not isfinite(self.rate_limit_seconds) or self.rate_limit_seconds < MUSICBRAINZ_RATE_LIMIT_SECONDS:
            raise ValueError(RATE_LIMIT_BELOW_PROVIDER_MINIMUM_MESSAGE)

    def search_artists(self, source_name: str) -> ArtistNameSearchResult:
        """Return ordered raw artist candidates or an unavailable observation."""
        query = source_name.strip()
        if query == "":
            return ArtistNameSearchResult(available=True)
        try:
            payload = self._request_artist_search(query)
        except OSError, TimeoutError, HTTPException, json.JSONDecodeError, UnicodeDecodeError:
            return _unavailable_search_result()
        candidates = _parse_artist_candidates(payload)
        if candidates is None:
            return _unavailable_search_result()
        return ArtistNameSearchResult(available=True, candidates=candidates)

    def _request_artist_search(self, source_artist: str) -> object:
        query = urlencode({"query": source_artist, "fmt": "json", "limit": str(self.search_limit)})
        request = Request(  # noqa: S310 - URL is built from the MusicBrainz HTTPS base URL.
            f"{self.base_url.rstrip('/')}/artist?{query}",
            headers={"User-Agent": self.user_agent, "Accept": "application/json"},
        )
        for attempt in range(self.retry_limit + 1):
            try:
                self._rate_limit()
                with self.url_open(request, self.timeout_seconds) as response:
                    raw_payload = response.read()
                return cast("object", json.loads(raw_payload.decode("utf-8")))
            except RETRYABLE_PROVIDER_ERRORS:
                if attempt >= self.retry_limit:
                    raise
            finally:
                self._last_request_at = self.clock()
        raise AssertionError(RETRY_LOOP_EXHAUSTED_MESSAGE)

    def _rate_limit(self) -> None:
        if self.request_cadence is not None:
            self.request_cadence.wait_for_request(self.rate_limit_seconds)
            return
        if self._last_request_at is None:
            return
        elapsed = self.clock() - self._last_request_at
        remaining = self.rate_limit_seconds - elapsed
        if remaining > 0:
            self.sleeper(remaining)


def _parse_artist_candidates(payload: object) -> tuple[ArtistNameProviderCandidate, ...] | None:
    if not isinstance(payload, dict):
        return None
    payload_mapping = cast("dict[str, object]", payload)
    artists = payload_mapping.get("artists")
    if not isinstance(artists, list):
        return None
    artist_items = cast("list[object]", artists)
    candidates: list[ArtistNameProviderCandidate] = []
    for artist_item in artist_items:
        candidate = _parse_artist_candidate(artist_item)
        if candidate is None:
            return None
        candidates.append(candidate)
    return tuple(candidates)


def _parse_artist_candidate(value: object) -> ArtistNameProviderCandidate | None:
    if not isinstance(value, dict):
        return None
    artist = cast("dict[str, object]", value)
    provider_artist_id = _canonical_uuid(artist.get("id"))
    score = _parse_score(artist.get("score"))
    name = _non_empty_text(artist.get("name"))
    raw_sort_name = artist.get("sort-name")
    sort_name = None if raw_sort_name is None else _non_empty_text(raw_sort_name)
    aliases = _parse_aliases(artist.get("aliases"))
    if (
        provider_artist_id is None
        or score is None
        or name is None
        or (raw_sort_name is not None and sort_name is None)
        or aliases is None
    ):
        return None
    return ArtistNameProviderCandidate(
        provider_artist_id=provider_artist_id,
        score=score,
        name=name,
        sort_name=sort_name,
        aliases=aliases,
    )


def _parse_aliases(value: object) -> tuple[ArtistNameAliasCandidate, ...] | None:
    if value is None:
        return ()
    if not isinstance(value, list):
        return None
    alias_items = cast("list[object]", value)
    aliases: list[ArtistNameAliasCandidate] = []
    for alias_item in alias_items:
        alias = _parse_alias(alias_item)
        if alias is None:
            return None
        aliases.append(alias)
    return tuple(aliases)


def _parse_alias(value: object) -> ArtistNameAliasCandidate | None:
    if not isinstance(value, dict):
        return None
    alias = cast("dict[str, object]", value)
    name = _non_empty_text(alias.get("name"))
    raw_sort_name = alias.get("sort-name")
    sort_name = None if raw_sort_name is None else _non_empty_text(raw_sort_name)
    locale = alias.get("locale")
    raw_primary = alias.get("primary", False)
    if (
        name is None
        or (raw_sort_name is not None and sort_name is None)
        or (locale is not None and not isinstance(locale, str))
        or (raw_primary is not None and not isinstance(raw_primary, bool))
    ):
        return None
    return ArtistNameAliasCandidate(
        name=name,
        locale=locale,
        sort_name=sort_name,
        primary=raw_primary is True,
    )


def _canonical_uuid(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return str(UUID(value))
    except ValueError:
        return None


def _parse_score(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _non_empty_text(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() != "" else None


def _unavailable_search_result() -> ArtistNameSearchResult:
    return ArtistNameSearchResult(available=False)
