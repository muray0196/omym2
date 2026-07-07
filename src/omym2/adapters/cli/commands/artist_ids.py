"""
Summary: Implements artist ID generation CLI commands.
Why: Lets users generate editable artist IDs with optional fastText lookup.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from omym2.adapters.cli.commands.output import write_line, write_usage, write_validation_errors
from omym2.features.artist_ids.dto import GenerateArtistIdsRequest
from omym2.features.artist_ids.usecases.generate_artist_ids import GenerateArtistIdsUseCase
from omym2.features.common_ports import ConfigStoreValidationError

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import TextIO

    from omym2.features.artist_ids.ports import ArtistLanguageDetector, ArtistNameResolver
    from omym2.features.common_ports import ConfigStore

ERROR_EXIT_CODE = 1
FASTTEXT_MODEL_OPTION = "--fasttext-model"
FASTTEXT_MODEL_LOAD_ERROR_MESSAGE = "fastText model load failed."
FASTTEXT_OPTIONAL_DEPENDENCY_MESSAGE = "fastText support requires the optional fasttext package."
FASTTEXT_MODEL_LOAD_ERROR_TYPES = (OSError, RuntimeError, ValueError)
GENERATE_SUBCOMMAND = "generate"
OVERWRITE_OPTION = "--overwrite"
SUCCESS_EXIT_CODE = 0
USAGE_EXIT_CODE = 2
USAGE_MESSAGE = "Usage: omym2 artist-ids generate [--overwrite] [--fasttext-model PATH] ARTIST..."


@dataclass(frozen=True, slots=True)
class ArtistIdsCommandPorts:
    """Ports injected for artist ID generation."""

    config_store: ConfigStore
    language_detector_factory: Callable[[Path | None], ArtistLanguageDetector]
    artist_resolver: ArtistNameResolver


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
    ports: ArtistIdsCommandPorts,
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
    detector, detector_error = _command_language_detector(ports, command_dependencies, parsed_args.fasttext_model_path)
    if detector_error is not None or detector is None:
        write_line(stderr, detector_error or FASTTEXT_MODEL_LOAD_ERROR_MESSAGE)
        return ERROR_EXIT_CODE

    resolver = command_dependencies.artist_resolver or ports.artist_resolver
    usecase = GenerateArtistIdsUseCase(
        config_store=ports.config_store,
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


def _command_language_detector(
    ports: ArtistIdsCommandPorts,
    dependencies: ArtistIdsCommandDependencies,
    fasttext_model_path: Path | None,
) -> tuple[ArtistLanguageDetector | None, str | None]:
    if dependencies.language_detector is not None:
        return dependencies.language_detector, None
    try:
        return ports.language_detector_factory(fasttext_model_path), None
    except ModuleNotFoundError as exc:
        return None, f"{FASTTEXT_OPTIONAL_DEPENDENCY_MESSAGE} ({exc})"
    except FASTTEXT_MODEL_LOAD_ERROR_TYPES as exc:
        return None, f"{FASTTEXT_MODEL_LOAD_ERROR_MESSAGE} ({exc})"
