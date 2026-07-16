"""
Summary: Tests shared artist display-name resolution orchestration.
Why: Proves precedence, eligibility, matching, caching, and transaction bounds.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Self, override

import pytest

from omym2.config import ARTIST_NAME_LANGUAGE_CONFIDENCE_MIN
from omym2.domain.models.accepted_artist_name import (
    AcceptedArtistName,
    ArtistNameProvider,
    SelectedArtistNameKind,
)
from omym2.domain.models.artist_name_resolution import (
    ArtistNameResolutionIssue,
    ArtistNameResolutionProvenance,
)
from omym2.features.artist_names.dto import (
    ArtistLanguagePrediction,
    ArtistNameAliasCandidate,
    ArtistNameProviderCandidate,
    ArtistNameSearchResult,
    ResolveArtistNamesRequest,
)
from omym2.features.artist_names.ports import ResolveArtistNamesPorts
from omym2.features.artist_names.usecases.resolve_artist_names import ResolveArtistNamesUseCase
from tests.fakes.in_memory_repositories import InMemoryAcceptedArtistNameRepository, InMemoryUnitOfWork
from tests.fakes.runtime import FixedClock

if TYPE_CHECKING:
    from types import TracebackType

SOURCE_NAME = "宇多田ヒカル"
SECOND_SOURCE_NAME = "椎名林檎"
RESOLVED_NAME = "Hikaru Utada"
SECOND_RESOLVED_NAME = "Ringo Sheena"
MUSICBRAINZ_ARTIST_ID = "db2f4f3a-f0c2-4c96-bea3-636f4b44f57b"
SECOND_MUSICBRAINZ_ARTIST_ID = "4d9c88b7-8a31-4b77-a6a5-7fbd7dc58829"
BASE_TIME = datetime(2026, 7, 15, 12, tzinfo=UTC)
CACHE_AND_PERSIST_TRANSACTION_COUNT = 2
JAPANESE_PREDICTION = ArtistLanguagePrediction(
    label="__label__ja",
    confidence=0.8,
    available=True,
)
DEFAULT_ALIAS_CANDIDATES = (ArtistNameAliasCandidate(name=RESOLVED_NAME, locale="en"),)


@dataclass(slots=True)
class _ObservedUnitOfWork(InMemoryUnitOfWork):
    transaction_depth: int = 0
    transaction_entries: int = 0

    @override
    def __enter__(self) -> Self:
        self.transaction_depth += 1
        self.transaction_entries += 1
        _ = super().__enter__()
        return self

    @override
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        try:
            return super().__exit__(exc_type, exc, tb)
        finally:
            self.transaction_depth -= 1


@dataclass(slots=True)
class _Predictor:
    prediction: ArtistLanguagePrediction
    uow: _ObservedUnitOfWork
    calls: list[str]

    def predict_language(self, text: str) -> ArtistLanguagePrediction:
        assert self.uow.transaction_depth == 0
        self.calls.append(text)
        return self.prediction


@dataclass(slots=True)
class _Provider:
    result: ArtistNameSearchResult
    uow: _ObservedUnitOfWork
    calls: list[str]

    def search_artists(self, source_name: str) -> ArtistNameSearchResult:
        assert self.uow.transaction_depth == 0
        self.calls.append(source_name)
        return self.result


class _RacingAcceptedNameRepository(InMemoryAcceptedArtistNameRepository):
    def __init__(self, winner: AcceptedArtistName) -> None:
        super().__init__()
        self.winner: AcceptedArtistName = winner

    @override
    def insert_if_absent(self, accepted_name: AcceptedArtistName) -> bool:
        self.records[accepted_name.source_key] = self.winner
        return False


def _candidate(
    *,
    provider_artist_id: str = MUSICBRAINZ_ARTIST_ID,
    score: int = 100,
    name: str = SOURCE_NAME,
    aliases: tuple[ArtistNameAliasCandidate, ...] = DEFAULT_ALIAS_CANDIDATES,
) -> ArtistNameProviderCandidate:
    return ArtistNameProviderCandidate(
        provider_artist_id=provider_artist_id,
        score=score,
        name=name,
        aliases=aliases,
    )


def _accepted_name(
    *,
    source_name: str = SOURCE_NAME,
    resolved_name: str = RESOLVED_NAME,
) -> AcceptedArtistName:
    return AcceptedArtistName(
        source_key=source_name,
        source_name=source_name,
        resolved_name=resolved_name,
        provider=ArtistNameProvider.MUSICBRAINZ,
        provider_artist_id=MUSICBRAINZ_ARTIST_ID,
        selected_name_kind=SelectedArtistNameKind.ALIAS,
        selected_locale="en",
        accepted_at=BASE_TIME,
    )


def test_resolver_applies_preferences_before_cache_and_automatic_work() -> None:
    """An exact raw preference wins without consulting an accepted row or model."""
    uow = _ObservedUnitOfWork()
    uow.accepted_artist_names.records[SOURCE_NAME] = _accepted_name()
    usecase, predictor, provider = _usecase(uow)

    result = usecase.execute(ResolveArtistNamesRequest((SOURCE_NAME,), preferences={SOURCE_NAME: "Utada Hikaru"}))

    assert result[0].resolved_name == "Utada Hikaru"
    assert result[0].provenance is ArtistNameResolutionProvenance.USER_PREFERENCE
    assert predictor.calls == []
    assert provider.calls == []
    assert uow.usecase_scope_enter_count == 0
    assert uow.transaction_entries == 0


def test_resolver_uses_accepted_cache_before_eligibility() -> None:
    """A sticky accepted name bypasses language and composite eligibility checks."""
    composite = f"{SOURCE_NAME},{SECOND_SOURCE_NAME}"
    accepted_name = _accepted_name(source_name=composite)
    uow = _ObservedUnitOfWork()
    uow.accepted_artist_names.records[composite] = accepted_name
    usecase, predictor, provider = _usecase(uow)

    result = usecase.resolve_many((composite,))

    assert result[0].accepted_name == accepted_name
    assert result[0].provenance is ArtistNameResolutionProvenance.ACCEPTED_MUSICBRAINZ
    assert predictor.calls == []
    assert provider.calls == []
    assert uow.transaction_entries == 1


def test_resolver_uses_accepted_cache_when_automatic_lookup_is_disabled() -> None:
    """Disabling new network work does not hide sticky accepted provider results."""
    accepted_name = _accepted_name()
    uow = _ObservedUnitOfWork()
    uow.accepted_artist_names.records[SOURCE_NAME] = accepted_name
    usecase, predictor, provider = _usecase(uow, automatic_lookup_enabled=False)

    resolution = usecase.resolve_many((SOURCE_NAME,))[0]

    assert resolution.accepted_name == accepted_name
    assert resolution.provenance is ArtistNameResolutionProvenance.ACCEPTED_MUSICBRAINZ
    assert predictor.calls == []
    assert provider.calls == []


def test_resolver_disables_uncached_automatic_lookup_before_model_work() -> None:
    """Persisted opt-out preserves original metadata without model or provider I/O."""
    uow = _ObservedUnitOfWork()
    usecase, predictor, provider = _usecase(uow, automatic_lookup_enabled=False)

    resolution = usecase.resolve_many((SOURCE_NAME,))[0]

    assert resolution.resolved_name == SOURCE_NAME
    assert resolution.issue is ArtistNameResolutionIssue.AUTOMATIC_LOOKUP_DISABLED
    assert predictor.calls == []
    assert provider.calls == []


def test_resolver_uses_configured_minimum_language_confidence() -> None:
    """A configured confidence threshold controls provider eligibility."""
    prediction = ArtistLanguagePrediction(label="__label__ja", confidence=0.89, available=True)
    uow = _ObservedUnitOfWork()
    usecase, predictor, provider = _usecase(uow, prediction=prediction, minimum_confidence=0.9)

    resolution = usecase.resolve_many((SOURCE_NAME,))[0]

    assert resolution.issue is ArtistNameResolutionIssue.LOW_LANGUAGE_CONFIDENCE
    assert predictor.calls == [SOURCE_NAME]
    assert provider.calls == []


def test_resolver_preserves_input_cardinality_and_deduplicates_source_key_io() -> None:
    """Equivalent raw strings resolve once but retain one aligned result per input."""
    first_source = "\t宇多田  ヒカル\n"
    second_source = "宇多田 ヒカル"
    uow = _ObservedUnitOfWork()
    usecase, predictor, provider = _usecase(uow)

    result = usecase.resolve_many((first_source, second_source))

    assert tuple(item.source_name for item in result) == (first_source, second_source)
    assert tuple(item.resolved_name for item in result) == (RESOLVED_NAME, RESOLVED_NAME)
    assert predictor.calls == [second_source]
    assert provider.calls == [second_source]
    assert uow.usecase_scope_enter_count == 1
    assert uow.usecase_scope_exit_count == 1
    assert uow.transaction_entries == CACHE_AND_PERSIST_TRANSACTION_COUNT
    assert uow.commit_count == 1


def test_resolver_applies_later_raw_preference_before_source_key_deduplication() -> None:
    """Equivalent keys do not hide an exact preference on a later raw occurrence."""
    first_source = "宇多田  ヒカル"
    second_source = "宇多田 ヒカル"
    uow = _ObservedUnitOfWork()
    usecase, predictor, provider = _usecase(uow)

    result = usecase.resolve_many(
        (first_source, second_source),
        preferences={second_source: "Manual Name"},
    )

    assert result[0].provenance is ArtistNameResolutionProvenance.NEW_MUSICBRAINZ
    assert result[1].provenance is ArtistNameResolutionProvenance.USER_PREFERENCE
    assert result[1].resolved_name == "Manual Name"
    assert predictor.calls == [second_source]
    assert provider.calls == [second_source]


@pytest.mark.parametrize(
    ("source_name", "prediction", "expected_issue"),
    [
        (None, JAPANESE_PREDICTION, ArtistNameResolutionIssue.MISSING_SOURCE),
        (f"{SOURCE_NAME},{SECOND_SOURCE_NAME}", JAPANESE_PREDICTION, ArtistNameResolutionIssue.COMPOSITE_UNSUPPORTED),
        ("Artist", JAPANESE_PREDICTION, ArtistNameResolutionIssue.NON_LATIN_REQUIRED),
        ("A宇多田", JAPANESE_PREDICTION, ArtistNameResolutionIssue.NON_LATIN_REQUIRED),
        (
            SOURCE_NAME,
            ArtistLanguagePrediction(label=None, confidence=None, available=False),
            ArtistNameResolutionIssue.DETECTOR_UNAVAILABLE,
        ),
        (
            SOURCE_NAME,
            ArtistLanguagePrediction(label="__label__en", confidence=0.99, available=True),
            ArtistNameResolutionIssue.NOT_JAPANESE,
        ),
        (
            SOURCE_NAME,
            ArtistLanguagePrediction(label="__label__ja", confidence=0.79, available=True),
            ArtistNameResolutionIssue.LOW_LANGUAGE_CONFIDENCE,
        ),
        (
            SOURCE_NAME,
            ArtistLanguagePrediction(label="__label__ja", confidence=float("nan"), available=True),
            ArtistNameResolutionIssue.LOW_LANGUAGE_CONFIDENCE,
        ),
        (
            SOURCE_NAME,
            ArtistLanguagePrediction(label="__label__ja", confidence=float("inf"), available=True),
            ArtistNameResolutionIssue.LOW_LANGUAGE_CONFIDENCE,
        ),
    ],
)
def test_resolver_reports_automatic_eligibility_issue(
    source_name: str | None,
    prediction: ArtistLanguagePrediction,
    expected_issue: ArtistNameResolutionIssue,
) -> None:
    """Each rejected automatic gate preserves the exact original value."""
    uow = _ObservedUnitOfWork()
    usecase, _predictor, provider = _usecase(uow, prediction=prediction)

    resolution = usecase.resolve_many((source_name,))[0]

    assert resolution.resolved_name == source_name
    assert resolution.provenance is ArtistNameResolutionProvenance.ORIGINAL
    assert resolution.issue is expected_issue
    assert provider.calls == []


@pytest.mark.parametrize(
    ("search_result", "expected_issue"),
    [
        (ArtistNameSearchResult(available=False), ArtistNameResolutionIssue.PROVIDER_UNAVAILABLE),
        (ArtistNameSearchResult(available=True), ArtistNameResolutionIssue.NO_CONFIDENT_MATCH),
        (
            ArtistNameSearchResult(available=True, candidates=(_candidate(score=94),)),
            ArtistNameResolutionIssue.NO_CONFIDENT_MATCH,
        ),
        (
            ArtistNameSearchResult(
                available=True,
                candidates=(
                    _candidate(score=100),
                    _candidate(provider_artist_id=SECOND_MUSICBRAINZ_ARTIST_ID, score=95),
                ),
            ),
            ArtistNameResolutionIssue.AMBIGUOUS_MATCH,
        ),
    ],
)
def test_resolver_reports_provider_match_issue(
    search_result: ArtistNameSearchResult,
    expected_issue: ArtistNameResolutionIssue,
) -> None:
    """Unavailable, weak, missing, and inclusively close matches fall back safely."""
    uow = _ObservedUnitOfWork()
    usecase, _predictor, _provider = _usecase(uow, search_result=search_result)

    resolution = usecase.resolve_many((SOURCE_NAME,))[0]

    assert resolution.provenance is ArtistNameResolutionProvenance.ORIGINAL
    assert resolution.issue is expected_issue


@pytest.mark.parametrize(
    ("candidate", "expected_name", "expected_kind", "expected_locale"),
    [
        (
            _candidate(
                aliases=(
                    ArtistNameAliasCandidate(name="Zeta Name", locale="en", primary=True),
                    ArtistNameAliasCandidate(name="Alpha Name", locale="en", primary=False),
                    ArtistNameAliasCandidate(name="Alpha Name", locale="en", primary=True),
                    ArtistNameAliasCandidate(name="Earlier Other", locale="ja-Latn", primary=True),
                )
            ),
            "Alpha Name",
            SelectedArtistNameKind.ALIAS,
            "en",
        ),
        (
            _candidate(
                aliases=(
                    ArtistNameAliasCandidate(name="Zeta Latin", locale="ja-Latn"),
                    ArtistNameAliasCandidate(name="Álpha Latin", locale=None),
                )
            ),
            "Zeta Latin",
            SelectedArtistNameKind.ALIAS,
            "ja-Latn",
        ),
        (
            _candidate(name="Beyoncé", aliases=()),
            "Beyoncé",
            SelectedArtistNameKind.NAME,
            None,
        ),
    ],
)
def test_resolver_selects_latin_name_by_deterministic_tiers(
    candidate: ArtistNameProviderCandidate,
    expected_name: str,
    expected_kind: SelectedArtistNameKind,
    expected_locale: str | None,
) -> None:
    """English, other-Latin, then canonical names use lexical alias ordering."""
    uow = _ObservedUnitOfWork()
    usecase, _predictor, _provider = _usecase(
        uow,
        search_result=ArtistNameSearchResult(available=True, candidates=(candidate,)),
    )

    resolution = usecase.resolve_many((SOURCE_NAME,))[0]

    assert resolution.resolved_name == expected_name
    assert resolution.accepted_name is not None
    assert resolution.accepted_name.selected_name_kind is expected_kind
    assert resolution.accepted_name.selected_locale == expected_locale


def test_resolver_coalesces_repeated_identity_independent_of_response_order() -> None:
    """Duplicate rows for one MBID merge alias facts without creating ambiguity."""
    candidates = (
        _candidate(aliases=(ArtistNameAliasCandidate(name="Zeta Name", locale="en"),)),
        _candidate(aliases=(ArtistNameAliasCandidate(name="Alpha Name", locale="en"),)),
    )
    resolved_names: list[str | None] = []

    for ordered_candidates in (candidates, tuple(reversed(candidates))):
        uow = _ObservedUnitOfWork()
        usecase, _predictor, _provider = _usecase(
            uow,
            search_result=ArtistNameSearchResult(available=True, candidates=ordered_candidates),
        )
        resolved_names.append(usecase.resolve_many((SOURCE_NAME,))[0].resolved_name)

    assert resolved_names == ["Alpha Name", "Alpha Name"]


def test_resolver_rereads_sticky_winner_after_insert_race() -> None:
    """A concurrent accepted row wins instead of being silently replaced."""
    winner = _accepted_name(resolved_name="Sticky Winner")
    uow = _ObservedUnitOfWork()
    uow.accepted_artist_names = _RacingAcceptedNameRepository(winner)
    usecase, _predictor, _provider = _usecase(uow)

    resolution = usecase.resolve_many((SOURCE_NAME,))[0]

    assert resolution.resolved_name == "Sticky Winner"
    assert resolution.accepted_name == winner
    assert resolution.provenance is ArtistNameResolutionProvenance.ACCEPTED_MUSICBRAINZ


def _usecase(
    uow: _ObservedUnitOfWork,
    *,
    prediction: ArtistLanguagePrediction = JAPANESE_PREDICTION,
    search_result: ArtistNameSearchResult | None = None,
    automatic_lookup_enabled: bool = True,
    minimum_confidence: float = ARTIST_NAME_LANGUAGE_CONFIDENCE_MIN,
) -> tuple[ResolveArtistNamesUseCase, _Predictor, _Provider]:
    predictor = _Predictor(prediction, uow, [])
    provider = _Provider(
        search_result or ArtistNameSearchResult(available=True, candidates=(_candidate(),)),
        uow,
        [],
    )
    usecase = ResolveArtistNamesUseCase(
        ResolveArtistNamesPorts(
            uow=uow,
            language_predictor=predictor,
            artist_name_provider=provider,
            clock=FixedClock(BASE_TIME),
            automatic_lookup_enabled=automatic_lookup_enabled,
            minimum_confidence=minimum_confidence,
        )
    )
    return usecase, predictor, provider
