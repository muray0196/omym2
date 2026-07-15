"""
Summary: Resolves artist display names through preferences, cache, and MusicBrainz.
Why: Produces deterministic path-facing names without changing embedded metadata.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING
from uuid import UUID

from omym2.config import (
    ARTIST_NAME_COMPOSITE_SEPARATOR,
    ARTIST_NAME_LANGUAGE_CONFIDENCE_MAX,
    ARTIST_NAME_LANGUAGE_CONFIDENCE_MIN,
    FASTTEXT_JAPANESE_LABEL,
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
from omym2.domain.services.artist_name import derive_artist_name_source_key
from omym2.features.artist_names.dto import ArtistNameAliasCandidate, ArtistNameProviderCandidate

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

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
        return self.resolve_many(request.source_names, preferences=request.preferences)

    def resolve_many(
        self,
        source_names: Sequence[str | None],
        *,
        preferences: Mapping[str, str] | None = None,
    ) -> tuple[ArtistNameResolution, ...]:
        """Resolve each input in order while deduplicating external work by source key."""
        batch = _prepare_batch(source_names, preferences)
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
                        ArtistNameResolutionProvenance.ACCEPTED_MUSICBRAINZ,
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
        if eligibility_issue is None:
            prediction = self.ports.language_predictor.predict_language(source_key)
            eligibility_issue = _prediction_issue(
                available=prediction.available,
                label=prediction.label,
                confidence=prediction.confidence,
            )
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
    preferences: Mapping[str, str] | None,
) -> _ResolutionBatch:
    sources = tuple(
        _SourceName(source_name=source_name, source_key=derive_artist_name_source_key(source_name))
        for source_name in source_names
    )
    resolutions: list[ArtistNameResolution | None] = [None] * len(sources)
    lookup_indexes_by_key: dict[str, list[int]] = {}
    preference_snapshot = dict(preferences or {})
    for index, source in enumerate(sources):
        preferred_name = _preferred_name(source.source_name, preference_snapshot)
        if preferred_name is not None:
            resolutions[index] = _preferred_resolution(source, preferred_name)
            continue
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
    return winner, ArtistNameResolutionProvenance.ACCEPTED_MUSICBRAINZ


def _preferred_name(source_name: str | None, preferences: Mapping[str, str]) -> str | None:
    if source_name is None or source_name not in preferences:
        return None
    return preferences[source_name]


def _preferred_resolution(source: _SourceName, preferred_name: str) -> ArtistNameResolution:
    return ArtistNameResolution(
        source_name=source.source_name,
        source_key=source.source_key,
        resolved_name=preferred_name,
        provenance=ArtistNameResolutionProvenance.USER_PREFERENCE,
    )


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
    if not _has_only_non_latin_alphabetic(source_key):
        return ArtistNameResolutionIssue.NON_LATIN_REQUIRED
    return None


def _prediction_issue(
    *,
    available: bool,
    label: str | None,
    confidence: float | None,
) -> ArtistNameResolutionIssue | None:
    if not available:
        return ArtistNameResolutionIssue.DETECTOR_UNAVAILABLE
    if label != FASTTEXT_JAPANESE_LABEL:
        return ArtistNameResolutionIssue.NOT_JAPANESE
    if (
        confidence is None
        or not isfinite(confidence)
        or not ARTIST_NAME_LANGUAGE_CONFIDENCE_MIN <= confidence <= ARTIST_NAME_LANGUAGE_CONFIDENCE_MAX
    ):
        return ArtistNameResolutionIssue.LOW_LANGUAGE_CONFIDENCE
    return None


def _has_only_non_latin_alphabetic(text: str) -> bool:
    alphabetic = tuple(character for character in text if character.isalpha())
    return bool(alphabetic) and all(not _is_latin_character(character) for character in alphabetic)


def _is_latin_text(text: str) -> bool:
    alphabetic = tuple(character for character in text if character.isalpha())
    return bool(alphabetic) and all(_is_latin_character(character) for character in alphabetic)


def _is_latin_character(character: str) -> bool:
    return "LATIN" in unicodedata.name(character, "")


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
    aliases_by_identity: dict[tuple[str, str], ArtistNameAliasCandidate] = {}
    for candidate in candidates:
        for alias in candidate.aliases:
            alias_identity = (alias.name, alias.locale or "")
            existing = aliases_by_identity.get(alias_identity)
            if existing is None or (alias.primary and not existing.primary):
                aliases_by_identity[alias_identity] = alias
    return ArtistNameProviderCandidate(
        provider_artist_id=identity,
        score=top_score,
        name=top_name,
        aliases=tuple(aliases_by_identity[key] for key in sorted(aliases_by_identity)),
    )


def _provider_identity(provider_artist_id: str) -> str:
    try:
        return str(UUID(provider_artist_id))
    except ValueError:
        return provider_artist_id


def _select_display_name(candidate: ArtistNameProviderCandidate) -> _SelectedDisplayName | None:
    aliases = _deduplicated_aliases(candidate.aliases)
    english_aliases = tuple(
        alias for alias in aliases if _is_english_locale(alias.locale) and _is_latin_text(alias.name)
    )
    if english_aliases:
        selected = english_aliases[0]
        return _SelectedDisplayName(selected.name, SelectedArtistNameKind.ALIAS, selected.locale)

    other_latin_aliases = tuple(
        alias for alias in aliases if not _is_english_locale(alias.locale) and _is_latin_text(alias.name)
    )
    if other_latin_aliases:
        selected = other_latin_aliases[0]
        return _SelectedDisplayName(selected.name, SelectedArtistNameKind.ALIAS, selected.locale)

    if _is_latin_text(candidate.name):
        return _SelectedDisplayName(candidate.name, SelectedArtistNameKind.NAME, None)
    return None


def _deduplicated_aliases(aliases: Sequence[ArtistNameAliasCandidate]) -> tuple[ArtistNameAliasCandidate, ...]:
    by_identity: dict[tuple[str, str], ArtistNameAliasCandidate] = {}
    for alias in aliases:
        key = (alias.name, alias.locale or "")
        if key not in by_identity:
            by_identity[key] = alias
    return tuple(by_identity[key] for key in sorted(by_identity))


def _is_english_locale(locale: str | None) -> bool:
    if locale is None:
        return False
    normalized = locale.casefold()
    return normalized == "en" or normalized.startswith("en-")
