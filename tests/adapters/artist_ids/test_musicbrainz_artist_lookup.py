"""
Summary: Tests MusicBrainz artist lookup adapter behavior.
Why: Verifies HTTP contract, parsing, timeout, and rate limiting without network I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

from omym2.adapters.artist_ids.musicbrainz_artist_lookup import MusicBrainzArtistLookup
from omym2.config import MUSICBRAINZ_DEFAULT_USER_AGENT

if TYPE_CHECKING:
    from urllib.request import Request

EXPECTED_ALIAS = "Hikaru Utada"
JAPANESE_ARTIST = "宇多田ヒカル"
TIMEOUT_SECONDS = 2.5


def test_musicbrainz_lookup_prefers_english_latin_alias() -> None:
    """Lookup parses MusicBrainz JSON and prefers English Latin aliases."""
    opener = FakeOpener(
        """
        {
          "artists": [
            {
              "name": "宇多田ヒカル",
              "aliases": [
                {"name": "Utada Hikaru", "locale": "ja"},
                {"name": "Hikaru Utada", "locale": "en"}
              ]
            }
          ]
        }
        """.encode()
    )

    result = MusicBrainzArtistLookup(timeout_seconds=TIMEOUT_SECONDS, opener=opener).find_latin_artist_name(
        JAPANESE_ARTIST
    )

    assert result == EXPECTED_ALIAS
    assert opener.timeout_seconds == TIMEOUT_SECONDS
    assert opener.request is not None
    assert opener.request.headers["User-agent"] == MUSICBRAINZ_DEFAULT_USER_AGENT
    assert "artist%3A%22" in opener.request.full_url


def test_musicbrainz_lookup_rate_limits_subsequent_requests() -> None:
    """Lookup sleeps before a second request inside the configured interval."""
    opener = FakeOpener(b'{"artists": []}')
    clock = FakeClock(times=[10.0, 10.25, 10.25])
    sleeps: list[float] = []
    lookup = MusicBrainzArtistLookup(opener=opener, clock=clock, sleeper=sleeps.append)

    _ = lookup.find_latin_artist_name("first")
    _ = lookup.find_latin_artist_name("second")

    assert sleeps == [0.75]


@dataclass(slots=True)
class FakeResponse:
    """Minimal response context manager for urlopen fakes."""

    payload: bytes

    def read(self) -> bytes:
        """Return the configured response bytes."""
        return self.payload

    def __enter__(self) -> Self:
        """Return this fake response."""
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        """Close the fake response."""


@dataclass(slots=True)
class FakeOpener:
    """urlopen fake that records request details."""

    payload: bytes
    request: Request | None = None
    timeout_seconds: float | None = None

    def __call__(self, request: Request, timeout_seconds: float) -> FakeResponse:
        """Record request inputs and return a fake response."""
        self.request = request
        self.timeout_seconds = timeout_seconds
        return FakeResponse(self.payload)


@dataclass(slots=True)
class FakeClock:
    """Monotonic clock fake with predetermined values."""

    times: list[float]

    def __call__(self) -> float:
        """Return the next configured timestamp."""
        return self.times.pop(0)
