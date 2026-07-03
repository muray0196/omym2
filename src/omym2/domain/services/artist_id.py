"""
Summary: Generates deterministic user-facing artist IDs.
Why: Keeps artist path/config value assembly pure and testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar

from omym2.config import (
    ARTIST_ID_ALLOWED_PATTERN,
    ARTIST_ID_MULTI_ARTIST_SEPARATOR,
    ARTIST_ID_SPLIT_PATTERN,
    ARTIST_ID_VOWELS,
    DEFAULT_ARTIST_ID_FALLBACK,
    DEFAULT_ARTIST_ID_MAX_LENGTH,
)

_KEEP_PATTERN = re.compile(ARTIST_ID_ALLOWED_PATTERN)
_SPLIT_PATTERN = re.compile(ARTIST_ID_SPLIT_PATTERN)


@dataclass(frozen=True, slots=True)
class _WordPlan:
    original: str
    priority: str


class ArtistIdGenerator:
    """Generate compact deterministic IDs from already-resolved artist text."""

    ID_LENGTH: ClassVar[int] = DEFAULT_ARTIST_ID_MAX_LENGTH
    FALLBACK_ID: ClassVar[str] = DEFAULT_ARTIST_ID_FALLBACK

    @classmethod
    def generate(
        cls,
        artist_name: str | None,
        *,
        max_length: int = DEFAULT_ARTIST_ID_MAX_LENGTH,
        fallback_id: str = DEFAULT_ARTIST_ID_FALLBACK,
    ) -> str:
        """Return an artist ID for text that already has the desired script."""
        if artist_name is None or artist_name.strip() == "":
            return fallback_id[:max_length]

        artist_plans = tuple(_artist_words(part) for part in artist_name.split(ARTIST_ID_MULTI_ARTIST_SEPARATOR))
        artist_plans = tuple(words for words in artist_plans if words)
        if not artist_plans:
            return fallback_id[:max_length]

        capacities = tuple(sum(len(word.original) for word in words) for words in artist_plans)
        quotas = _allocate_quotas(capacities, max_length)
        artist_id = "".join(_render_artist(words, quota) for words, quota in zip(artist_plans, quotas, strict=True))
        return artist_id or fallback_id[:max_length]


def generate_artist_id(
    artist_name: str | None,
    *,
    max_length: int = DEFAULT_ARTIST_ID_MAX_LENGTH,
    fallback_id: str = DEFAULT_ARTIST_ID_FALLBACK,
) -> str:
    """Return a deterministic artist ID for an already-resolved display name."""
    return ArtistIdGenerator.generate(artist_name, max_length=max_length, fallback_id=fallback_id)


def _artist_words(artist_name: str) -> tuple[_WordPlan, ...]:
    plans: list[_WordPlan] = []
    for raw_word in _SPLIT_PATTERN.split(artist_name.strip()):
        if not raw_word.strip():
            continue
        word = _word_plan(raw_word)
        if word.original:
            plans.append(word)
    return tuple(plans)


def _word_plan(word: str) -> _WordPlan:
    normalized = "".join(_KEEP_PATTERN.findall(word.upper()))
    return _WordPlan(original=normalized, priority=_priority_text(normalized))


def _priority_text(word: str) -> str:
    if word == "":
        return ""
    chars = [word[0]]
    chars.extend(char for char in word[1:] if char not in ARTIST_ID_VOWELS)
    return "".join(chars)


def _render_artist(words: tuple[_WordPlan, ...], quota: int) -> str:
    if quota <= 0:
        return ""

    priority_capacities = tuple(len(word.priority) for word in words)
    priority_quotas = _allocate_quotas(priority_capacities, quota)
    remaining = quota - sum(priority_quotas)
    if remaining > 0:
        refill_capacities = tuple(
            len(word.original) - priority_quota for word, priority_quota in zip(words, priority_quotas, strict=True)
        )
        refill_quotas = _allocate_quotas(refill_capacities, remaining)
    else:
        refill_quotas = tuple(0 for _ in words)

    word_quotas = tuple(
        priority_quota + refill_quota
        for priority_quota, refill_quota in zip(priority_quotas, refill_quotas, strict=True)
    )
    return "".join(_render_word(word, word_quota) for word, word_quota in zip(words, word_quotas, strict=True))


def _render_word(word: _WordPlan, quota: int) -> str:
    if quota <= 0:
        return ""
    if len(word.priority) >= quota:
        return word.priority[:quota]
    return word.original[:quota]


def _allocate_quotas(capacities: tuple[int, ...], max_total: int) -> tuple[int, ...]:
    quotas = [0 for _ in capacities]
    remaining = min(max_total, sum(capacities))
    while remaining > 0:
        changed = False
        for index, capacity in enumerate(capacities):
            if remaining <= 0:
                break
            if quotas[index] >= capacity:
                continue
            quotas[index] += 1
            remaining -= 1
            changed = True
        if not changed:
            break
    return tuple(quotas)


__all__ = ["ArtistIdGenerator", "generate_artist_id"]
