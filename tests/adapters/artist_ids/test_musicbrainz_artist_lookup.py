"""
Summary: Tests MusicBrainz artist lookup adapter.
Why: Verifies HTTP bounds, headers, parsing, and rate limiting.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

from omym2.adapters.artist_ids.musicbrainz_artist_lookup import MusicBrainzArtistLookup

if TYPE_CHECKING:
    from urllib.request import Request


@dataclass(slots=True)
class _Response:
    payload: dict[str, object]

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


@dataclass(slots=True)
class _Recorder:
    payload: dict[str, object]
    requests: list[Request]
    timeouts: list[float]

    def open(self, request: Request, timeout: float) -> _Response:
        self.requests.append(request)
        self.timeouts.append(timeout)
        return _Response(self.payload)


def test_musicbrainz_lookup_prefers_english_alias() -> None:
    """English aliases are preferred over the source artist name."""
    recorder = _Recorder(
        {
            "artists": [
                {
                    "name": "米津玄師",
                    "aliases": [
                        {"name": "Kenshi Yonezu", "locale": "en"},
                        {"name": "Yonezu Kenshi", "locale": "ja-Latn"},
                    ],
                }
            ]
        },
        [],
        [],
    )

    result = MusicBrainzArtistLookup(url_open=recorder.open, timeout_seconds=2.5).english_or_latin_name("米津玄師")

    assert result == "Kenshi Yonezu"
    assert recorder.timeouts == [2.5]
    assert recorder.requests[0].headers["User-agent"].startswith("OMYM2/")


def test_musicbrainz_lookup_returns_none_on_transport_error() -> None:
    """HTTP errors are handled as lookup misses."""

    def raise_os_error(_request: Request, _timeout: float) -> _Response:
        message = "network unavailable"
        raise OSError(message)

    result = MusicBrainzArtistLookup(url_open=raise_os_error).english_or_latin_name("米津玄師")

    assert result is None


def test_musicbrainz_lookup_rate_limits_between_requests() -> None:
    """The adapter sleeps when requests are closer than the configured limit."""
    recorder = _Recorder({"artists": []}, [], [])
    clock_values = iter((10.0, 10.0, 10.2, 10.2))
    sleeps: list[float] = []
    lookup = MusicBrainzArtistLookup(
        url_open=recorder.open,
        clock=lambda: next(clock_values),
        sleeper=sleeps.append,
        rate_limit_seconds=1.0,
    )

    assert lookup.english_or_latin_name("A") is None
    assert lookup.english_or_latin_name("B") is None

    assert sleeps == [1.0]
