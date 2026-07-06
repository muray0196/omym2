"""
Summary: Provides shared CLI command output helpers.
Why: Removes repeated stderr writing logic from command adapters.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import TextIO

JSON_INDENT = 2


def write_line(stream: TextIO, message: str) -> None:
    """Write one newline-terminated CLI output line."""
    _ = stream.write(f"{message}\n")


def write_json(stream: TextIO, payload: Mapping[str, object]) -> None:
    """Write one newline-terminated indented JSON document."""
    write_line(stream, json.dumps(payload, indent=JSON_INDENT))


def write_usage(stderr: TextIO, usage_message: str) -> None:
    """Write a command usage line to stderr."""
    write_line(stderr, usage_message)


def write_validation_errors(stderr: TextIO, errors: tuple[str, ...]) -> None:
    """Write one validation error per line to stderr."""
    stderr.writelines(f"{error}\n" for error in errors)
