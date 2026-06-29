# Development Harness

This document is authoritative for developer quality commands, validation gates, suppressions, and Python runtime configuration policy.

Product command behavior is defined in [commands.md](commands.md). Test design is defined in [testing.md](testing.md). Application config and stored path policy are defined in [storage.md](storage.md) and [contracts/](contracts/).

Keep this file limited to commands and validation policy.

## Edit-Loop Commands

During implementation, check only Python files changed in the current task.
Avoid project-wide diagnostics during the edit loop unless the change crosses
many modules or the failure cannot be understood from changed-file checks.

Use this command group after editing Python files. Replace <py-files>
with the Python files changed in the current task:

```bash
uv run ruff check <py-files> --fix --output-format=concise
uv run ruff format <py-files> -q
uv run basedpyright <py-files> --level error
```

Ruff auto-fix runs before formatting. Basedpyright reports errors only. Do not
use verbose, statistics, JSON output, or full-project diagnostics during the edit
loop.

Use this command group after editing the React Web UI:

```bash
cd web
npm ci
npm run format:check
npm run lint
npm run build
```

## Final Quality Gates

Run these commands in order before marking implementation work complete:

```bash
cd web
npm ci
npm run format:check
npm run lint
npm run build
cd ..
uv run ruff check . --output-format=concise
uv run ruff format . --check -q
uv run basedpyright
uv run pytest -q --maxfail=1 --tb=line --show-capture=stdout
```

All gates must pass:

* Frontend installation fails if `package-lock.json` is out of sync.
* Frontend formatting fails if Prettier would change any file.
* Frontend linting fails if ESLint reports any issue.
* Frontend build fails if TypeScript or the Vite production build fails.
* Linting fails if any lint error remains.
* Formatting fails if Ruff would change any file.
* Type checking fails if `basedpyright` reports any error or warning.
* Tests fail if any test fails.

If the Python project skeleton or tool configuration does not exist yet, report the commands as not runnable instead of inventing replacement commands.

## Test Commands

Use these pytest commands by intent:

```bash
# Inspect a focused failure.
uv run pytest <test-target> -q --tb=short --show-capture=all

# Deep debug a focused failure.
uv run pytest <test-target> -q --tb=long -s --show-capture=all
```

Replace `<test-target>` with a test file, test class, test function, or pytest node id.

## Suppressions

Use suppressions sparingly.

Allowed suppression forms:

* `# pyright: ignore[...]`
* `# ruff: noqa: RULE`

Each suppression must include a brief justification comment explaining why the warning or rule is intentionally suppressed.

## Runtime Configuration

Python/runtime configuration uses environment variables only.

This does not change OMYM2 application configuration. Application config remains TOML-based and is governed by [contracts/config.md](contracts/config.md).
