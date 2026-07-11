---
type: Development Guide
title: Development Harness
description: Specifies developer quality gates, checks.sh, the full-hash and trust-stat pipeline benchmark modes, suppression rules, and Python runtime configuration policy.
tags: [development, tooling, quality-gates, validation]
timestamp: 2026-07-11T10:21:41+09:00
---

# Development Harness

This document is authoritative for developer quality commands, validation gates, suppressions, and Python runtime configuration policy.

Product command behavior is defined in [COMMANDS.md](COMMANDS.md). Test design is defined in [TESTING.md](TESTING.md). Application config and stored path policy are defined in [STORAGE.md](STORAGE.md) and [contracts/](contracts/).

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
* Frontend build fails if TypeScript or the Next.js production build fails.
* Linting fails if any lint error remains.
* Formatting fails if Ruff would change any file.
* Type checking fails if `basedpyright` reports any error or warning.
* Tests fail if any test fails.

If the Python project skeleton or tool configuration does not exist yet, report the commands as not runnable instead of inventing replacement commands.

## Wrapper Script

`scripts/checks.sh` wraps the command groups in this document so they can be run with one call:

```bash
scripts/checks.sh [changed|py|web|all|docs|arch]
scripts/checks.sh test <pytest-target>
```

* `changed` (default): edit-loop checks on Python files changed vs `HEAD`
* `py`: full Python gates
* `web`: frontend gates
* `all`: web + py, the final quality gates
* `docs`: docs bundle conformance tests
* `arch`: architecture tests
* `test <pytest-target>`: focused failure inspection

The command groups in this document remain authoritative; the script must stay in sync with them.

## Pipeline Performance Benchmark

Run the end-to-end pipeline benchmark before and after performance changes:

```bash
uv run python scripts/benchmark_pipeline.py \
  --tracks 100 \
  --file-size-bytes 1048576 \
  --tracks-per-album 10
```

`--tracks` controls the total dataset size. `--file-size-bytes` controls the exact size of each generated file, and `--tracks-per-album` controls the album shape. The minimum file size is 4096 bytes so every fixture can contain valid FLAC metadata. Use `--workspace-root PATH` to place the disposable workspace on the filesystem being measured; otherwise the operating system's temporary directory is used.

The harness first registers an empty Library through the public `organize` command, then generates tagged synthetic FLAC files in Incoming. Its clean baseline runs `add`, `apply latest --yes`, `organize`, and `check` through fresh `python -m omym2` processes. Each stage timing therefore includes CLI startup and the real composition, metadata, filesystem, hashing, and SQLite pathways.

After the clean check, setup changes the path-neutral genre tag on every managed FLAC and creates an unapplied `refresh --all` Plan containing one `refresh_metadata` action per Track. A second measured `check_ready_plan` stage exercises the overlap between managed-Track and READY-Plan source diagnostics. That diagnostic check intentionally exits nonzero because every Track differs from persisted managed state; the harness requires one `content_hash_changed` and one `metadata_hash_changed` result per Track.

Bootstrap, fixture generation, tag mutation, and READY-Plan creation are reported as `setup.*` timings. `stage.measured_total_seconds` retains the original clean-baseline total, while `stage.extended_measured_total_seconds` adds only the measured `check_ready_plan` stage; neither includes setup. The temporary workspace is deleted after the run.

Compare runs only when dataset arguments and workspace filesystem are the same. The harness does not clear operating-system filesystem caches.

Add `--trust-stat` to forward the explicit opt-in to measured organize/check stages and to the post-mutation refresh/check setup:

```bash
uv run python scripts/benchmark_pipeline.py \
  --tracks 100 \
  --file-size-bytes 1048576 \
  --tracks-per-album 10 \
  --trust-stat
```

The output header records `trust_stat=false` or `trust_stat=true`. Apply remains unchanged in both modes and always performs full source hashing. On the clean organize/check stages, a true run measures the stat-only path after apply has populated verified baselines. After tag mutation, baseline mismatch forces refresh and READY-Plan check back to full capture, which also verifies the fallback behavior.

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
