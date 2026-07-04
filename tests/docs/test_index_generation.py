"""
Summary: Verifies docs/ index.md files stay generated from frontmatter, not hand-edited.
Why: Frontmatter is the single source of truth for docs/ indexes; drift must fail CI.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT_NOT_FOUND_MESSAGE = "Unable to locate project root from test file."
GENERATOR_SCRIPT_RELATIVE_PATH = "scripts/generate_docs_indexes.py"


def test_generated_indexes_match_disk() -> None:
    """`generate_docs_indexes.py --check` exits 0 when docs/ indexes match their frontmatter."""
    project_root = _project_root()
    result = subprocess.run(  # noqa: S603 -- fixed argv invoking this repo's own generator script.
        [sys.executable, GENERATOR_SCRIPT_RELATIVE_PATH, "--check"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        f"docs index generation --check failed with exit code {result.returncode}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def _project_root() -> Path:
    current_file = Path(__file__).resolve()
    for parent in current_file.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError(PROJECT_ROOT_NOT_FOUND_MESSAGE)
