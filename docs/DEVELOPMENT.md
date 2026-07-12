---
type: Development Guide
title: Development Harness
description: Specifies dependency setup, current and renewal-transition quality gates, checks.sh, suppressions, and Python runtime configuration policy.
tags: [development, tooling, quality-gates, validation, web-renewal]
timestamp: 2026-07-13T00:31:39+09:00
---

# Development Harness

This document is authoritative for developer quality commands, validation gates,
suppressions, and Python runtime configuration policy.

Product command behavior is defined in [COMMANDS.md](COMMANDS.md). Test design is defined in [TESTING.md](TESTING.md). Application config and stored path policy are defined in [STORAGE.md](STORAGE.md) and [contracts/](contracts/).

Keep this file limited to commands and validation policy.

## Dependency Setup

Install dependencies after checkout, when a dependency manifest or lockfile changes, or when the environment is missing:

```bash
uv sync --locked --dev
cd web
npm ci
cd ..
```

Dependency installation is setup, not a quality check. Reuse `.venv`, `web/node_modules/`, and tool caches during ordinary edit loops and validation reruns. Do not routinely delete or reinstall them; clean installation rewrites the complete dependency tree. Hosted CI performs both locked installations before running the quality wrapper.

## Web Renewal Transition

Until M1 creates `web-v2/`, the runnable frontend commands in this document
continue validating the packaged pre-cutover UI under `web/`. That directory is
an exclusion zone for renewal implementation; its commands and dependencies
keep the shipping package green but are not examples or design inputs.

In the M1 foundation change, update dependency setup, `scripts/checks.sh`, npm
cache paths, and CI working directories together to target `web-v2/`, and add
the OpenAPI drift, strict typecheck, unit/component, Playwright, package audit,
and performance commands required by [TESTING.md](TESTING.md) and
[codebase/web-frontend.md](codebase/web-frontend.md). Document the exact
runnable commands here in that same change. M5 changes only those path
references from `web-v2/` to `web/` as part of the mechanical rename.

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
npm run format:check
npm run lint
npm run build
```

## Final Quality Gates

Run these commands in order before marking implementation work complete:

```bash
cd web
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

* Frontend formatting fails if Prettier would change any file.
* Frontend linting fails if ESLint reports any issue.
* Frontend build fails if TypeScript or the Next.js production build fails.
* Linting fails if any lint error remains.
* Formatting fails if Ruff would change any file.
* Type checking fails if `basedpyright` reports any error or warning.
* Tests fail if any test fails.

If the Python project skeleton or tool configuration does not exist yet, report the commands as not runnable instead of inventing replacement commands.

## Wrapper Script

`scripts/checks.sh` wraps the command groups in this document so they can be run with one call:

```bash
scripts/checks.sh <changed|py|web|all|docs|arch>
scripts/checks.sh test <pytest-target>
```

The mode is required; there is no default. The wrapper does not install dependencies.

* `changed`: edit-loop checks on Python files changed vs `HEAD`
* `py`: full Python gates
* `web`: frontend gates
* `all`: web + py, the final quality gates
* `docs`: docs bundle conformance tests
* `arch`: architecture tests
* `test <pytest-target>`: focused failure inspection

The command groups in this document remain authoritative; the script must stay in sync with them.

Hosted CI runs `uv sync --locked --dev`, `npm ci`, `scripts/checks.sh all`, and then `git diff --exit-code`. The final diff check is a clean-checkout guard against validation tools mutating tracked files; it is intentionally CI-only because a local implementation worktree normally contains intended changes.

## Pipeline Performance Benchmark

For a performance change, read [BENCHMARKS.md](BENCHMARKS.md) and run its
pipeline benchmark before and after the change. It owns the benchmark dataset,
measurement boundaries, and `--trust-stat` comparison procedure.

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
