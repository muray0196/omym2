"""
Summary: Provides shared CLI command output helpers.
Why: Removes repeated stderr writing logic from command adapters.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import TextIO


def write_line(stream: TextIO, message: str) -> None:
    """Write one newline-terminated CLI output line."""
    _ = stream.write(f"{message}\n")


def write_usage(stderr: TextIO, usage_message: str) -> None:
    """Write a command usage line to stderr."""
    write_line(stderr, usage_message)


def write_validation_errors(stderr: TextIO, errors: tuple[str, ...]) -> None:
    """Write one validation error per line to stderr."""
    stderr.writelines(f"{error}\n" for error in errors)
