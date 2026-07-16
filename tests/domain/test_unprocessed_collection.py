"""
Summary: Tests recorded unprocessed collection path layouts.
Why: Keeps external collection and reversal paths rooted, portable, and identity-preserving.
"""

from __future__ import annotations

import pytest

from omym2.domain.services.unprocessed_collection import validate_unprocessed_path_layout


def test_unprocessed_layout_preserves_original_relative_path() -> None:
    """One portable directory component may prefix the exact original relative path."""
    layout = validate_unprocessed_path_layout(
        "/incoming",
        "/incoming/notes/readme.txt",
        "/incoming/Review Later/notes/readme.txt",
        excluded_root="/music/library",
    )

    assert layout is not None
    assert layout.directory == "Review Later"
    assert layout.source_relative_path == "notes/readme.txt"


@pytest.mark.parametrize(
    ("source_path", "target_path", "excluded_root"),
    [
        ("notes/readme.txt", "/incoming/Unprocessed/notes/readme.txt", None),
        ("/incoming/notes/readme.txt", "Unprocessed/notes/readme.txt", None),
        ("/incoming/../outside/readme.txt", "/incoming/Unprocessed/notes/readme.txt", None),
        ("/incoming/notes/readme.txt", "/outside/Unprocessed/notes/readme.txt", None),
        ("/incoming/notes/readme.txt", "/incoming/Unprocessed/renamed/readme.txt", None),
        ("/incoming/notes/readme.txt", "/incoming/bad:name/notes/readme.txt", None),
        ("/incoming/notes/readme.txt", "/incoming/Unprocessed/notes/readme.txt", "/incoming/Unprocessed"),
    ],
)
def test_unprocessed_layout_rejects_malformed_or_overlapping_paths(
    source_path: str,
    target_path: str,
    excluded_root: str | None,
) -> None:
    """Unsafe roots, relabelling, components, and managed overlap fail closed."""
    assert (
        validate_unprocessed_path_layout(
            "/incoming",
            source_path,
            target_path,
            excluded_root=excluded_root,
        )
        is None
    )
