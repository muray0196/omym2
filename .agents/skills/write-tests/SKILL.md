---
name: write-tests
description: Add or update OMYM2 tests. Use when writing tests for a change, deciding test placement and fixtures, or when told a change needs test coverage.
---

# Write Tests

Test policy is authoritative in `docs/TESTING.md`. This skill is the operational shortcut.

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

## Fixture rules

- Usecase tests use in-memory repositories and fakes, never real SQLite or the filesystem.
- Always use fixed `Clock` and `IdGenerator` ports so time and IDs are deterministic.
- Filesystem fixtures: minimal and read-only, except when testing apply/undo (the only flows that move files).
- Allowed libraries: `pytest` and `pytest-mock` only. No Playwright, no new test dependencies.

## What must be tested (by contract touched)

| You changed | Required test focus |
| --- | --- |
| Config contract | load, save, validation, defaults, migration |
| DB schema | migrations, repositories, constraints, stored JSON, timestamps, path representation |
| Path identity | normalization, relink, Library/Track identity, root-relative persistence |
| Status catalog | state transitions, failure behavior, persisted values |
| Plan/apply/undo/refresh/check execution | Plan, PlanAction, Run, FileEvent, apply order, failure cases |
| Layer or naming rule | `tests/architecture/` |

## Procedure

1. Find the existing test file for the module (mirror path). Extend it; create a new file only if none exists.
2. Copy the naming and fixture style of a neighboring test. Test functions: `test_<behavior>` stating the expected outcome.
3. Cover the normal case, one error case, and the boundary the change introduces. Do not pad with redundant cases.
4. Run focused first: `scripts/checks.sh test <file-or-node-id>`, then `scripts/checks.sh changed`.

## Anti-patterns (reject these in your own work)

- Asserting on implementation details (private attributes, call order) instead of observable behavior.
- Over-mocking: if you mock the thing under test, the test is void.
- Tests that depend on wall-clock time, real UUIDs, ordering of dict/set iteration, or files outside `tmp_path`.
- Editing an unrelated failing test to green it — report it instead.
