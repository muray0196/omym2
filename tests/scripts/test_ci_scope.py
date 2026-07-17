"""
Summary: Tests conservative changed-path classification for CI routing.
Why: Fast paths must never skip full validation for product or unknown changes.
"""

from __future__ import annotations

import pytest

from scripts import config
from scripts.ci_scope import classify_paths


@pytest.mark.parametrize(
    ("paths", "expected"),
    [
        ((), config.CI_SCOPE_FULL),
        (("docs/development/harness.md",), config.CI_SCOPE_DOCS),
        ((".agents/skills/validate/SKILL.md", ".codex/hooks.json"), config.CI_SCOPE_DOCS),
        (("README.md", "ARCHITECTURE.md"), config.CI_SCOPE_DOCS),
        (("docs/PRODUCT.md", "src/omym2/config.py"), config.CI_SCOPE_FULL),
        ((".github/workflows/ci.yml",), config.CI_SCOPE_FULL),
        (("scripts/checks.sh",), config.CI_SCOPE_FULL),
        (("unknown/path.txt",), config.CI_SCOPE_FULL),
    ],
)
def test_classify_paths_uses_only_the_explicit_docs_fast_path(
    paths: tuple[str, ...],
    expected: str,
) -> None:
    """Unknown or executable paths always retain the complete CI suite."""
    assert classify_paths(paths) == expected
