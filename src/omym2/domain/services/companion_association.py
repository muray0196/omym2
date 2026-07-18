"""
Summary: Associates source lyrics and artwork with deterministic audio candidates.
Why: Keeps companion ownership, claims, and target derivation pure and reviewable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from omym2.domain.models.companion_asset import CompanionAssetKind
from omym2.domain.models.plan_action import ActionType, PlanActionReason

if TYPE_CHECKING:
    from collections.abc import Iterable

LYRICS_EXTENSION = ".lrc"
ARTWORK_EXTENSIONS = frozenset({".jpg", ".png"})
CLAIMED_COMPANION_DECISION_MISSING_MESSAGE = "Claimed companion must have an association or issue."


class CompanionIssueCode(StrEnum):
    """Typed companion association failures for later Plan integration."""

    OWNER_MISSING = "owner_missing"
    OWNER_AMBIGUOUS = "owner_ambiguous"
    TARGET_MISSING = "target_missing"
    TARGET_PARENT_MISMATCH = "target_parent_mismatch"


@dataclass(frozen=True, slots=True)
class CompanionAudioCandidate:
    """One source audio path and its optional reviewed target path."""

    source_path: str
    target_path: str | None = None


@dataclass(frozen=True, slots=True)
class CompanionAssociation:
    """One companion owned by audio candidates with its derived target."""

    kind: CompanionAssetKind
    source_path: str
    owner_audio_source_path: str
    target_path: str | None
    dependency_audio_source_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompanionIssue:
    """One typed reason a recognized source cannot form an executable association."""

    kind: CompanionAssetKind
    source_path: str
    code: CompanionIssueCode
    dependency_audio_source_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompanionAssociationResult:
    """Deterministic companion claims, associations, and policy issues."""

    claimed_source_paths: frozenset[str]
    associations: tuple[CompanionAssociation, ...]
    issues: tuple[CompanionIssue, ...]


@dataclass(frozen=True, slots=True)
class _CompanionDecision:
    """One internal classification result before aggregate collection."""

    claimed: bool
    association: CompanionAssociation | None
    issue: CompanionIssue | None


def associate_companions(
    audio_candidates: Iterable[CompanionAudioCandidate],
    source_inventory_paths: Iterable[str],
) -> CompanionAssociationResult:
    """Associate regular, non-symlink inventory paths without consulting enablement.

    Callers supply logical source paths in source-root-relative order. The
    policy sorts them again so ownership and output stay deterministic even
    when an equivalent iterable arrives in a different order.
    """
    ordered_audio = tuple(sorted(audio_candidates, key=lambda candidate: candidate.source_path))
    claimed_sources: set[str] = set()
    associations: list[CompanionAssociation] = []
    issues: list[CompanionIssue] = []

    for source_path in sorted(set(source_inventory_paths)):
        source = PurePosixPath(source_path)
        extension = source.suffix.lower()
        if extension == LYRICS_EXTENSION:
            decision = _lyrics_decision(source_path, source, ordered_audio)
        elif extension in ARTWORK_EXTENSIONS:
            decision = _artwork_decision(source_path, source, ordered_audio)
        else:
            continue
        if decision.claimed:
            claimed_sources.add(source_path)
        if decision.association is not None:
            associations.append(decision.association)
        if decision.issue is not None:
            issues.append(decision.issue)

    return CompanionAssociationResult(
        claimed_source_paths=frozenset(claimed_sources),
        associations=tuple(associations),
        issues=tuple(issues),
    )


def _lyrics_decision(
    source_path: str,
    source: PurePosixPath,
    audio_candidates: tuple[CompanionAudioCandidate, ...],
) -> _CompanionDecision:
    matching_audio = tuple(
        candidate
        for candidate in audio_candidates
        if _source_path(candidate).parent == source.parent and _source_path(candidate).stem == source.stem
    )
    dependencies = tuple(candidate.source_path for candidate in matching_audio)
    if not matching_audio:
        return _issue_decision(
            source_path,
            CompanionAssetKind.LYRICS,
            CompanionIssueCode.OWNER_MISSING,
            dependencies,
            claimed=False,
        )
    if len(matching_audio) > 1:
        return _issue_decision(
            source_path,
            CompanionAssetKind.LYRICS,
            CompanionIssueCode.OWNER_AMBIGUOUS,
            dependencies,
            claimed=True,
        )

    owner = next(iter(matching_audio))
    target_path = (
        None if owner.target_path is None else str(PurePosixPath(owner.target_path).with_suffix(LYRICS_EXTENSION))
    )
    association = CompanionAssociation(
        kind=CompanionAssetKind.LYRICS,
        source_path=source_path,
        owner_audio_source_path=owner.source_path,
        target_path=target_path,
        dependency_audio_source_paths=dependencies,
    )
    issue = (
        None
        if target_path is not None
        else CompanionIssue(
            kind=CompanionAssetKind.LYRICS,
            source_path=source_path,
            code=CompanionIssueCode.TARGET_MISSING,
            dependency_audio_source_paths=dependencies,
        )
    )
    return _CompanionDecision(claimed=True, association=association, issue=issue)


def _artwork_decision(
    source_path: str,
    source: PurePosixPath,
    audio_candidates: tuple[CompanionAudioCandidate, ...],
) -> _CompanionDecision:
    associated_audio = tuple(
        candidate for candidate in audio_candidates if _source_path(candidate).parent == source.parent
    )
    dependencies = tuple(candidate.source_path for candidate in associated_audio)
    if not associated_audio:
        return _issue_decision(
            source_path,
            CompanionAssetKind.ARTWORK,
            CompanionIssueCode.OWNER_MISSING,
            dependencies,
            claimed=False,
        )

    owner = associated_audio[0]
    target_path, issue_code = _artwork_target(source.name, associated_audio)
    association = CompanionAssociation(
        kind=CompanionAssetKind.ARTWORK,
        source_path=source_path,
        owner_audio_source_path=owner.source_path,
        target_path=target_path,
        dependency_audio_source_paths=dependencies,
    )
    issue = (
        None
        if issue_code is None
        else CompanionIssue(
            kind=CompanionAssetKind.ARTWORK,
            source_path=source_path,
            code=issue_code,
            dependency_audio_source_paths=dependencies,
        )
    )
    return _CompanionDecision(claimed=True, association=association, issue=issue)


def _artwork_target(
    artwork_basename: str,
    audio_candidates: tuple[CompanionAudioCandidate, ...],
) -> tuple[str | None, CompanionIssueCode | None]:
    if any(candidate.target_path is None for candidate in audio_candidates):
        return None, CompanionIssueCode.TARGET_MISSING
    target_parents = {
        PurePosixPath(candidate.target_path).parent
        for candidate in audio_candidates
        if candidate.target_path is not None
    }
    if len(target_parents) != 1:
        return None, CompanionIssueCode.TARGET_PARENT_MISMATCH
    target_parent = next(iter(target_parents))
    return str(target_parent / artwork_basename), None


def _issue_decision(
    source_path: str,
    kind: CompanionAssetKind,
    code: CompanionIssueCode,
    dependencies: tuple[str, ...],
    *,
    claimed: bool,
) -> _CompanionDecision:
    return _CompanionDecision(
        claimed=claimed,
        association=None,
        issue=CompanionIssue(
            kind=kind,
            source_path=source_path,
            code=code,
            dependency_audio_source_paths=dependencies,
        ),
    )


def _source_path(candidate: CompanionAudioCandidate) -> PurePosixPath:
    return PurePosixPath(candidate.source_path)


def companion_kind(
    association: CompanionAssociation | None,
    issue: CompanionIssue | None,
) -> CompanionAssetKind:
    """Return the companion kind recorded by whichever decision claimed it."""
    if association is not None:
        return association.kind
    if issue is not None:
        return issue.kind
    raise AssertionError(CLAIMED_COMPANION_DECISION_MISSING_MESSAGE)


def companion_dependency_sources(
    association: CompanionAssociation | None,
    issue: CompanionIssue | None,
) -> tuple[str, ...]:
    """Return the audio sources a claimed companion depends on, if any."""
    if association is not None:
        return association.dependency_audio_source_paths
    if issue is not None:
        return issue.dependency_audio_source_paths
    return ()


def companion_issue_reason(issue: CompanionIssue | None) -> PlanActionReason | None:
    """Map one companion association issue to its PlanAction block reason."""
    if issue is None:
        return None
    if issue.code in {
        CompanionIssueCode.OWNER_AMBIGUOUS,
        CompanionIssueCode.TARGET_PARENT_MISMATCH,
    }:
        return PlanActionReason.COMPANION_ASSOCIATION_AMBIGUOUS
    return PlanActionReason.COMPANION_OWNER_BLOCKED


def companion_action_type(kind: CompanionAssetKind) -> ActionType:
    """Return the PlanAction type that represents one companion kind."""
    if kind is CompanionAssetKind.LYRICS:
        return ActionType.MOVE_LYRICS
    return ActionType.MOVE_ARTWORK
