"""
Summary: Provides the python -m omym2 entry point.
Why: Lets the package start through the same CLI boundary as the console script.
"""

from __future__ import annotations

from omym2.adapters.cli.main import main

raise SystemExit(main())
