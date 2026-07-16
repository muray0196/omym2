"""
Summary: Tests deterministic artist ID generation.
Why: Protects user-facing path/config values from algorithm drift.
"""

from __future__ import annotations

from omym2.config import DEFAULT_ARTIST_ID_FALLBACK, DEFAULT_ARTIST_ID_MAX_LENGTH
from omym2.domain.services.artist_id import generate_artist_id


class TestGenerateArtistId:
    """Test cases for the deterministic artist-ID function."""

    def test_generate_empty_input(self) -> None:
        """Test ID generation with empty input."""
        assert generate_artist_id(None) == "NOART"
        assert generate_artist_id("") == "NOART"

    def test_generate_english(self) -> None:
        """Test ID generation with English text."""
        assert generate_artist_id("John Smith") == "JOHNSMTH"
        assert generate_artist_id("John-Smith") == "JOHNSMTH"
        assert generate_artist_id("123 John Smith") == "123JHNSM"
        assert generate_artist_id("Jo") == "JO"
        assert generate_artist_id("John Jacob Smith") == "JHNJCBSM"
        assert generate_artist_id("On the Ant") == "ONTHEANT"

    def test_generate_multi_artist(self) -> None:
        """Multiple artists receive length-balanced quotas while preserving order."""
        assert generate_artist_id("John Smith, Jane Doe") == "JHSMJAND"

    def test_generate_multi_artist_hyphenated_segments(self) -> None:
        """Hyphen-separated segments remain balanced but respect input order."""
        assert generate_artist_id("Michael Jackson, More More Jump") == "MCJCMRMJ"

    def test_generate_multi_artist_preserves_initial_vowel(self) -> None:
        """Initial vowels for subsequent artists remain in the identifier."""
        assert generate_artist_id("kaf, isekaijoucho") == "KAFISKJC"

    def test_generate_multi_artist_respects_input_order(self) -> None:
        """Switching artist order changes allocation as expected."""
        assert generate_artist_id("isekaijoucho, kaf") == "ISKJCKAF"
        assert generate_artist_id("Jane Doe, John Smith") == "JANDJHSM"

    def test_generate_multi_artist_inserts_vowels_in_place(self) -> None:
        """Fallback vowels re-enter at their original positions within each artist."""
        assert generate_artist_id("kaf, kafu") == "KAFKAFU"

    def test_generate_multi_artist_round_robin_segments(self) -> None:
        """Round-robin allocation mirrors single-artist progression across artists."""
        artists = "Kuramoto China, Shinosawa Hiro, Tsukimura Temari"
        assert generate_artist_id(artists) == "KRCSHHTT"

    def test_generate_edge_cases(self) -> None:
        """Test ID generation with edge cases."""
        assert generate_artist_id("!@#$%") == DEFAULT_ARTIST_ID_FALLBACK
        assert generate_artist_id("   ") == "NOART"
        assert generate_artist_id("12345") == "12345"
        assert generate_artist_id("JoHn SmItH") == "JOHNSMTH"

    def test_generate_sparse_consonants(self) -> None:
        """Scarce-consonant names retain all words within the configured cap."""
        assert generate_artist_id("Fujii Kaze") == "FUJIKAZE"
        assert generate_artist_id("Michael-Jackson") == "MCHLJCKS"

        abc_id = generate_artist_id("A-B-C")
        assert abc_id == "ABC"
        assert all(char in abc_id for char in "ABC")
        assert len(abc_id) <= DEFAULT_ARTIST_ID_MAX_LENGTH
