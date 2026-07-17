"""
Summary: Resolves artist names through editable mappings and MusicBrainz.
Why: Builds one reusable original-to-English mapping without changing embedded metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from omym2.config import (
    ARTIST_NAME_COMPOSITE_SEPARATOR,
    MUSICBRAINZ_ARTIST_AMBIGUITY_MARGIN,
    MUSICBRAINZ_ARTIST_MATCH_SCORE_MIN,
)
from omym2.domain.models.accepted_artist_name import (
    AcceptedArtistName,
    ArtistNameProvider,
    SelectedArtistNameKind,
)
from omym2.domain.models.artist_name_resolution import (
    ArtistNameResolution,
    ArtistNameResolutionIssue,
    ArtistNameResolutionProvenance,
)
from omym2.domain.services.artist_name import (
    contains_non_latin_artist_name_letters,
    derive_artist_name_source_key,
    is_usable_english_artist_name,
)
from omym2.features.artist_names.dto import ArtistNameAliasCandidate, ArtistNameProviderCandidate

if TYPE_CHECKING:
    from collections.abc import Sequence

    from omym2.features.artist_names.dto import ResolveArtistNamesRequest
    from omym2.features.artist_names.ports import ResolveArtistNamesPorts
    from omym2.features.common_ports import UnitOfWork

STICKY_ACCEPTED_NAME_MISSING_MESSAGE = "Sticky artist-name insertion lost without a persisted winner."
INCOMPLETE_RESOLUTION_MESSAGE = "Artist-name resolution did not produce every requested outcome."
ORIGINAL_FALLBACK_ISSUE_REQUIRED_MESSAGE = "Original artist-name fallback requires a resolution issue."


@dataclass(frozen=True, slots=True)
class ResolveArtistNamesUseCase:
    """Resolve ordered source values while keeping provider I/O outside transactions."""

    ports: ResolveArtistNamesPorts

    def execute(self, request: ResolveArtistNamesRequest) -> tuple[ArtistNameResolution, ...]:
        """Resolve one typed batch request."""
        return self.resolve_many(request.source_names)

    def resolve_many(
        self,
        source_names: Sequence[str | None],
    ) -> tuple[ArtistNameResolution, ...]:
        """Resolve each input in order while deduplicating external work by source key."""
        batch = _prepare_batch(source_names)
        if not batch.lookup_indexes_by_key:
            return _completed_resolutions(batch.resolutions)
        with self.ports.uow.usecase_scope():
            uncached_keys = self._read_cached_names(batch)
            pending = self._resolve_uncached_keys(batch, uncached_keys)
            self._persist_new_names(batch, pending)
        return _completed_resolutions(batch.resolutions)

    def _read_cached_names(self, batch: _ResolutionBatch) -> tuple[str, ...]:
        uncached_keys: list[str] = []
        with self.ports.uow as uow:
            for source_key, indexes in batch.lookup_indexes_by_key.items():
                accepted_name = uow.accepted_artist_names.find_by_source_key(source_key)
                if accepted_name is None:
                    uncached_keys.append(source_key)
                    continue
                for index in indexes:
                    batch.resolutions[index] = _accepted_resolution(
                        batch.sources[index],
                        accepted_name,
                        _cached_provenance(accepted_name),
                    )
        return tuple(uncached_keys)

    def _resolve_uncached_keys(
        self,
        batch: _ResolutionBatch,
        uncached_keys: Sequence[str],
    ) -> tuple[_PendingAcceptedName, ...]:
        pending: list[_PendingAcceptedName] = []
        for source_key in uncached_keys:
            indexes = tuple(batch.lookup_indexes_by_key[source_key])
            resolution, accepted_name = self._resolve_uncached(batch.sources[indexes[0]])
            if accepted_name is not None:
                pending.append(_PendingAcceptedName(indexes=indexes, accepted_name=accepted_name))
                continue
            if resolution.issue is None:
                raise RuntimeError(ORIGINAL_FALLBACK_ISSUE_REQUIRED_MESSAGE)
            for index in indexes:
                batch.resolutions[index] = _original_resolution(batch.sources[index], resolution.issue)
        return tuple(pending)

    def _persist_new_names(
        self,
        batch: _ResolutionBatch,
        pending: Sequence[_PendingAcceptedName],
    ) -> None:
        if not pending:
            return
        with self.ports.uow as uow:
            for item in pending:
                winner, provenance = _insert_or_read_winner(uow, item.accepted_name)
                for index in item.indexes:
                    batch.resolutions[index] = _accepted_resolution(batch.sources[index], winner, provenance)
            uow.commit()

    def _resolve_uncached(
        self,
        source: _SourceName,
    ) -> tuple[ArtistNameResolution, AcceptedArtistName | None]:
        source_name = source.source_name
        source_key = source.source_key
        if source_name is None or source_key is None:
            return _original_resolution(source, ArtistNameResolutionIssue.MISSING_SOURCE), None
        eligibility_issue = _source_eligibility_issue(source_key)
        if eligibility_issue is None and not self.ports.automatic_lookup_enabled:
            eligibility_issue = ArtistNameResolutionIssue.AUTOMATIC_LOOKUP_DISABLED
        if eligibility_issue is not None:
            return _original_resolution(source, eligibility_issue), None

        return self._resolve_provider(source, source_name, source_key)

    def _resolve_provider(
        self,
        source: _SourceName,
        source_name: str,
        source_key: str,
    ) -> tuple[ArtistNameResolution, AcceptedArtistName | None]:
        """Search MusicBrainz and construct one accepted cache candidate."""

        search_result = self.ports.artist_name_provider.search_artists(source_key)
        if not search_result.available:
            return _original_resolution(source, ArtistNameResolutionIssue.PROVIDER_UNAVAILABLE), None

        selected_candidate, selection_issue = _accepted_candidate(search_result.candidates)
        if selected_candidate is None:
            return _original_resolution(
                source,
                selection_issue or ArtistNameResolutionIssue.NO_CONFIDENT_MATCH,
            ), None

        selected_name = _select_display_name(selected_candidate)
        if selected_name is None:
            return _original_resolution(source, ArtistNameResolutionIssue.NO_CONFIDENT_MATCH), None

        try:
            accepted_name = AcceptedArtistName(
                source_key=source_key,
                source_name=source_name,
                resolved_name=selected_name.name,
                provider=ArtistNameProvider.MUSICBRAINZ,
                provider_artist_id=selected_candidate.provider_artist_id,
                selected_name_kind=selected_name.kind,
                selected_locale=selected_name.locale,
                accepted_at=self.ports.clock.now(),
            )
        except ValueError:
            return _original_resolution(source, ArtistNameResolutionIssue.NO_CONFIDENT_MATCH), None
        return _accepted_resolution(
            source, accepted_name, ArtistNameResolutionProvenance.NEW_MUSICBRAINZ
        ), accepted_name


@dataclass(frozen=True, slots=True)
class _SourceName:
    source_name: str | None
    source_key: str | None


@dataclass(slots=True)
class _ResolutionBatch:
    sources: tuple[_SourceName, ...]
    resolutions: list[ArtistNameResolution | None]
    lookup_indexes_by_key: dict[str, list[int]]


@dataclass(frozen=True, slots=True)
class _PendingAcceptedName:
    indexes: tuple[int, ...]
    accepted_name: AcceptedArtistName


@dataclass(frozen=True, slots=True)
class _SelectedDisplayName:
    name: str
    kind: SelectedArtistNameKind
    locale: str | None


def _prepare_batch(
    source_names: Sequence[str | None],
) -> _ResolutionBatch:
    sources = tuple(
        _SourceName(source_name=source_name, source_key=derive_artist_name_source_key(source_name))
        for source_name in source_names
    )
    resolutions: list[ArtistNameResolution | None] = [None] * len(sources)
    lookup_indexes_by_key: dict[str, list[int]] = {}
    for index, source in enumerate(sources):
        source_key = source.source_key
        if source_key is None:
            resolutions[index] = _original_resolution(source, ArtistNameResolutionIssue.MISSING_SOURCE)
            continue
        lookup_indexes_by_key.setdefault(source_key, []).append(index)
    return _ResolutionBatch(sources, resolutions, lookup_indexes_by_key)


def _completed_resolutions(
    resolutions: Sequence[ArtistNameResolution | None],
) -> tuple[ArtistNameResolution, ...]:
    if any(resolution is None for resolution in resolutions):
        raise RuntimeError(INCOMPLETE_RESOLUTION_MESSAGE)
    return tuple(resolution for resolution in resolutions if resolution is not None)


def _insert_or_read_winner(
    uow: UnitOfWork,
    accepted_name: AcceptedArtistName,
) -> tuple[AcceptedArtistName, ArtistNameResolutionProvenance]:
    if uow.accepted_artist_names.insert_if_absent(accepted_name):
        return accepted_name, ArtistNameResolutionProvenance.NEW_MUSICBRAINZ
    winner = uow.accepted_artist_names.find_by_source_key(accepted_name.source_key)
    if winner is None:
        raise RuntimeError(STICKY_ACCEPTED_NAME_MISSING_MESSAGE)
    return winner, _cached_provenance(winner)


def _cached_provenance(accepted_name: AcceptedArtistName) -> ArtistNameResolutionProvenance:
    if accepted_name.provider is ArtistNameProvider.USER:
        return ArtistNameResolutionProvenance.USER_PREFERENCE
    return ArtistNameResolutionProvenance.ACCEPTED_MUSICBRAINZ


def _accepted_resolution(
    source: _SourceName,
    accepted_name: AcceptedArtistName,
    provenance: ArtistNameResolutionProvenance,
) -> ArtistNameResolution:
    return ArtistNameResolution(
        source_name=source.source_name,
        source_key=source.source_key,
        resolved_name=accepted_name.resolved_name,
        provenance=provenance,
        accepted_name=accepted_name,
    )


def _original_resolution(source: _SourceName, issue: ArtistNameResolutionIssue) -> ArtistNameResolution:
    return ArtistNameResolution(
        source_name=source.source_name,
        source_key=source.source_key,
        resolved_name=source.source_name,
        provenance=ArtistNameResolutionProvenance.ORIGINAL,
        issue=issue,
    )


def _source_eligibility_issue(source_key: str) -> ArtistNameResolutionIssue | None:
    if ARTIST_NAME_COMPOSITE_SEPARATOR in source_key:
        return ArtistNameResolutionIssue.COMPOSITE_UNSUPPORTED
    if not contains_non_latin_artist_name_letters(source_key):
        return ArtistNameResolutionIssue.ROMANIZATION_NOT_REQUIRED
    return None


def _accepted_candidate(
    candidates: Sequence[ArtistNameProviderCandidate],
) -> tuple[ArtistNameProviderCandidate | None, ArtistNameResolutionIssue | None]:
    ranked = _distinct_ranked_candidates(candidates)
    if not ranked or ranked[0].score < MUSICBRAINZ_ARTIST_MATCH_SCORE_MIN:
        return None, ArtistNameResolutionIssue.NO_CONFIDENT_MATCH
    top = ranked[0]
    if len(ranked) > 1 and top.score - ranked[1].score <= MUSICBRAINZ_ARTIST_AMBIGUITY_MARGIN:
        return None, ArtistNameResolutionIssue.AMBIGUOUS_MATCH
    return top, None


def _distinct_ranked_candidates(
    candidates: Sequence[ArtistNameProviderCandidate],
) -> tuple[ArtistNameProviderCandidate, ...]:
    by_identity: dict[str, list[ArtistNameProviderCandidate]] = {}
    for candidate in candidates:
        identity = _provider_identity(candidate.provider_artist_id)
        by_identity.setdefault(identity, []).append(candidate)
    merged = tuple(
        _merge_identity_candidates(identity, tuple(identity_candidates))
        for identity, identity_candidates in by_identity.items()
    )
    return tuple(
        sorted(
            merged,
            key=lambda candidate: (-candidate.score, candidate.provider_artist_id, candidate.name),
        )
    )


def _merge_identity_candidates(
    identity: str,
    candidates: Sequence[ArtistNameProviderCandidate],
) -> ArtistNameProviderCandidate:
    top_score = max(candidate.score for candidate in candidates)
    top_name = min(candidate.name for candidate in candidates if candidate.score == top_score)
    top_sort_names = tuple(
        candidate.sort_name
        for candidate in candidates
        if candidate.score == top_score and candidate.sort_name is not None
    )
    aliases_by_identity: dict[tuple[str, str], ArtistNameAliasCandidate] = {}
    for candidate in candidates:
        for alias in candidate.aliases:
            alias_identity = (alias.name, alias.locale or "")
            existing = aliases_by_identity.get(alias_identity)
            aliases_by_identity[alias_identity] = alias if existing is None else _merge_aliases(existing, alias)
    return ArtistNameProviderCandidate(
        provider_artist_id=identity,
        score=top_score,
        name=top_name,
        sort_name=min(top_sort_names) if top_sort_names else None,
        aliases=tuple(aliases_by_identity[key] for key in sorted(aliases_by_identity)),
    )


def _provider_identity(provider_artist_id: str) -> str:
    try:
        return str(UUID(provider_artist_id))
    except ValueError:
        return provider_artist_id


def _select_display_name(candidate: ArtistNameProviderCandidate) -> _SelectedDisplayName | None:
    aliases = _deduplicated_aliases(candidate.aliases)
    japanese_latin_alias = _primary_japanese_latin_alias(aliases)
    if japanese_latin_alias is not None:
        return japanese_latin_alias

    preferred_order_name = _normalized_sort_display_name(candidate.sort_name)
    if preferred_order_name is not None:
        return _SelectedDisplayName(preferred_order_name, SelectedArtistNameKind.SORT_NAME, None)
    return None


def _deduplicated_aliases(aliases: Sequence[ArtistNameAliasCandidate]) -> tuple[ArtistNameAliasCandidate, ...]:
    by_identity: dict[tuple[str, str], ArtistNameAliasCandidate] = {}
    for alias in aliases:
        key = (alias.name, alias.locale or "")
        existing = by_identity.get(key)
        by_identity[key] = alias if existing is None else _merge_aliases(existing, alias)
    return tuple(by_identity[key] for key in sorted(by_identity))


def _merge_aliases(
    first: ArtistNameAliasCandidate,
    second: ArtistNameAliasCandidate,
) -> ArtistNameAliasCandidate:
    sort_names = tuple(value for value in (first.sort_name, second.sort_name) if value is not None)
    return ArtistNameAliasCandidate(
        name=first.name,
        locale=first.locale,
        sort_name=min(sort_names) if sort_names else None,
        primary=first.primary or second.primary,
    )


def _primary_japanese_latin_alias(
    aliases: Sequence[ArtistNameAliasCandidate],
) -> _SelectedDisplayName | None:
    selections: list[tuple[bool, str, ArtistNameAliasCandidate]] = []
    for alias in aliases:
        if not alias.primary or not _is_japanese_latin_locale(alias.locale):
            continue
        normalized_sort_name = _normalized_sort_display_name(alias.sort_name)
        if normalized_sort_name is not None:
            selections.append((False, normalized_sort_name, alias))
        elif is_usable_english_artist_name(alias.name):
            selections.append((True, alias.name, alias))
    if not selections:
        return None
    used_alias_name, selected_name, selected_alias = min(
        selections,
        key=lambda item: (item[0], item[1].casefold(), item[1], item[2].name),
    )
    selected_kind = SelectedArtistNameKind.ALIAS if used_alias_name else SelectedArtistNameKind.ALIAS_SORT_NAME
    return _SelectedDisplayName(selected_name, selected_kind, selected_alias.locale)


def _is_japanese_latin_locale(locale: str | None) -> bool:
    return locale is not None and locale.casefold().replace("_", "-") == "ja-latn"


def _normalized_sort_display_name(sort_name: str | None) -> str | None:
    if sort_name is None:
        return None
    normalized = " ".join(sort_name.replace(",", " ").split())
    return normalized if is_usable_english_artist_name(normalized) else None
