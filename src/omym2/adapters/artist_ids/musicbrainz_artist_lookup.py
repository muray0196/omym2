"""
Summary: Implements MusicBrainz artist English-name lookup.
Why: Resolves Japanese artist text before deterministic artist ID generation.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol, Self, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from omym2.config import (
    MUSICBRAINZ_ARTIST_SEARCH_ENDPOINT,
    MUSICBRAINZ_DEFAULT_RESULT_LIMIT,
    MUSICBRAINZ_DEFAULT_TIMEOUT_SECONDS,
    MUSICBRAINZ_DEFAULT_USER_AGENT,
    MUSICBRAINZ_MIN_REQUEST_INTERVAL_SECONDS,
)

LATIN_TEXT_PATTERN = re.compile(r"[A-Za-z]")
LOOKUP_FAILED_MESSAGE = "MusicBrainz artist lookup failed:"
NON_LATIN_BLOCK_PATTERN = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
USER_AGENT_HEADER = "User-Agent"

type Clock = Callable[[], float]
type Sleeper = Callable[[float], None]
type UrlOpener = Callable[[Request, float], "ReadableResponse"]


class ReadableResponse(Protocol):
    """Small response contract needed by the MusicBrainz adapter."""

    def read(self) -> bytes:
        """Return response body bytes."""
        ...

    def __enter__(self) -> Self:
        """Open the response context."""
        ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        """Close the response context."""
        ...


class MusicBrainzLookupError(RuntimeError):
    """Raised when MusicBrainz lookup cannot complete."""


def _open_url(request: Request, timeout_seconds: float) -> ReadableResponse:
    return cast(
        "ReadableResponse",
        urlopen(request, timeout=timeout_seconds),  # noqa: S310 - MusicBrainz HTTPS lookup is intentional.
    )


@dataclass(slots=True)
class MusicBrainzArtistLookup:
    """Resolve preferred Latin artist names through MusicBrainz."""

    endpoint: str = MUSICBRAINZ_ARTIST_SEARCH_ENDPOINT
    user_agent: str = MUSICBRAINZ_DEFAULT_USER_AGENT
    timeout_seconds: float = MUSICBRAINZ_DEFAULT_TIMEOUT_SECONDS
    min_request_interval_seconds: float = MUSICBRAINZ_MIN_REQUEST_INTERVAL_SECONDS
    result_limit: int = MUSICBRAINZ_DEFAULT_RESULT_LIMIT
    clock: Clock = time.monotonic
    sleeper: Sleeper = time.sleep
    opener: UrlOpener = _open_url
    _last_request_at: float | None = field(default=None, init=False)

    def find_latin_artist_name(self, artist_name: str) -> str | None:
        """Return the best English/Latin artist name from MusicBrainz."""
        if artist_name.strip() == "":
            return None

        request = Request(  # noqa: S310 - MusicBrainz HTTPS lookup is intentional.
            f"{self.endpoint}?{urlencode(_query_params(artist_name, self.result_limit))}",
            headers={USER_AGENT_HEADER: self.user_agent},
        )
        self._wait_for_rate_limit()
        try:
            with self.opener(request, self.timeout_seconds) as response:
                payload = cast("object", json.loads(response.read().decode("utf-8")))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            message = f"{LOOKUP_FAILED_MESSAGE} {exc}"
            raise MusicBrainzLookupError(message) from exc
        finally:
            self._last_request_at = self.clock()

        return _preferred_latin_artist_name(payload)

    def _wait_for_rate_limit(self) -> None:
        if self._last_request_at is None:
            return
        elapsed = self.clock() - self._last_request_at
        remaining = self.min_request_interval_seconds - elapsed
        if remaining > 0:
            self.sleeper(remaining)


def _query_params(artist_name: str, result_limit: int) -> dict[str, str]:
    return {"fmt": "json", "limit": str(result_limit), "query": f'artist:"{artist_name}"'}


def _preferred_latin_artist_name(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    payload_mapping = cast("Mapping[str, object]", payload)
    artists = payload_mapping.get("artists")
    if not isinstance(artists, list):
        return None

    for artist in cast("Sequence[object]", artists):
        if not isinstance(artist, dict):
            continue
        artist_mapping = cast("Mapping[str, object]", artist)
        preferred_alias = _preferred_alias(artist_mapping.get("aliases"))
        if preferred_alias is not None:
            return preferred_alias
        artist_name = artist_mapping.get("name")
        if isinstance(artist_name, str) and _is_latin_name(artist_name):
            return artist_name
    return None


def _preferred_alias(raw_aliases: object) -> str | None:
    if not isinstance(raw_aliases, list):
        return None

    latin_aliases: list[str] = []
    for alias in cast("Sequence[object]", raw_aliases):
        if not isinstance(alias, dict):
            continue
        alias_mapping = cast("Mapping[str, object]", alias)
        name = alias_mapping.get("name")
        if not isinstance(name, str) or not _is_latin_name(name):
            continue
        if alias_mapping.get("locale") == "en":
            return name
        latin_aliases.append(name)
    if len(latin_aliases) == 0:
        return None
    return latin_aliases[0]


def _is_latin_name(value: str) -> bool:
    return LATIN_TEXT_PATTERN.search(value) is not None and NON_LATIN_BLOCK_PATTERN.search(value) is None
