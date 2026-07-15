"""
Summary: Resolves shared application paths and stateful adapters for one run.
Why: Gives composition one Config, metadata, lock, and optional naming runtime.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from omym2.adapters.config.application_paths import ApplicationPaths, default_application_paths
from omym2.adapters.config.toml_config_store import TomlConfigStore
from omym2.adapters.fs.exclusive_operation_lock import FilesystemExclusiveOperationLock
from omym2.adapters.metadata.mutagen_reader import MutagenMetadataReader
from omym2.config import ARTIST_NAME_FASTTEXT_MODEL_PATH_ENVIRONMENT_VARIABLE, DATA_DIRECTORY_NAME
from omym2.platform.artist_name_composition import (
    automatic_language_predictor_for_model,
    default_artist_name_provider,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from omym2.features.artist_names.ports import ArtistLanguagePredictor, ArtistNameProvider


@dataclass(frozen=True, slots=True)
class RuntimeContext:
    """Resolved application paths and shared stateful adapters for one process run."""

    application_root: Path
    config_file: Path
    database_file: Path
    config_store: TomlConfigStore
    metadata_reader: MutagenMetadataReader
    exclusive_operation_lock: FilesystemExclusiveOperationLock
    artist_name_language_predictor: ArtistLanguagePredictor
    artist_name_provider: ArtistNameProvider


def runtime_context_for(
    config_path: Path | None = None,
    database_path: Path | None = None,
    *,
    environment: Mapping[str, str] | None = None,
) -> RuntimeContext:
    """Resolve application paths once and construct one shared config store and metadata reader."""
    app_paths = default_application_paths()
    config_file = config_path or app_paths.config_file
    database_file = database_path or app_paths.database_file
    application_root = _application_root(database_file)
    resolved_paths = ApplicationPaths(application_root)
    runtime_environment = os.environ if environment is None else environment
    model_path = _artist_name_model_path(runtime_environment)
    return RuntimeContext(
        application_root=application_root,
        config_file=config_file,
        database_file=database_file,
        config_store=TomlConfigStore(config_file),
        metadata_reader=MutagenMetadataReader(),
        exclusive_operation_lock=FilesystemExclusiveOperationLock(resolved_paths.exclusive_operation_lock_file),
        artist_name_language_predictor=automatic_language_predictor_for_model(model_path),
        artist_name_provider=default_artist_name_provider(),
    )


def _application_root(database_file: Path) -> Path:
    """Anchor exclusion to the effective DB identity shared by every state-changing flow."""
    database_directory = database_file.parent
    return database_directory.parent if database_directory.name == DATA_DIRECTORY_NAME else database_directory


def _artist_name_model_path(environment: Mapping[str, str]) -> Path | None:
    raw_model_path = environment.get(ARTIST_NAME_FASTTEXT_MODEL_PATH_ENVIRONMENT_VARIABLE)
    if raw_model_path is None or raw_model_path.strip() == "":
        return None
    return Path(raw_model_path.strip())
