"""
Summary: Defines a small Result primitive.
Why: Lets usecases return explicit success or failure values without exceptions.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Ok[T]:
    """Successful Result branch."""

    value: T


@dataclass(frozen=True, slots=True)
class Err[E]:
    """Failed Result branch."""

    error: E


type Result[T, E] = Ok[T] | Err[E]


def ok[T](value: T) -> Ok[T]:
    """Create a successful Result branch."""
    return Ok(value)


def err[E](error: E) -> Err[E]:
    """Create a failed Result branch."""
    return Err(error)
