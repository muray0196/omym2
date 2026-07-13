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
- Use only the canonical fixtures in `docs/development/testing.md`.

## What must be tested (by contract touched)

Open `docs/development/testing.md`'s Contract Change Test Requirements table and match
the row for the contract you changed (Config, DB schema, Path identity,
Status catalog, Execution, Architecture, Web API, durable Operation, exclusive
operation, or generated API).

## Anti-patterns (reject these in your own work)

- Asserting on implementation details (private attributes, call order) instead of observable behavior.
- Over-mocking: if you mock the thing under test, the test is void.
- Tests that depend on wall-clock time, real UUIDs, ordering of dict/set iteration, or files outside `tmp_path`.
- Editing an unrelated failing test to green it — report it instead.

## Procedure

1. Find the existing test file for the module (mirror path). Extend it; create a new file only if none exists.
2. For Python, copy the naming and fixture style of a neighboring test. Test
   functions use `test_<behavior>`. For frontend work, use the patterns defined
   inside `web/` itself.
3. Cover the normal case, one error case, and the boundary the change introduces. Do not pad with redundant cases.

## Done means

- The check mode `validate` selects for inspecting one failing test passes, then the check mode it selects for the edit-loop situation passes.

## Stop and report when

- This skill's placement, fixture, or coverage rules conflict with what you find in the existing test suite.
