"""
Summary: Builds artist ID language detector and name resolver adapters.
Why: Moves the artist-ids CLI's private selection logic to a shared composition root.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from omym2.adapters.artist_ids.fasttext_language_detector import FastTextLanguageDetector
from omym2.adapters.artist_ids.musicbrainz_artist_lookup import MusicBrainzArtistLookup
from omym2.adapters.artist_ids.no_op_artist_name_resolver import NoOpArtistNameResolver
from omym2.adapters.artist_ids.no_op_language_detector import NoOpLanguageDetector
from omym2.adapters.cli.commands.artist_ids import ArtistIdsCommandPorts
from omym2.platform.runtime_context import runtime_context_for

if TYPE_CHECKING:
    from pathlib import Path

    from omym2.features.artist_ids.ports import ArtistLanguageDetector, ArtistNameResolver
    from omym2.platform.runtime_context import RuntimeContext


def language_detector_for_model(model_path: Path | None) -> ArtistLanguageDetector:
    """Select a fastText detector when a model path is given, else a no-op detector."""
    if model_path is None:
        return NoOpLanguageDetector()
    return FastTextLanguageDetector(model_path=model_path)


def default_artist_resolver() -> ArtistNameResolver:
    """Build the default MusicBrainz-backed artist name resolver."""
    return MusicBrainzArtistLookup()


def web_artist_language_detector() -> ArtistLanguageDetector:
    """Build the no-op language detector used by the Web adapter."""
    return NoOpLanguageDetector()


def web_artist_name_resolver() -> ArtistNameResolver:
    """Build the no-op artist name resolver used by the Web adapter."""
    return NoOpArtistNameResolver()


def artist_ids_command_ports_for(runtime: RuntimeContext) -> ArtistIdsCommandPorts:
    """Build artist-ids CLI ports from a shared RuntimeContext."""
    return ArtistIdsCommandPorts(
        config_store=runtime.config_store,
        language_detector_factory=language_detector_for_model,
        artist_resolver=default_artist_resolver(),
    )


def build_artist_ids_command_ports(config_path: Path | None = None) -> ArtistIdsCommandPorts:
    """Build artist-ids CLI ports directly from an optional config path."""
    return artist_ids_command_ports_for(runtime_context_for(config_path))
