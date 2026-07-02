"""
Summary: Implements artist ID generation CLI commands.
Why: Exposes fastText/MusicBrainz-backed config entry generation to users.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.adapters.artist_ids.fasttext_language_detector import FastTextLanguageDetector, FastTextLanguageDetectorError
from omym2.adapters.artist_ids.musicbrainz_artist_lookup import MusicBrainzArtistLookup, MusicBrainzLookupError
from omym2.adapters.cli.commands.output import write_line, write_usage, write_validation_errors
from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.config.toml_config_store import TomlConfigStore
from omym2.features.artist_ids.dto import ArtistIdGenerationRequest
from omym2.features.artist_ids.ports import ArtistIdPorts
from omym2.features.artist_ids.usecases.generate_artist_ids import GenerateArtistIdsUseCase
from omym2.features.common_ports import ConfigStoreValidationError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path
    from typing import TextIO

ERROR_EXIT_CODE = 1
GENERATE_SUBCOMMAND = "generate"
MODEL_OPTION = "--fasttext-model"
OVERWRITE_OPTION = "--overwrite"
SUCCESS_EXIT_CODE = 0
USAGE_EXIT_CODE = 2
USAGE_MESSAGE = "Usage: omym2 artist-ids generate --fasttext-model MODEL [--overwrite] ARTIST..."


@dataclass(frozen=True, slots=True)
class _GenerateArgs:
    model_path: str
    overwrite_existing: bool
    artist_names: tuple[str, ...]


def run_artist_ids_command(
    args: Sequence[str],
    stdout: TextIO,
    stderr: TextIO,
    config_path: Path | None = None,
) -> int:
    """Run artist ID subcommands and return a process exit code."""
    if len(args) == 0 or args[0] != GENERATE_SUBCOMMAND:
        write_usage(stderr, USAGE_MESSAGE)
        return USAGE_EXIT_CODE

    parsed_args = _parse_generate_args(tuple(args[1:]))
    if parsed_args is None:
        write_usage(stderr, USAGE_MESSAGE)
        return USAGE_EXIT_CODE

    store = TomlConfigStore(config_path or default_application_paths().config_file)
    ports = ArtistIdPorts(
        config_store=store,
        language_detector=FastTextLanguageDetector(parsed_args.model_path),
        musicbrainz_lookup=MusicBrainzArtistLookup(),
    )
    try:
        result = GenerateArtistIdsUseCase(ports).execute(
            ArtistIdGenerationRequest(
                artist_names=parsed_args.artist_names,
                overwrite_existing=parsed_args.overwrite_existing,
            )
        )
    except (ConfigStoreValidationError, FastTextLanguageDetectorError, MusicBrainzLookupError, OSError) as exc:
        write_validation_errors(stderr, _error_messages(exc))
        return ERROR_EXIT_CODE

    for entry in result.entries:
        status = "preserved" if entry.preserved_existing else "saved"
        write_line(stdout, f"{status}: {entry.source_artist} = {entry.artist_id}")
    return SUCCESS_EXIT_CODE


def _parse_generate_args(args: tuple[str, ...]) -> _GenerateArgs | None:
    model_path: str | None = None
    overwrite_existing = False
    artist_names: list[str] = []
    index = 0
    while index < len(args):
        value = args[index]
        if value == OVERWRITE_OPTION:
            overwrite_existing = True
            index += 1
            continue
        if value == MODEL_OPTION:
            if index + 1 >= len(args):
                return None
            model_path = args[index + 1]
            index += 2
            continue
        artist_names.append(value)
        index += 1

    if model_path is None or len(artist_names) == 0:
        return None
    return _GenerateArgs(
        model_path=model_path,
        overwrite_existing=overwrite_existing,
        artist_names=tuple(artist_names),
    )


def _error_messages(
    exc: ConfigStoreValidationError | FastTextLanguageDetectorError | MusicBrainzLookupError | OSError,
) -> tuple[str, ...]:
    if isinstance(exc, ConfigStoreValidationError):
        return exc.errors
    return (str(exc),)
