"""
Summary: Exports deterministic OpenAPI JSON from the schema-only Web app.
Why: Keeps committed frontend types aligned without application I/O or drift.
"""
# ruff: noqa: INP001, T201 -- Standalone generator reports concise CLI results.

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, cast

from omym2.adapters.web.schema_app import create_api_schema_app

if TYPE_CHECKING:
    from collections.abc import Sequence

PROJECT_ROOT_NOT_FOUND_MESSAGE = "Unable to locate the project root."
DEFAULT_OPENAPI_RELATIVE_PATH = Path("web-v2/openapi.json")
OPENAPI_ENCODING = "utf-8"
OPENAPI_INDENT = 2


class OpenApiExportError(RuntimeError):
    """Raised when deterministic OpenAPI output cannot be written or checked."""


class ParsedArgs(argparse.Namespace):
    """Typed command-line arguments for OpenAPI export."""

    def __init__(self, output: Path) -> None:
        super().__init__()
        self.output: Path = output
        self.check: bool = False


def render_openapi() -> str:
    """Render the schema-only production API as stable JSON text."""
    schema = cast("dict[str, object]", create_api_schema_app().openapi())
    return f"{json.dumps(schema, indent=OPENAPI_INDENT, sort_keys=True)}\n"


def export_openapi(output: Path) -> None:
    """Atomically replace the committed OpenAPI document."""
    output = output.resolve()
    _ = output.parent.mkdir(parents=True, exist_ok=True)
    rendered = render_openapi()
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding=OPENAPI_ENCODING,
        dir=output.parent,
        prefix=f".{output.name}.",
        delete=False,
    ) as stream:
        temporary_output = Path(stream.name)
        _ = stream.write(rendered)
    try:
        _ = temporary_output.replace(output)
    finally:
        temporary_output.unlink(missing_ok=True)


def check_openapi(output: Path) -> None:
    """Require committed OpenAPI text to equal a fresh schema-only render."""
    if not output.is_file():
        msg = f"Committed OpenAPI document does not exist: {output}"
        raise OpenApiExportError(msg)
    committed = output.read_text(encoding=OPENAPI_ENCODING)
    generated = render_openapi()
    if committed != generated:
        msg = f"Committed OpenAPI document has drifted: {output}"
        raise OpenApiExportError(msg)


def _project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise OpenApiExportError(PROJECT_ROOT_NOT_FOUND_MESSAGE)


def _parse_args(argv: Sequence[str] | None) -> ParsedArgs:
    root = _project_root()
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--output", type=Path, default=root / DEFAULT_OPENAPI_RELATIVE_PATH)
    _ = parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv, namespace=ParsedArgs(root / DEFAULT_OPENAPI_RELATIVE_PATH))


def main(argv: Sequence[str] | None = None) -> int:
    """Export or check deterministic OpenAPI JSON."""
    args = _parse_args(argv)
    try:
        if args.check:
            check_openapi(args.output)
            print(f"OpenAPI check passed: {args.output}")
        else:
            export_openapi(args.output)
            print(f"OpenAPI export passed: {args.output}")
    except (OSError, OpenApiExportError) as exc:
        print(f"OpenAPI export failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
