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
| `scripts/*.py` | `tests/scripts/` (create on first use) | run the script via `subprocess`; anchor: `tests/docs/test_index_generation.py` |
| Layer / naming rules | `tests/architecture/` | already exist; extend only for new rules |
| `docs/` bundle shape | `tests/docs/` | already exist; do not duplicate |

Shared fakes live in `tests/fakes/`. Look there before writing a new fake.

Frontend unit/component tests live beside their feature or under
`web/src/test/`; Playwright tests live under `web/e2e/`.

## Fixture rules

- Usecase tests use in-memory repositories and fakes, never real SQLite or the filesystem.
- Always use fixed `Clock` and `IdGenerator` ports so time and IDs are deterministic.
- Filesystem fixtures: minimal and read-only, except when testing apply/undo (the only flows that move files).
- Python tests use `pytest` and `pytest-mock` only.
- Frontend unit/component tests use the contract-approved Vitest, React Testing
  Library, `user-event`, and MSW stack. Browser tests use Playwright Chromium
  and axe. Exact versions come from the frontend lockfile.
- When a canonical fixture is relevant, locate and read only its matching
  subsection in `docs/development/testing.md`.

## What must be tested (by contract touched)

Only for a contract change, locate `Contract Change Test Requirements` in
`docs/development/testing.md` and read the row for the changed contract. Routine
regression tests follow the nearest existing test and do not require loading the
full testing document.

## Procedure

1. Find the existing test file for the module (mirror path). Extend it; create a new file only if none exists.
2. Match the naming and fixture style of a neighboring test; Python test functions use `test_<behavior>`.
3. Test observable behavior and the contract boundary introduced by the change. Add error cases only when they protect a distinct behavior or invariant.

## Done means

- The check mode `validate` selects for inspecting one failing test passes, then the check mode it selects for the edit-loop situation passes.

## Stop and report when

- This skill's placement, fixture, or coverage rules conflict with what you find in the existing test suite.
