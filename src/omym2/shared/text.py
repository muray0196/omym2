"""
Summary: Provides ASCII-only lowercasing matching SQLite's LOWER().
Why: Keeps in-process browse search folds identical to SQL LIKE search folds.
"""

from __future__ import annotations

import string

_ASCII_LOWER_TABLE = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)


def ascii_lower(text: str) -> str:
    """Lowercase ASCII letters only, mirroring SQLite's LOWER().

    Browse search is case-insensitive for ASCII only: SQL paths fold with
    LOWER(), so in-process paths must not fold further (no Unicode casefold),
    or list, facet, and group results would disagree on the same query.
    """
    return text.translate(_ASCII_LOWER_TABLE)
