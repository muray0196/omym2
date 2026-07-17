---
name: write-tests
description: Add or update OMYM2 tests. Use when writing tests for a change, deciding test placement and fixtures, or when told a change needs test coverage.
---

# Write Tests

Test policy is authoritative in `docs/development/testing.md`. This skill is the operational shortcut.

## Placement

`tests/` mirrors `src/omym2/`:

| Code under test | Test location | Style |
| --- | --- | --- |
| `domain/` models and services | `tests/domain/` | pure unit tests, no I/O |
| `features/*/usecases/` | `tests/features/` | unit tests through ports, using fakes |
| `adapters/` (SQLite, fs, metadata, config, cli, web) | `tests/adapters/` | integration tests with real adapter |
| `shared/` | `tests/shared/` | pure unit tests |
| `scripts/*.py` | `tests/scripts/` | run the script via `subprocess`; anchor: `tests/scripts/test_checks_script.py` |
| Layer / naming rules | `tests/architecture/` | already exist; extend only for new rules |
| `docs/` bundle shape | `tests/docs/` | already exist; do not duplicate |

Shared fakes live in `tests/fakes/`. Look there before writing a new fake.

Frontend unit/component tests live beside their feature or under
`web/src/test/`; Playwright tests live under `web/e2e/`.

## Fixture rules

- Fixture Policy in `docs/development/testing.md` is authoritative (in-memory
  repositories for usecase tests, minimal read-only filesystem fixtures except
  for apply/undo); it also requires fixed `Clock` and `IdGenerator` ports so
  time and IDs stay deterministic.
- Test-stack tooling (pytest/pytest-mock, Vitest/React Testing
  Library/`user-event`/MSW, Playwright Chromium/axe) is pinned by the
  Python and frontend lockfiles; see `docs/development/testing.md` for the
  full stack.
- When a canonical fixture is relevant, locate and read only its matching
  subsection in `docs/development/testing.md`.
- For tests under `tests/adapters/fs/` or any test simulating filesystem
  races (rename/replace/symlink swaps), read the `Windows Filesystem
  Semantics` section of `docs/development/testing.md` first; POSIX-only
  assumptions there fail on the native Windows CI job.

## What must be tested (by contract touched)

Only for a contract change, locate `Contract Change Test Requirements` in
`docs/development/testing.md` and read the row for the changed contract. Routine
regression tests follow the nearest existing test and do not require loading the
full testing document.

## Procedure

1. Match the naming and fixture style of a neighboring test; Python test functions use `test_<behavior>`.
2. Test observable behavior and the contract boundary introduced by the change.

## Done means

- The check mode `validate` selects for inspecting one failing test passes, then the check mode it selects for the edit-loop situation passes.

## Stop and report when

- This skill's placement, fixture, or coverage rules conflict with what you find in the existing test suite.
