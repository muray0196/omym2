"""
Summary: Runs one quality command with context-bounded diagnostics.
Why: Keeps successful checks silent and failed checks progressively inspectable.
"""
# ruff: noqa: INP001, T201 -- Standalone quality wrapper reports diagnostics to stderr.

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Final

if __package__:
    from scripts.config import CHECKS_FAILURE_DIAGNOSTIC_MAX_BYTES
else:
    from config import CHECKS_FAILURE_DIAGNOSTIC_MAX_BYTES

if TYPE_CHECKING:
    from collections.abc import Sequence

COMMAND_NOT_FOUND_EXIT_CODE: Final = 127
COMMAND_START_FAILURE_EXIT_CODE: Final = 126
OUTPUT_ENCODING: Final = "utf-8"
DEFAULT_LOG_DIRECTORY_NAME: Final = "omym2-check-logs"
OUTPUT_LOG_SUFFIX: Final = ".log"
LABEL_SLUG_PATTERN: Final = re.compile(r"[^a-z0-9]+")


class ParsedArgs(argparse.Namespace):
    """Typed command-line arguments for one check invocation."""

    def __init__(self) -> None:
        super().__init__()
        self.label: str = ""
        self.log_directory: Path | None = None
        self.command: list[str] = []


def _parse_args(argv: Sequence[str] | None) -> ParsedArgs:
    """Parse a label, an optional log directory, and the command after `--`."""
    parser = argparse.ArgumentParser(description="Run one check with bounded failure output.")
    _ = parser.add_argument("--label", required=True, help="short gate name used in failure diagnostics")
    _ = parser.add_argument(
        "--log-directory",
        type=Path,
        default=None,
        help="directory holding one overwritten log per gate (default: system temporary directory)",
    )
    _ = parser.add_argument("command", nargs=argparse.REMAINDER, help="command to run")
    args = parser.parse_args(argv, namespace=ParsedArgs())
    if args.command[:1] == ["--"]:
        args.command = args.command[1:]
    if not args.command:
        parser.error("a command is required after --")
    return args


def _log_path(label: str, log_directory: Path | None) -> Path:
    """Return the stable per-gate log path, overwritten on each run."""
    directory = log_directory if log_directory is not None else Path(tempfile.gettempdir()) / DEFAULT_LOG_DIRECTORY_NAME
    slug = LABEL_SLUG_PATTERN.sub("-", label.lower()).strip("-") or "check"
    return directory / f"{slug}{OUTPUT_LOG_SUFFIX}"


def _diagnostic_tail(path: Path) -> tuple[str, bool]:
    """Read only the configured tail of a failed command's combined output."""
    output_size = path.stat().st_size
    start = max(0, output_size - CHECKS_FAILURE_DIAGNOSTIC_MAX_BYTES)
    with path.open("rb") as stream:
        _ = stream.seek(start)
        output = stream.read()
    return output.decode(OUTPUT_ENCODING, errors="replace").strip(), start > 0


def _report_failure(*, label: str, return_code: int, output_path: Path) -> None:
    """Emit bounded first-pass diagnostics and retain the complete log."""
    diagnostics, truncated = _diagnostic_tail(output_path)
    print(f"checks.sh: gate '{label}' failed with exit code {return_code}.", file=sys.stderr)
    if truncated:
        print("[earlier check output omitted]", file=sys.stderr)
    if diagnostics:
        print(diagnostics, file=sys.stderr)
    else:
        print("The command returned no diagnostic output.", file=sys.stderr)
    print(f"checks.sh: full output retained at {output_path}", file=sys.stderr)


def run_check(*, label: str, command: Sequence[str], log_directory: Path | None) -> int:
    """Run one command, keeping successful output silent and bounding failed output."""
    output_path = _log_path(label, log_directory)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as output:
        try:
            result = subprocess.run(  # noqa: S603 -- checks.sh supplies reviewed quality-gate argv.
                command,
                stdout=output,
                stderr=subprocess.STDOUT,
                check=False,
            )
        except FileNotFoundError:
            _ = output.write(f"command not found: {command[0]}\n".encode(OUTPUT_ENCODING))
            return_code = COMMAND_NOT_FOUND_EXIT_CODE
        except OSError as error:
            _ = output.write(f"command could not start: {error}\n".encode(OUTPUT_ENCODING, errors="replace"))
            return_code = COMMAND_START_FAILURE_EXIT_CODE
        else:
            return_code = result.returncode

    if return_code == 0:
        return 0

    _report_failure(label=label, return_code=return_code, output_path=output_path)
    return return_code


def main(argv: Sequence[str] | None = None) -> int:
    """Run the requested check command."""
    args = _parse_args(argv)
    return run_check(label=args.label, command=args.command, log_directory=args.log_directory)


if __name__ == "__main__":
    raise SystemExit(main())
