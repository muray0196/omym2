"""
Summary: Tests deterministic artist ID generation.
Why: Protects user-facing path/config values from algorithm drift.
"""

from __future__ import annotations

from omym2.domain.services.artist_id import ArtistIdGenerator


class TestArtistIdGenerator:
    """Test cases for ArtistIdGenerator class."""

    def test_generate_empty_input(self) -> None:
        """Test ID generation with empty input."""
        assert ArtistIdGenerator.generate(None) == "NOART"
        assert ArtistIdGenerator.generate("") == "NOART"

    def test_generate_english(self) -> None:
        """Test ID generation with English text."""
        assert ArtistIdGenerator.generate("John Smith") == "JOHNSMTH"
        assert ArtistIdGenerator.generate("John-Smith") == "JOHNSMTH"
        assert ArtistIdGenerator.generate("123 John Smith") == "123JHNSM"
        assert ArtistIdGenerator.generate("Jo") == "JO"
        assert ArtistIdGenerator.generate("John Jacob Smith") == "JHNJCBSM"
        assert ArtistIdGenerator.generate("On the Ant") == "ONTHEANT"

    def test_generate_multi_artist(self) -> None:
        """Multiple artists receive length-balanced quotas while preserving order."""
        assert ArtistIdGenerator.generate("John Smith, Jane Doe") == "JHSMJAND"

    def test_generate_multi_artist_hyphenated_segments(self) -> None:
        """Hyphen-separated segments remain balanced but respect input order."""
        assert ArtistIdGenerator.generate("Michael Jackson, More More Jump") == "MCJCMRMJ"

    def test_generate_multi_artist_preserves_initial_vowel(self) -> None:
        """Initial vowels for subsequent artists remain in the identifier."""
        assert ArtistIdGenerator.generate("kaf, isekaijoucho") == "KAFISKJC"

    def test_generate_multi_artist_respects_input_order(self) -> None:
        """Switching artist order changes allocation as expected."""
        assert ArtistIdGenerator.generate("isekaijoucho, kaf") == "ISKJCKAF"
        assert ArtistIdGenerator.generate("Jane Doe, John Smith") == "JANDJHSM"

    def test_generate_multi_artist_inserts_vowels_in_place(self) -> None:
        """Fallback vowels re-enter at their original positions within each artist."""
        assert ArtistIdGenerator.generate("kaf, kafu") == "KAFKAFU"

    def test_generate_multi_artist_round_robin_segments(self) -> None:
        """Round-robin allocation mirrors single-artist progression across artists."""
        artists = "Kuramoto China, Shinosawa Hiro, Tsukimura Temari"
        assert ArtistIdGenerator.generate(artists) == "KRCSHHTT"

    def test_generate_edge_cases(self) -> None:
        """Test ID generation with edge cases."""
        assert ArtistIdGenerator.generate("!@#$%") == ArtistIdGenerator.FALLBACK_ID
        assert ArtistIdGenerator.generate("   ") == "NOART"
        assert ArtistIdGenerator.generate("12345") == "12345"
        assert ArtistIdGenerator.generate("JoHn SmItH") == "JOHNSMTH"

    def test_generate_sparse_consonants(self) -> None:
        """Scarce-consonant names retain all words within the configured cap."""
        assert ArtistIdGenerator.generate("Fujii Kaze") == "FUJIKAZE"
        assert ArtistIdGenerator.generate("Michael-Jackson") == "MCHLJCKS"

        abc_id = ArtistIdGenerator.generate("A-B-C")
        assert abc_id == "ABC"
        assert all(char in abc_id for char in "ABC")
        assert len(abc_id) <= ArtistIdGenerator.ID_LENGT
