"""
Summary: Builds artist ID language detector and name resolver adapters.
Why: Moves the artist-ids CLI's private selection logic to a shared composition root.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from omym2.adapters.cli.commands.artist_ids import ArtistIdsCommandPorts
from omym2.features.artist_ids.usecases.generate_artist_ids import GenerateArtistIdsUseCase
from omym2.platform.artist_name_composition import (
    artist_name_resolver_for,
    default_artist_name_provider,
    language_predictor_for_model,
)
from omym2.platform.operation_composition import OperationRuntime
from omym2.platform.runtime_context import runtime_context_for

if TYPE_CHECKING:
    from pathlib import Path

    from omym2.features.artist_ids.dto import GenerateArtistIdsRequest, GenerateArtistIdsResult
    from omym2.features.artist_names.ports import ArtistLanguagePredictor, ArtistNameProvider
    from omym2.platform.runtime_context import RuntimeContext


def artist_ids_command_ports_for(runtime: RuntimeContext, operations: OperationRuntime) -> ArtistIdsCommandPorts:
    """Build artist-ids CLI ports from a shared RuntimeContext."""
    return ArtistIdsCommandPorts(
        generate_artist_ids=lambda request, predictor, provider: _generate_artist_ids(
            runtime, operations, request, predictor, provider
        ),
        language_predictor_factory=language_predictor_for_model,
        artist_name_provider=default_artist_name_provider(),
    )


def build_artist_ids_command_ports(
    config_path: Path | None = None,
    database_path: Path | None = None,
) -> ArtistIdsCommandPorts:
    """Build artist-ids CLI ports directly from optional state paths."""
    runtime = runtime_context_for(config_path, database_path)
    return artist_ids_command_ports_for(runtime, OperationRuntime(runtime))


def _generate_artist_ids(
    runtime: RuntimeContext,
    operations: OperationRuntime,
    request: GenerateArtistIdsRequest,
    predictor: ArtistLanguagePredictor,
    provider: ArtistNameProvider,
) -> GenerateArtistIdsResult:
    return operations.execute_exclusive(
        "generate_artist_ids",
        lambda: GenerateArtistIdsUseCase(
            config_store=runtime.config_store,
            artist_name_resolver=artist_name_resolver_for(runtime.database_file, predictor, provider),
        ).execute(request),
    )
