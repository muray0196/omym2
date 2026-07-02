"""
Summary: Implements artist ID generation CLI commands.
Why: Lets users generate editable artist IDs with optional fastText lookup.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from omym2.adapters.artist_ids.fasttext_language_detector import FastTextLanguageDetector
from omym2.adapters.artist_ids.musicbrainz_artist_lookup import MusicBrainzArtistLookup
from omym2.adapters.cli.commands.output import write_line, write_usage, write_validation_errors
from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.config.toml_config_store import TomlConfigStore
from omym2.features.artist_ids.dto import GenerateArtistIdsRequest
from omym2.features.artist_ids.usecases.generate_artist_ids import GenerateArtistIdsUseCase
from omym2.features.common_ports import ConfigStoreValidationError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import TextIO

    from omym2.features.artist_ids.ports import ArtistLanguageDetector, ArtistNameResolver

ERROR_EXIT_CODE = 1
FASTTEXT_MODEL_OPTION = "--fasttext-model"
FASTTEXT_OPTIONAL_DEPENDENCY_MESSAGE = "fastText support requires the optional fasttext package."
GENERATE_SUBCOMMAND = "generate"
OVERWRITE_OPTION = "--overwrite"
SUCCESS_EXIT_CODE = 0
USAGE_EXIT_CODE = 2
USAGE_MESSAGE = "Usage: omym2 artist-ids generate [--overwrite] [--fasttext-model PATH] ARTIST..."


@dataclass(frozen=True, slots=True)
class ArtistIdsCommandDependencies:
    """Optional dependency overrides for CLI tests."""

    language_detector: ArtistLanguageDetector | None = None
    artist_resolver: ArtistNameResolver | None = None


@dataclass(frozen=True, slots=True)
class _ParsedGenerateArgs:
    artist_names: tuple[str, ...]
    fasttext_model_path: Path | None
    overwrite: bool


def run_artist_ids_command(
    args: Sequence[str],
    stdout: TextIO,
    stderr: TextIO,
    config_path: Path | None = None,
    dependencies: ArtistIdsCommandDependencies | None = None,
) -> int:
    """Run artist ID subcommands and return a process exit code."""
    if not args or args[0] != GENERATE_SUBCOMMAND:
        write_usage(stderr, USAGE_MESSAGE)
        return USAGE_EXIT_CODE

    parsed_args = _parse_generate_args(tuple(args[1:]))
    if parsed_args is None:
        write_usage(stderr, USAGE_MESSAGE)
        return USAGE_EXIT_CODE

    command_dependencies = ArtistIdsCommandDependencies() if dependencies is None else dependencies
    try:
        detector = command_dependencies.language_detector or _language_detector(parsed_args.fasttext_model_path)
    except ModuleNotFoundError as exc:
        write_line(stderr, f"{FASTTEXT_OPTIONAL_DEPENDENCY_MESSAGE} ({exc})")
        return ERROR_EXIT_CODE
    resolver = command_dependencies.artist_resolver or MusicBrainzArtistLookup()
    usecase = GenerateArtistIdsUseCase(
        config_store=TomlConfigStore(config_path or default_application_paths().config_file),
        language_detector=detector,
        artist_resolver=resolver,
    )
    try:
        result = usecase.execute(GenerateArtistIdsRequest(parsed_args.artist_names, overwrite=parsed_args.overwrite))
    except ConfigStoreValidationError as exc:
        write_validation_errors(stderr, exc.errors)
        return ERROR_EXIT_CODE
    except OSError as exc:
        write_line(stderr, f"Config I/O error: {exc}")
        return ERROR_EXIT_CODE

    for entry in result.entries:
        status = "saved" if entry.saved else "preserved"
        write_line(stdout, f"{entry.source_artist}: {entry.artist_id} ({status}, from {entry.generation_artist})")
    return SUCCESS_EXIT_CODE


def _parse_generate_args(args: tuple[str, ...]) -> _ParsedGenerateArgs | None:
    artist_names: list[str] = []
    fasttext_model_path: Path | None = None
    overwrite = False
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == OVERWRITE_OPTION:
            overwrite = True
            index += 1
            continue
        if arg == FASTTEXT_MODEL_OPTION:
            if index + 1 >= len(args):
                return None
            fasttext_model_path = Path(args[index + 1])
            index += 2
            continue
        if arg.startswith("-"):
            return None
        artist_names.append(arg)
        index += 1
    if not artist_names:
        return None
    return _ParsedGenerateArgs(tuple(artist_names), fasttext_model_path, overwrite)


def _language_detector(model_path: Path | None) -> ArtistLanguageDetector:
    if model_path is None:
        return _NonJapaneseLanguageDetector()
    return FastTextLanguageDetector(model_path=model_path)


@dataclass(frozen=True, slots=True)
class _NonJapaneseLanguageDetector:
    """Detector used when the user did not provide a fastText model."""

    def is_japanese(self, text: str) -> bool:
        _ = text
        return False
