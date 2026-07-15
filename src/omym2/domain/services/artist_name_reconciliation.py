"""
Summary: Detects artist-name changes that require whole-Library reconciliation.
Why: Prevents partial Plans from creating mixed canonical artist paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath
from typing import TYPE_CHECKING

from omym2.domain.services.album_disc import infer_album_disc_totals
from omym2.domain.services.album_year import metadata_with_resolved_album_year, resolve_album_years
from omym2.domain.services.artist_name import ArtistNameProjection, derive_artist_name_source_key

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from omym2.domain.models.app_config import AppConfig
    from omym2.domain.models.artist_name_resolution import ArtistNameResolution
    from omym2.domain.models.track import Track
    from omym2.domain.models.track_metadata import TrackMetadata
    from omym2.domain.services.path_policy import PathPolicy


@dataclass(frozen=True, slots=True)
class _PlannedArtistNameChanges:
    """Resolved names that can affect matching existing raw values."""

    exact_names: Mapping[str, str]
    names_by_source_key: Mapping[str, str]


def artist_name_reconciliation_required(
    *,
    unreconciled_tracks: Sequence[Track],
    planned_resolutions: Sequence[ArtistNameResolution],
    effective_metadata_batch: Sequence[TrackMetadata],
    config: AppConfig,
    path_policy: PathPolicy,
) -> bool:
    """Return whether planned naming would leave an active Track at an obsolete path."""
    changes = _planned_artist_name_changes(planned_resolutions, config.artist_names.preferences)
    if not changes.exact_names and not changes.names_by_source_key:
        return False

    resolved_years = resolve_album_years(
        effective_metadata_batch,
        config.path_policy,
        config.metadata.album_year_resolution,
    )
    resolved_metadata_batch = tuple(
        metadata_with_resolved_album_year(metadata, config.path_policy, resolved_years)
        for metadata in effective_metadata_batch
    )
    album_disc_totals = infer_album_disc_totals(
        resolved_metadata_batch,
        unknown_artist=config.path_policy.unknown_artist,
        unknown_album=config.path_policy.unknown_album,
    )

    for track in unreconciled_tracks:
        metadata = track.metadata
        original_projection = ArtistNameProjection(
            artist=metadata.artist,
            album_artist=metadata.album_artist,
        )
        resolved_projection = ArtistNameProjection(
            artist=_resolved_artist_name(metadata.artist, config.artist_names.preferences, changes),
            album_artist=_resolved_artist_name(
                metadata.album_artist,
                config.artist_names.preferences,
                changes,
            ),
        )
        if resolved_projection == original_projection:
            continue

        resolved_metadata = metadata_with_resolved_album_year(
            metadata,
            config.path_policy,
            resolved_years,
        )
        file_extension = PurePath(track.current_path).suffix
        try:
            original_target = path_policy.canonical_path(
                resolved_metadata,
                file_extension,
                album_disc_total=album_disc_totals.for_metadata(resolved_metadata),
                artist_names=original_projection,
            )
            resolved_target = path_policy.canonical_path(
                resolved_metadata,
                file_extension,
                album_disc_total=album_disc_totals.for_metadata(resolved_metadata),
                artist_names=resolved_projection,
            )
        except ValueError:
            return True
        if original_target == resolved_target:
            continue
        if any(path != resolved_target for path in (track.current_path, track.canonical_path)):
            return True

    return False


def _planned_artist_name_changes(
    resolutions: Sequence[ArtistNameResolution],
    preferences: Mapping[str, str] | None,
) -> _PlannedArtistNameChanges:
    exact_names: dict[str, str] = {}
    names_by_source_key: dict[str, str] = {}
    for resolution in resolutions:
        source_name = resolution.source_name
        source_key = resolution.source_key
        resolved_name = resolution.resolved_name
        if resolved_name is None or resolved_name == source_name:
            continue
        if source_name is not None and preferences is not None and source_name in preferences:
            _ = exact_names.setdefault(source_name, resolved_name)
        elif source_key is not None:
            _ = names_by_source_key.setdefault(source_key, resolved_name)
    return _PlannedArtistNameChanges(
        exact_names=exact_names,
        names_by_source_key=names_by_source_key,
    )


def _resolved_artist_name(
    source_name: str | None,
    preferences: Mapping[str, str] | None,
    changes: _PlannedArtistNameChanges,
) -> str | None:
    if source_name is None:
        return None
    exact_name = changes.exact_names.get(source_name)
    if exact_name is not None:
        return exact_name
    source_key = derive_artist_name_source_key(source_name)
    if source_key is None or source_key not in changes.names_by_source_key:
        return source_name
    if preferences is not None and source_name in preferences:
        return preferences[source_name]
    return changes.names_by_source_key[source_key]
