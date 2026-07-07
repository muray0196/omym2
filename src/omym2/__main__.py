"""
Summary: Provides the python -m omym2 entry point.
Why: Lets the package start through the same CLI boundary as the console script.
"""

from __future__ import annotations

from omym2.platform.cli_entry_point import main

raise SystemExit(main())
