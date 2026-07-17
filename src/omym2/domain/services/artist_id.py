"""
Summary: Generates deterministic user-facing artist IDs.
Why: Keeps artist path/config value assembly pure and testable.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

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


@dataclass(slots=True)
class _CharacterToken:
    """One normalized character and whether it belongs to the consonant-first pass."""

    character: str
    prioritized: bool
    included: bool = False


@dataclass(slots=True)
class _WordState:
    """Preserve original character order while filling one word's ID allocation."""

    tokens: list[_CharacterToken]
    next_unused_index: int = 0

    @classmethod
    def from_word(cls, word: str) -> _WordState:
        """Build tokens whose priority sequence removes vowels after the first character."""
        priority = _priority_text(word)
        priority_index = 0
        tokens: list[_CharacterToken] = []
        for character in word:
            prioritized = priority_index < len(priority) and character == priority[priority_index]
            tokens.append(_CharacterToken(character=character, prioritized=prioritized))
            if prioritized:
                priority_index += 1
        return cls(tokens)

    def prioritized_total(self) -> int:
        """Return the number of consonant-first characters available."""
        return sum(token.prioritized for token in self.tokens)

    def include_prioritized_prefix(self, count: int) -> None:
        """Include the requested priority prefix and reset all other tokens."""
        remaining = count
        for token in self.tokens:
            token.included = token.prioritized and remaining > 0
            if token.included:
                remaining -= 1
        self.next_unused_index = 0

    def has_unused_tokens(self) -> bool:
        """Return whether an omitted non-priority character can still be restored."""
        return any(not token.included and not token.prioritized for token in self.tokens)

    def include_next_unused_token(self) -> bool:
        """Restore the next omitted character in its original word position."""
        index = self.next_unused_index
        while index < len(self.tokens):
            token = self.tokens[index]
            if not token.included and not token.prioritized:
                token.included = True
                self.next_unused_index = index + 1
                return True
            index += 1
        self.next_unused_index = len(self.tokens)
        return False

    def rendered(self) -> str:
        """Render selected characters in original order."""
        return "".join(token.character for token in self.tokens if token.included)

    def rendered_length(self) -> int:
        """Return the selected character count."""
        return sum(token.included for token in self.tokens)


def generate_artist_id(
    artist_name: str | None,
    *,
    max_length: int = DEFAULT_ARTIST_ID_MAX_LENGTH,
    fallback_id: str = DEFAULT_ARTIST_ID_FALLBACK,
) -> str:
    """Return a deterministic artist ID for an already-resolved display name."""
    if artist_name is None or artist_name.strip() == "":
        return fallback_id[:max_length]

    artist_words = tuple(_artist_words(part) for part in artist_name.split(ARTIST_ID_MULTI_ARTIST_SEPARATOR))
    artist_words = tuple(words for words in artist_words if words)
    if not artist_words:
        return fallback_id[:max_length]

    capacities = tuple(sum(len(word) for word in words) for words in artist_words)
    quotas = _allocate_quotas(capacities, max_length)
    artist_id = "".join(_render_artist(words, quota) for words, quota in zip(artist_words, quotas, strict=True))
    return artist_id or fallback_id[:max_length]


def _artist_words(artist_name: str) -> tuple[str, ...]:
    words: list[str] = []
    for raw_word in _SPLIT_PATTERN.split(artist_name.strip()):
        if not raw_word.strip():
            continue
        decomposed = unicodedata.normalize("NFKD", raw_word.upper())
        normalized = "".join(_KEEP_PATTERN.findall(decomposed))
        if normalized:
            words.append(normalized)
    return tuple(words)


def _priority_text(word: str) -> str:
    if word == "":
        return ""
    chars = [word[0]]
    chars.extend(char for char in word[1:] if char not in ARTIST_ID_VOWELS)
    return "".join(chars)


def _render_artist(words: tuple[str, ...], quota: int) -> str:
    if quota <= 0:
        return ""

    states = [_WordState.from_word(word) for word in words]
    priority_capacities = tuple(state.prioritized_total() for state in states)
    priority_quotas = _allocate_quotas(priority_capacities, quota)
    for state, priority_quota in zip(states, priority_quotas, strict=True):
        state.include_prioritized_prefix(priority_quota)

    selected = sum(state.rendered_length() for state in states)
    active_indexes = [index for index, state in enumerate(states) if state.has_unused_tokens()]
    position = 0
    while active_indexes and selected < quota:
        state_index = active_indexes[position]
        state = states[state_index]
        if state.include_next_unused_token():
            selected += 1
        if not state.has_unused_tokens():
            _ = active_indexes.pop(position)
            if position >= len(active_indexes):
                position = 0
        else:
            position = (position + 1) % len(active_indexes)

    return "".join(state.rendered() for state in states)


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
