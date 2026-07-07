"""
Summary: Resolves shared application paths and stateful adapters for one run.
Why: Gives platform composition builders one config store and metadata reader to reuse.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from omym2.adapters.config.application_paths import default_application_paths
from omym2.adapters.config.toml_config_store import TomlConfigStore
from omym2.adapters.metadata.mutagen_reader import MutagenMetadataReader

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class RuntimeContext:
    """Resolved application paths and shared stateful adapters for one process run."""

    config_file: Path
    database_file: Path
    config_store: TomlConfigStore
    metadata_reader: MutagenMetadataReader


def runtime_context_for(config_path: Path | None = None, database_path: Path | None = None) -> RuntimeContext:
    """Resolve application paths once and construct one shared config store and metadata reader."""
    app_paths = default_application_paths()
    config_file = config_path or app_paths.config_file
    database_file = database_path or app_paths.database_file
    return RuntimeContext(
        config_file=config_file,
        database_file=database_file,
        config_store=TomlConfigStore(config_file),
        metadata_reader=MutagenMetadataReader(),
    )
