---
type: Development Guide
title: Development Harness
description: Quality commands, validation gates, checks.sh modes, Codex completion hook, suppressions, and runtime configuration boundaries.
tags: [development, tooling, quality-gates, validation, web, desktop]
timestamp: 2026-07-18T03:18:00+09:00
---

# Development Harness

Authoritative for developer quality commands, validation gates, suppressions, and runtime configuration boundaries. Product command behavior: [COMMANDS.md](../COMMANDS.md); test design: [testing.md](testing.md); config and stored path policy: [STORAGE.md](../STORAGE.md), [contracts/](../contracts/). This file stays limited to commands and validation policy.

## Dependency Setup

After checkout, on manifest/lockfile changes, or when the environment is missing:

```bash
uv sync --locked --dev
cd web && npm ci && cd ..
```

Installation is setup, not a quality check. Reuse `.venv`, `web/node_modules/`, and tool caches during edit loops and validation reruns; do not routinely delete or reinstall. Hosted CI performs both locked installations before the quality wrapper.

## Bundled Web Source

The React/Vite frontend under `web/` is the only frontend source, dependency, test, fixture, and CI working directory. The generated API boundary is intentional source: after a coordinated Pydantic/OpenAPI contract change, regenerate with `cd web && npm run api:generate`. Ordinary validation uses `npm run api:check`, which regenerates into temporary output and compares against the committed OpenAPI/client files without using the Git diff as baseline.

## Edit-Loop Commands

Check only Python files changed in the current task; avoid project-wide diagnostics unless the change crosses many modules or the failure cannot be understood from changed-file checks.

After editing Python files (`<py-files>` = changed files):

```bash
uv run ruff check <py-files> --fix --output-format=concise
uv run ruff format <py-files> -q
uv run basedpyright <py-files> --level error
```

Ruff auto-fix runs before formatting; basedpyright reports errors only. No verbose/statistics/JSON output or full-project diagnostics in the edit loop. The checked-in configuration resolves dependencies from the locked `.venv`.

After editing the React Web UI:

```bash
cd web
npm run api:check
npm run format:check
npm run lint
npm run typecheck
npm run test:unit
npm run build
cd ..
uv run python scripts/web/sync_web_static.py
uv run python scripts/web/audit_web_static.py
```

The sync performs a complete destination replacement; the audit hashes both trees and rejects stale, missing, remote, source-map, secret, inline-script, and inline-style output before packaging.

## Final Quality Gates

The aggregate completion gate is `scripts/checks.sh all`. All gates must pass:

* OpenAPI generation and the committed TypeScript client have zero drift.
* Frontend formatting (Prettier), linting (ESLint), and strict typechecking report no change/issue/error.
* Vitest unit/component tests pass without watch mode.
* The Vite production build and synchronized static export audit pass.
* Pinned-Chromium Playwright keyboard and axe E2E passes against an isolated loopback FastAPI application root.
* Wheel/sdist audit, sdist-to-wheel rebuild without Node.js, and clean-install smoke pass for direct and rebuilt wheels.
* `npm run test:performance` enforces the installed-package interactive-shell and initial JavaScript-size budgets.
* Ruff linting and formatting report no error/change; `basedpyright` reports no error or warning; all tests pass.

If the Python project skeleton or tool configuration does not exist yet, report the commands as not runnable instead of inventing replacements.

## Codex Completion Backstop

The repo-local `.codex/hooks.json` registers one `Stop` hook delegating to path-aware `scripts/checks.sh completion` when repository work is present; the hook does not redefine gate commands or install dependencies.

During Codex implementation, run the smallest checks covering the changed area, then let the `Stop` hook own one completion run — do not run `scripts/checks.sh completion` manually immediately before a normal handoff (the hook cannot consume that result and would repeat the checks). Run completion manually only when the hook is unavailable or bypassed, a hook failure needs direct diagnosis, or an environment-only repair must be verified. Repository edits change the hook fingerprint and re-trigger validation; environment-only repairs do not and require one manual completion run.

Completion mode selects checks from paths changed relative to the merge base with `origin/main` (staged, unstaged, untracked): docs-only → docs checks; frontend → Web checks; Python/backend/tooling → Python gates; Web-adapter → both; unknown paths conservatively run Python gates; missing `origin/main` runs all groups. E2E, package, performance, and cross-platform checks remain in the full aggregate gate and hosted CI. This division applies to Codex sessions only; it does not replace independent CI or developer validation.

## Wrapper Script

`scripts/checks.sh` wraps the command groups in this document:

```bash
scripts/checks.sh <changed|completion|py|api|web|e2e|e2e-ci|package|performance|performance-ci|all|docs|arch>
scripts/checks.sh test <pytest-target>
```

