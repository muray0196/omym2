---
type: Development Guide
title: Development Harness
description: Specifies dependency setup, current quality gates, release verification, checks.sh, suppressions, and Python runtime configuration policy.
tags: [development, tooling, quality-gates, validation, web]
timestamp: 2026-07-13T19:23:00+09:00
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

Dependency installation is setup, not a quality check. Reuse `.venv`,
`web/node_modules/`, and tool caches during ordinary edit loops and
validation reruns. Do not routinely delete or reinstall them; clean
installation rewrites the complete dependency tree. Hosted CI performs both
locked installations before running the quality wrapper.

## Bundled Web Source

The React and Vite frontend lives under `web/`. It is the only frontend source,
dependency, test, fixture, and CI working directory.

The generated API boundary is intentional source. After a coordinated
Pydantic/OpenAPI contract change, regenerate it with:

```bash
cd web
npm run api:generate
cd ..
```

Ordinary validation uses `npm run api:check`, which regenerates into temporary
output and compares it with the committed OpenAPI/client files without using
the current Git diff as its baseline.

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
npm run api:check
npm run format:check
npm run lint
npm run typecheck
npm run test:unit
npm run build
cd ..
uv run python scripts/sync_web_static.py
uv run python scripts/audit_web_static.py
```

The sync performs a complete destination replacement. The audit hashes both
trees and rejects stale, missing, remote, source-map, secret, inline-script,
and inline-style output before packaging.

## Final Quality Gates

Run the aggregate gate before marking implementation work complete:

```bash
scripts/checks.sh all
```

All gates must pass:

* OpenAPI generation and the committed TypeScript client have zero drift.
* Frontend formatting fails if Prettier would change any file.
* Frontend linting fails if ESLint reports any issue.
* Strict frontend type checking reports no error.
* Vitest unit/component tests pass without watch mode.
* The Vite production build and synchronized static export audit pass.
* Pinned-Chromium Playwright keyboard and axe E2E passes against an isolated
  loopback FastAPI application root.
* Wheel/sdist audit, sdist-to-wheel rebuild without Node.js, and clean-install
  smoke pass for the direct and rebuilt wheels.
* `npm run test:performance` enforces the installed-package interactive-shell
  time and initial JavaScript-size budgets from M2 onward.
* Linting fails if any lint error remains.
* Formatting fails if Ruff would change any file.
* Type checking fails if `basedpyright` reports any error or warning.
* Tests fail if any test fails.

If the Python project skeleton or tool configuration does not exist yet, report the commands as not runnable instead of inventing replacement commands.

## Wrapper Script

`scripts/checks.sh` wraps the command groups in this document so they can be run with one call:

```bash
scripts/checks.sh <changed|py|api|web|e2e|package|performance|all|docs|arch>
scripts/checks.sh test <pytest-target>
```

The mode is required; there is no default. The wrapper does not install dependencies.

* `changed`: edit-loop checks on Python files changed vs `HEAD`
* `py`: full Python gates
* `api`: schema-only OpenAPI and generated-client drift gate
* `web`: API drift, frontend format/lint/typecheck/unit/build, static sync, and
  static audit
* `e2e`: `web` plus two pinned-Chromium Playwright profiles against isolated
  source-checkout servers. The registered profile covers normal inspection and
  execution with deterministic state. The first-run profile starts without a
  Config or registered Library and proves Settings recovery, both Organize
  outcomes, Add review, Apply, blocked evidence, History, and filesystem state.
  Every browser context rejects non-loopback runtime requests.
* `package`: Vite build, complete static replacement/audit, wheel/sdist audit,
  Node-poisoned sdist rebuild, and clean-install smoke
* `performance`: `package` plus the installed-package frontend performance
  budget gate and measurement record
* `all`: `web` + `py` + E2E + package/performance, the final local gate
* `docs`: docs bundle conformance tests
* `arch`: architecture tests
* `test <pytest-target>`: focused failure inspection

The command groups in this document remain authoritative; the script must stay in sync with them.

Hosted CI runs independently diagnosable Python, API/client, frontend,
Playwright, Linux package, Windows package/static-smoke, and installed-package
performance jobs. Linux measurement uses the pinned `ubuntu-24.04` image;
Windows package smoke uses `windows-2025`. Frontend jobs install with
`web/package-lock.json` and pinned Chromium. The Linux package job uploads
short-lived audited package evidence for the Windows smoke job, which also
runs the real multiprocess lock contention/crash-release test.

CI runs `git diff --exit-code` after tracked generators. The final diff check is
a clean-checkout guard against validation tools mutating tracked files; it is
intentionally CI-only because a local implementation worktree normally
contains intended changes. Ignored `static_dist/` is protected instead by its
explicit byte-for-byte audit.

## Release And Rollback

`.github/workflows/release.yml` is the only publication path. It is manually
dispatched against `main`, requires successful push CI for the exact commit,
and publishes through the GitHub environment named `release`. Configure that
environment with required reviewers before the first dispatch. The workflow
refuses an existing release tag instead of overwriting published state.

The release stores the audited final wheel and source distribution directly.
It also stores one deterministic rollback ZIP built from the pinned last
pre-cutover commit. The ZIP keeps the standardized wheel and sdist filenames
and includes integrity-covered checksums, provenance, and a README. Before
publication, the workflow re-downloads the draft assets, verifies every nested
artifact, compares the staged and downloaded bytes, and rechecks the tag.

Final and rollback distributions both identify themselves as version `0.1.0`.
Install rollback into a fresh environment or force a reinstall. Rollback
changes application code only; restore a pre-cutover persisted-state backup
first because backward state compatibility is not provided.

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
