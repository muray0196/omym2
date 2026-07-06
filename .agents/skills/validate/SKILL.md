---
name: validate
description: Run OMYM2 quality gates and triage failures. Use when validating changes, before declaring work complete, or when a gate or CI command fails and you need the next action.
---

# Validate

## Mode table

| Situation | Command |
| --- | --- |
| After editing Python files (edit loop) | `scripts/checks.sh changed` |
| Before declaring any implementation complete | `scripts/checks.sh all` |
| Python-only full gates | `scripts/checks.sh py` |
| Frontend gates only | `scripts/checks.sh web` |
| Docs bundle conformance | `scripts/checks.sh docs` |
| Architecture boundary / naming rules | `scripts/checks.sh arch` |
| Inspect one failing test | `scripts/checks.sh test <pytest-node-id>` |
| Deep-debug one failing test | `uv run pytest <pytest-node-id> -q --tb=long -s --show-capture=all` |

`scripts/checks.sh` wraps the authoritative commands in `docs/DEVELOPMENT.md`. If the script is missing or itself broken, run those commands directly.

## Triage table

Fix the first failing gate before looking at later ones.

| First failure | Likely cause | Next action |
| --- | --- | --- |
| `uv` / `npm` / command not found | environment | Install per README; do not edit product code |
| `npm ci` fails | lockfile out of sync | Report it; do not hand-edit `package-lock.json` |
| `ModuleNotFoundError` for a dependency | env not synced | `uv sync` (Python) or `cd web && npm ci` (frontend) |
| `ruff check` errors | lint issue in changed code | Fix the code; suppress only per policy below |
| `ruff format --check` fails | formatting | `uv run ruff format <files> -q` |
| `basedpyright` errors | typing issue | Fix types; narrow with `isinstance`, avoid `Any` |
| `pytest` failure in a test you touched | your change | Reproduce focused: `scripts/checks.sh test <node-id>` |
| `pytest` failure in a test you did not touch | regression from your change | Read the test's intent first; fix the code, not the test, unless the contract itself changed |
| `git diff --exit-code` fails in CI | generated files drifted | Re-run the relevant generator and commit only tracked generated outputs |

## Suppression rules

- Never weaken or delete an existing test to make a gate pass.
- Suppressions are last resort and need a justification comment on the same line:
  `# pyright: ignore[rule]  # why` or `# noqa: RULE  # why`.
- Do not run project-wide diagnostics during the edit loop; use `changed` mode.

## Procedure

1. Pick the command from the mode table above that matches your situation.
2. Run it.
3. If it fails, find the first failure in the triage table above and take its next action.
4. Apply a suppression only as a last resort, per the suppression rules above, with a justification comment on the same line.
5. Re-run the same command until it passes before moving to a broader mode (e.g. `changed` → `all`).

## Done means

- `scripts/checks.sh all` passes from a clean state.

## Stop and report when

- After 2 focused fix attempts on the same failure, stop and report the failure output plus your hypothesis.