The mode is required; there is no default. The wrapper does not install dependencies. Each command writes combined output to a stable per-gate log under the repository Git directory (`omym2-check-logs/<gate>.log`), overwritten on each run: success prints one pass line and keeps its log silently (inspect it on demand for warnings); failure stops at the first failed gate, prints a bounded tail, and reports the retained log path. Use the bounded tail first, then a larger tail or targeted range, and read the whole log or rerun with full output only as the final step. For pytest keep the progression: aggregate short traceback of the first failure → focused short traceback with full capture → focused long traceback with `-s`. First-pass disclosure is a tail, so every gate command must use flags that place its primary diagnostics at the end of its output.

* `changed`: edit-loop checks on Python files changed vs `HEAD`
* `completion`: path-aware Codex completion checks; excludes E2E, package, performance, cross-platform
* `py`: full Python gates
* `api`: schema-only OpenAPI and generated-client drift gate
* `web`: API drift, frontend format/lint/typecheck/unit/build, static sync, static audit
* `e2e`: `web` plus two pinned-Chromium Playwright profiles against isolated source-checkout servers — the registered profile covers normal inspection/execution with deterministic state; the first-run profile starts without Config or a registered Library and proves Settings recovery, both Organize outcomes, Add review, Apply, blocked evidence, History, and filesystem state. Every browser context rejects non-loopback runtime requests.
* `e2e-ci`: CI-only static build/sync plus the two Playwright profiles; the parallel Frontend job owns API drift, formatting, lint, types, unit tests, and static audit; local callers use `e2e`
* `package`: Vite build, complete static replacement/audit, wheel/sdist audit, Node-poisoned sdist rebuild, clean-install smoke
* `performance`: `package` plus the installed-package frontend performance budget gate and measurement record
* `performance-ci <wheel>`: CI-only performance measurement of the audited wheel downloaded from package evidence; local callers use `performance`
* `all`: `web` + `py` + E2E + package/performance — the final local gate
* `docs`: docs bundle conformance tests
* `arch`: architecture tests
* `test <pytest-target>`: focused failure inspection

The command groups in this document remain authoritative; the script must stay in sync.

Hosted CI first classifies changed paths. Changes limited to `docs/`, `.agents/`, `.codex/`, or root Markdown run only documentation conformance; empty, product, workflow, tooling, or unknown path sets conservatively run the full suite. Full CI keeps independently diagnosable Python, frontend, Playwright, Linux package, Windows runtime-boundary, Windows desktop package/native-smoke, and installed-package performance jobs. The fast API/client job remains independently diagnosable, the Frontend job owns the complete Web gates, and Playwright uses the CI-only E2E mode without repeating either group. Linux package evidence is built once, uploaded, then reused by both Windows packaging and the CI-only performance measurement. Windows runtime tests start independently while packaged smoke waits for the audited wheel. Linux measurement uses pinned `ubuntu-24.04`; both Windows jobs use `windows-2025` (authoritative commands: [Windows Desktop Packaging](desktop-packaging.md)). The hosted Windows Server 2025 x64 job is a native development build/smoke proxy, not Windows 11 release evidence.

CI runs `git diff --exit-code` after tracked generators as a clean-checkout guard against validation tools mutating tracked files — intentionally CI-only, since a local worktree normally contains intended changes. Ignored `static_dist/` is protected instead by its explicit byte-for-byte audit.

## Pipeline Performance Benchmark

For a performance change, read [benchmarks.md](benchmarks.md) and run its pipeline benchmark before and after; it owns the dataset, measurement boundaries, and `--trust-stat` comparison procedure.

## Test Commands

```bash
# Inspect a focused failure.
uv run pytest <test-target> -q --tb=short --show-capture=all

# Deep debug a focused failure.
uv run pytest <test-target> -q --tb=long -s --show-capture=all
```

`<test-target>` is a test file, class, function, or pytest node id.

## Suppressions

Use sparingly. Allowed forms: `# pyright: ignore[...]` and `# ruff: noqa: RULE`. Each suppression carries a brief justification comment.

## Runtime Configuration

No environment-variable override exists for artist naming, hashing, or logging: MusicBrainz enablement, provider bounds, hash chunk size, and log behavior are persisted application settings governed by the [Config Contract](../contracts/config.md), read by CLI, browser-hosted Web, and desktop composition alike. Automatic provider lookup is enabled by default (`musicbrainz.enabled = false` disables); eligibility uses Unicode script properties — Latin-only names stay local, names containing non-Latin letters may contact MusicBrainz. Apply, Undo, Check, history, inspection, Track browsing, and Settings preview never invoke the provider. Operational settings do not mark a Library stale, and already-reviewed Plans retain recorded paths.
