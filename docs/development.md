# Development Harness

This document is authoritative for developer quality commands, validation gates, suppressions, and Python runtime configuration policy.

Product command behavior is defined in [commands.md](commands.md). Test design is defined in [testing.md](testing.md). Application config and stored path policy are defined in [storage.md](storage.md).

## Final Quality Gates

Run these commands in order before marking implementation work complete:

```bash
uv run ruff check --fix -q
uv run ruff format . -q
uv run basedpyright
uv run pytest -q --maxfail=1 --tb=line --show-capture=stdout
```

All gates must pass:

* Linting fails if any lint error remains.
* Type checking fails if `basedpyright` reports any error or warning.
* Tests fail if any test fails.

If the Python project skeleton or tool configuration does not exist yet, report the commands as not runnable instead of inventing replacement commands.

## Test Commands

Use these pytest commands by intent:

```bash
# Quick global check; must be run before completion when tests are available.
uv run pytest -q --maxfail=1 --tb=line --show-capture=stdout

# Inspect a focused failure.
uv run pytest Target -q --tb=short --show-capture=all

# Deep debug a focused failure.
uv run pytest Target -q --tb=long -s --show-capture=all
```

Replace `Target` with a test file, test class, test function, or pytest node id.

## Suppressions

Use suppressions sparingly.

Allowed suppression forms:

* `# pyright: ignore[...]`
* `# ruff: noqa: RULE`

Each suppression must include a brief justification comment explaining why the warning or rule is intentionally suppressed.

## Runtime Configuration

Python/runtime configuration uses environment variables only.

This does not change OMYM2 application configuration. Application config remains TOML-based and is governed by [storage.md](storage.md#toml-config-design).
