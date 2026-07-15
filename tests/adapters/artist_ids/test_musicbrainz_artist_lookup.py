"""
Summary: Tests the MusicBrainz artist provider adapter.
Why: Verifies raw candidate parsing, availability, and request throttling.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from http.client import IncompleteRead
from typing import TYPE_CHECKING, Self
from urllib.parse import parse_qs, urlparse

import pytest

from omym2.adapters.artist_ids.musicbrainz_artist_lookup import MusicBrainzArtistLookup
from omym2.features.artist_names.dto import (
    ArtistNameAliasCandidate,
    ArtistNameProviderCandidate,
    ArtistNameSearchResult,
)

if TYPE_CHECKING:
    from urllib.request import Request


@dataclass(slots=True)
class _Response:
    payload: object

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


@dataclass(frozen=True, slots=True)
class _TruncatedResponse:
    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def read(self) -> bytes:
        raise IncompleteRead(partial=b"{", expected=1)


@dataclass(slots=True)
class _RawResponse:
    payload: bytes

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


@dataclass(slots=True)
class _Recorder:
    payload: object
    requests: list[Request]
    timeouts: list[float]

    def open(self, request: Request, timeout: float) -> _Response:
        self.requests.append(request)
        self.timeouts.append(timeout)
        return _Response(self.payload)


MUSICBRAINZ_ARTIST_ID = "db2f4f3a-f0c2-4c96-bea3-636f4b44f57b"


def test_musicbrainz_lookup_returns_ordered_raw_candidate_facts() -> None:
    """The adapter parses identity, score, name, and aliases without accepting one."""
    recorder = _Recorder(
        {
            "artists": [
                {
                    "id": MUSICBRAINZ_ARTIST_ID.upper(),
                    "score": "100",
                    "name": "米津玄師",
                    "aliases": [
                        {"name": "Kenshi Yonezu", "locale": "en", "primary": True},
                        {"name": "Yonezu Kenshi", "locale": "ja-Latn", "primary": None},
                    ],
                }
            ]
        },
        [],
        [],
    )

    result = MusicBrainzArtistLookup(url_open=recorder.open, timeout_seconds=2.5).search_artists("米津玄師")

    assert result == ArtistNameSearchResult(
        available=True,
        candidates=(
            ArtistNameProviderCandidate(
                provider_artist_id=MUSICBRAINZ_ARTIST_ID,
                score=100,
                name="米津玄師",
                aliases=(
                    ArtistNameAliasCandidate(name="Kenshi Yonezu", locale="en", primary=True),
                    ArtistNameAliasCandidate(name="Yonezu Kenshi", locale="ja-Latn"),
                ),
            ),
        ),
    )
    assert recorder.timeouts == [2.5]
    assert recorder.requests[0].headers["User-agent"].startswith("OMYM2/")
    assert recorder.requests[0].headers["Accept"] == "application/json"
    query = parse_qs(urlparse(recorder.requests[0].full_url).query)
    assert query == {"fmt": ["json"], "limit": ["5"], "query": ["米津玄師"]}


def test_musicbrainz_lookup_returns_available_empty_result() -> None:
    """A valid empty provider response remains distinct from unavailability."""
    recorder = _Recorder({"artists": []}, [], [])

    result = MusicBrainzArtistLookup(url_open=recorder.open).search_artists("unknown")

    assert result == ArtistNameSearchResult(available=True)


def test_musicbrainz_lookup_reports_transport_error_unavailable() -> None:
    """A failed HTTP request is not misreported as a valid lookup miss."""

    def raise_os_error(_request: Request, _timeout: float) -> _Response:
        message = "network unavailable"
        raise OSError(message)

    result = MusicBrainzArtistLookup(url_open=raise_os_error).search_artists("米津玄師")

    assert result == ArtistNameSearchResult(available=False)


def test_musicbrainz_lookup_reports_truncated_response_unavailable() -> None:
    """A partial HTTP body is a non-fatal provider failure."""

    def open_truncated(_request: Request, _timeout: float) -> _TruncatedResponse:
        return _TruncatedResponse()

    result = MusicBrainzArtistLookup(url_open=open_truncated).search_artists("米津玄師")

    assert result == ArtistNameSearchResult(available=False)


def test_musicbrainz_lookup_reports_invalid_json_unavailable() -> None:
    """A malformed JSON response is provider unavailability, not an empty match."""

    def open_invalid_json(_request: Request, _timeout: float) -> _RawResponse:
        return _RawResponse(b"not-json")

    result = MusicBrainzArtistLookup(url_open=open_invalid_json).search_artists("Artist")

    assert result == ArtistNameSearchResult(available=False)


@pytest.mark.parametrize(
    "payload",
    [
        {"unexpected": []},
        {"artists": [{"id": "not-a-uuid", "score": 100, "name": "Artist"}]},
        {"artists": [{"id": MUSICBRAINZ_ARTIST_ID, "score": "not-a-score", "name": "Artist"}]},
    ],
)
def test_musicbrainz_lookup_reports_schema_failure_unavailable(payload: object) -> None:
    """Malformed provider JSON cannot cross the adapter as valid candidates."""
    recorder = _Recorder(payload, [], [])

    result = MusicBrainzArtistLookup(url_open=recorder.open).search_artists("Artist")

    assert result == ArtistNameSearchResult(available=False)


def test_musicbrainz_lookup_rate_limits_after_failed_attempt() -> None:
    """A transport failure still delays the next provider request."""
    clock_values = iter((10.0, 10.2, 11.0))
    sleeps: list[float] = []

    def raise_os_error(_request: Request, _timeout: float) -> _Response:
        message = "network unavailable"
        raise OSError(message)

    lookup = MusicBrainzArtistLookup(
        url_open=raise_os_error,
        clock=lambda: next(clock_values),
        sleeper=sleeps.append,
        rate_limit_seconds=1.0,
    )

    assert lookup.search_artists("A") == ArtistNameSearchResult(available=False)
    assert lookup.search_artists("B") == ArtistNameSearchResult(available=False)

    assert sleeps == pytest.approx([0.8])


def test_musicbrainz_lookup_rejects_rate_limit_below_provider_minimum() -> None:
    """Callers cannot configure a request cadence faster than MusicBrainz permits."""

    with pytest.raises(ValueError, match="provider minimum"):
        _ = MusicBrainzArtistLookup(rate_limit_seconds=0.5)
