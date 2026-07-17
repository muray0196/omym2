"""
Summary: Tests shared artist display-name resolution orchestration.
Why: Proves precedence, eligibility, matching, caching, and transaction bounds.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Self, override

import pytest

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
RESOLVED_NAME = "Utada Hikaru"
MUSICBRAINZ_ARTIST_ID = "db2f4f3a-f0c2-4c96-bea3-636f4b44f57b"
SECOND_MUSICBRAINZ_ARTIST_ID = "4d9c88b7-8a31-4b77-a6a5-7fbd7dc58829"
BASE_TIME = datetime(2026, 7, 15, 12, tzinfo=UTC)
CACHE_AND_PERSIST_TRANSACTION_COUNT = 2
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
    sort_name: str | None = RESOLVED_NAME,
    aliases: tuple[ArtistNameAliasCandidate, ...] = DEFAULT_ALIAS_CANDIDATES,
) -> ArtistNameProviderCandidate:
    return ArtistNameProviderCandidate(
        provider_artist_id=provider_artist_id,
        score=score,
        name=name,
        sort_name=sort_name,
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


def _user_mapping(
    *,
    source_name: str = SOURCE_NAME,
    resolved_name: str = "Utada Hikaru",
) -> AcceptedArtistName:
    return AcceptedArtistName(
        source_key=source_name,
        source_name=source_name,
        resolved_name=resolved_name,
        provider=ArtistNameProvider.USER,
        provider_artist_id=None,
        selected_name_kind=None,
        selected_locale=None,
        accepted_at=BASE_TIME,
    )


def test_resolver_uses_user_mapping_before_automatic_work() -> None:
    """A user-corrected mapping wins without model or provider work."""
    uow = _ObservedUnitOfWork()
    uow.accepted_artist_names.records[SOURCE_NAME] = _user_mapping()
    usecase, provider = _usecase(uow)

    result = usecase.execute(ResolveArtistNamesRequest((SOURCE_NAME,)))

    assert result[0].resolved_name == "Utada Hikaru"
    assert result[0].provenance is ArtistNameResolutionProvenance.USER_PREFERENCE
    assert provider.calls == []
    assert uow.usecase_scope_enter_count == 1
    assert uow.transaction_entries == 1


def test_resolver_uses_accepted_cache_before_eligibility() -> None:
    """A sticky accepted name bypasses language and composite eligibility checks."""
    composite = f"{SOURCE_NAME},{SECOND_SOURCE_NAME}"
    accepted_name = _accepted_name(source_name=composite)
    uow = _ObservedUnitOfWork()
    uow.accepted_artist_names.records[composite] = accepted_name
    usecase, provider = _usecase(uow)

    result = usecase.resolve_many((composite,))

    assert result[0].accepted_name == accepted_name
    assert result[0].provenance is ArtistNameResolutionProvenance.ACCEPTED_MUSICBRAINZ
    assert provider.calls == []
    assert uow.transaction_entries == 1


def test_resolver_uses_accepted_cache_when_automatic_lookup_is_disabled() -> None:
    """Disabling new network work does not hide sticky accepted provider results."""
    accepted_name = _accepted_name()
    uow = _ObservedUnitOfWork()
    uow.accepted_artist_names.records[SOURCE_NAME] = accepted_name
    usecase, provider = _usecase(uow, automatic_lookup_enabled=False)

    resolution = usecase.resolve_many((SOURCE_NAME,))[0]

    assert resolution.accepted_name == accepted_name
    assert resolution.provenance is ArtistNameResolutionProvenance.ACCEPTED_MUSICBRAINZ
    assert provider.calls == []


def test_resolver_keeps_user_mapping_for_latin_source() -> None:
    """Explicit user edits remain authoritative even when romanization is unnecessary."""
    source_name = "MOTTO MUSIC"
    accepted_name = _user_mapping(source_name=source_name, resolved_name="Motto Music")
    uow = _ObservedUnitOfWork()
    uow.accepted_artist_names.records[source_name] = accepted_name
    usecase, provider = _usecase(uow)

    resolution = usecase.resolve_many((source_name,))[0]

    assert resolution.resolved_name == "Motto Music"
    assert resolution.accepted_name == accepted_name
    assert resolution.provenance is ArtistNameResolutionProvenance.USER_PREFERENCE
    assert provider.calls == []


def test_resolver_disables_uncached_automatic_lookup_before_provider_work() -> None:
    """Persisted opt-out preserves original metadata without provider I/O."""
    uow = _ObservedUnitOfWork()
    usecase, provider = _usecase(uow, automatic_lookup_enabled=False)

    resolution = usecase.resolve_many((SOURCE_NAME,))[0]

    assert resolution.resolved_name == SOURCE_NAME
    assert resolution.issue is ArtistNameResolutionIssue.AUTOMATIC_LOOKUP_DISABLED
    assert provider.calls == []


@pytest.mark.parametrize("source_name", ["IOSYS", "MORE MORE JUMP!", "MOTTO MUSIC", "YOASOBI", "Beyoncé"])
def test_resolver_preserves_latin_source_without_provider_work(source_name: str) -> None:
    """Already-Latin names do not need MusicBrainz romanization."""
    uow = _ObservedUnitOfWork()
    usecase, provider = _usecase(uow)

    resolution = usecase.resolve_many((source_name,))[0]

    assert resolution.resolved_name == source_name
    assert resolution.issue is ArtistNameResolutionIssue.ROMANIZATION_NOT_REQUIRED
    assert provider.calls == []


def test_resolver_preserves_input_cardinality_and_deduplicates_source_key_io() -> None:
    """Equivalent raw strings resolve once but retain one aligned result per input."""
    first_source = "\t宇多田  ヒカル\n"
    second_source = "宇多田 ヒカル"
    uow = _ObservedUnitOfWork()
    usecase, provider = _usecase(uow)

    result = usecase.resolve_many((first_source, second_source))

    assert tuple(item.source_name for item in result) == (first_source, second_source)
    assert tuple(item.resolved_name for item in result) == (RESOLVED_NAME, RESOLVED_NAME)
    assert provider.calls == [second_source]
    assert uow.usecase_scope_enter_count == 1
    assert uow.usecase_scope_exit_count == 1
    assert uow.transaction_entries == CACHE_AND_PERSIST_TRANSACTION_COUNT
    assert uow.commit_count == 1


@pytest.mark.parametrize(
    ("source_name", "expected_issue"),
    [
        (None, ArtistNameResolutionIssue.MISSING_SOURCE),
        (f"{SOURCE_NAME},{SECOND_SOURCE_NAME}", ArtistNameResolutionIssue.COMPOSITE_UNSUPPORTED),
        ("!!!", ArtistNameResolutionIssue.ROMANIZATION_NOT_REQUIRED),
    ],
)
def test_resolver_reports_automatic_eligibility_issue(
    source_name: str | None,
    expected_issue: ArtistNameResolutionIssue,
) -> None:
    """Each rejected automatic gate preserves the exact original value."""
    uow = _ObservedUnitOfWork()
    usecase, provider = _usecase(uow)

    resolution = usecase.resolve_many((source_name,))[0]

    assert resolution.resolved_name == source_name
    assert resolution.provenance is ArtistNameResolutionProvenance.ORIGINAL
    assert resolution.issue is expected_issue
    assert provider.calls == []


@pytest.mark.parametrize("source_name", [SOURCE_NAME, "아이유", "Молчат Дома", "Aimer 宇多田"])
def test_resolver_looks_up_names_with_non_latin_letters(source_name: str) -> None:
    """Any non-Latin alphabetic script may populate a Latin MusicBrainz mapping."""
    uow = _ObservedUnitOfWork()
    usecase, provider = _usecase(uow)

    resolution = usecase.resolve_many((source_name,))[0]

    assert resolution.resolved_name == RESOLVED_NAME
    assert resolution.provenance is ArtistNameResolutionProvenance.NEW_MUSICBRAINZ
    assert provider.calls == [source_name]


def test_resolver_looks_up_short_kanji_without_language_detection() -> None:
    """Short CJK names are eligible without a probabilistic language label."""
    source_name = "秦谷美鈴"
    candidate = _candidate(
        name=source_name,
        sort_name="Hataya, Misuzu",
        aliases=(),
    )
    uow = _ObservedUnitOfWork()
    usecase, provider = _usecase(
        uow,
        search_result=ArtistNameSearchResult(available=True, candidates=(candidate,)),
    )

    resolution = usecase.resolve_many((source_name,))[0]

    assert resolution.resolved_name == "Hataya Misuzu"
    assert resolution.issue is None
    assert provider.calls == [source_name]


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
    usecase, _provider = _usecase(uow, search_result=search_result)

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
                    ArtistNameAliasCandidate(
                        name="Ryuichi Sakamoto",
                        locale="ja-Latn",
                        sort_name="Sakamoto, Ryuichi",
                        primary=True,
                    ),
                )
            ),
            "Sakamoto Ryuichi",
            SelectedArtistNameKind.ALIAS_SORT_NAME,
            "ja-Latn",
        ),
        (
            _candidate(
                name="煮ル果実",
                sort_name="Niru Kajitsu",
                aliases=(ArtistNameAliasCandidate(name="NILFRUITS", locale="en", primary=True),),
            ),
            "Niru Kajitsu",
            SelectedArtistNameKind.SORT_NAME,
            None,
        ),
        (
            _candidate(
                name="宇多田ヒカル",
                sort_name="Utada, Hikaru",
                aliases=(ArtistNameAliasCandidate(name="Hikaru Utada", locale="en", primary=True),),
            ),
            "Utada Hikaru",
            SelectedArtistNameKind.SORT_NAME,
            None,
        ),
        (
            _candidate(
                aliases=(
                    ArtistNameAliasCandidate(
                        name="Kenshi Yonezu",
                        locale="JA_LATN",
                        sort_name="Yonezu, Kenshi",
                        primary=True,
                    ),
                    ArtistNameAliasCandidate(name="Yonezu Kenshi", locale="en", primary=True),
                ),
            ),
            "Yonezu Kenshi",
            SelectedArtistNameKind.ALIAS_SORT_NAME,
            "JA_LATN",
        ),
        (
            _candidate(name="秦谷美鈴", sort_name="Hataya, Misuzu", aliases=()),
            "Hataya Misuzu",
            SelectedArtistNameKind.SORT_NAME,
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
    """OMYM tiers use a primary ja-Latn alias, then the artist sort-name."""
    uow = _ObservedUnitOfWork()
    usecase, _provider = _usecase(
        uow,
        search_result=ArtistNameSearchResult(available=True, candidates=(candidate,)),
    )

    resolution = usecase.resolve_many((SOURCE_NAME,))[0]

    assert resolution.resolved_name == expected_name
    assert resolution.accepted_name is not None
    assert resolution.accepted_name.selected_name_kind is expected_kind
    assert resolution.accepted_name.selected_locale == expected_locale


def test_resolver_rejects_aliases_and_canonical_name_without_omym_selection() -> None:
    """English aliases and canonical names do not replace a missing OMYM sort-name."""
    candidate = _candidate(
        name="Beyoncé",
        sort_name=None,
        aliases=(ArtistNameAliasCandidate(name="NILFRUITS", locale="en", primary=True),),
    )
    uow = _ObservedUnitOfWork()
    usecase, _provider = _usecase(
        uow,
        search_result=ArtistNameSearchResult(available=True, candidates=(candidate,)),
    )

    resolution = usecase.resolve_many((SOURCE_NAME,))[0]

    assert resolution.resolved_name == SOURCE_NAME
    assert resolution.accepted_name is None
    assert resolution.provenance is ArtistNameResolutionProvenance.ORIGINAL
    assert resolution.issue is ArtistNameResolutionIssue.NO_CONFIDENT_MATCH


def test_resolver_coalesces_repeated_identity_independent_of_response_order() -> None:
    """Duplicate rows for one MBID merge alias facts without creating ambiguity."""
    alias = ArtistNameAliasCandidate(
        name="Ryuichi Sakamoto",
        locale="ja-Latn",
        sort_name="Sakamoto, Ryuichi",
    )
    candidates = (
        _candidate(aliases=(alias,)),
        _candidate(
            aliases=(
                ArtistNameAliasCandidate(
                    name=alias.name,
                    locale=alias.locale,
                    sort_name=alias.sort_name,
                    primary=True,
                ),
            )
        ),
    )
    resolved_names: list[str | None] = []

    for ordered_candidates in (candidates, tuple(reversed(candidates))):
        uow = _ObservedUnitOfWork()
        usecase, _provider = _usecase(
            uow,
            search_result=ArtistNameSearchResult(available=True, candidates=ordered_candidates),
        )
        resolved_names.append(usecase.resolve_many((SOURCE_NAME,))[0].resolved_name)

    assert resolved_names == ["Sakamoto Ryuichi", "Sakamoto Ryuichi"]


def test_resolver_rereads_sticky_winner_after_insert_race() -> None:
    """A concurrent accepted row wins instead of being silently replaced."""
    winner = _accepted_name(resolved_name="Sticky Winner")
    uow = _ObservedUnitOfWork()
    uow.accepted_artist_names = _RacingAcceptedNameRepository(winner)
    usecase, _provider = _usecase(uow)

    resolution = usecase.resolve_many((SOURCE_NAME,))[0]

    assert resolution.resolved_name == "Sticky Winner"
    assert resolution.accepted_name == winner
    assert resolution.provenance is ArtistNameResolutionProvenance.ACCEPTED_MUSICBRAINZ


def _usecase(
    uow: _ObservedUnitOfWork,
    *,
    search_result: ArtistNameSearchResult | None = None,
    automatic_lookup_enabled: bool = True,
) -> tuple[ResolveArtistNamesUseCase, _Provider]:
    provider = _Provider(
        search_result or ArtistNameSearchResult(available=True, candidates=(_candidate(),)),
        uow,
        [],
    )
    usecase = ResolveArtistNamesUseCase(
        ResolveArtistNamesPorts(
            uow=uow,
            artist_name_provider=provider,
            clock=FixedClock(BASE_TIME),
            automatic_lookup_enabled=automatic_lookup_enabled,
        )
    )
    return usecase, provider
