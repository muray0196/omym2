---
name: validate
description: Run OMYM2 quality gates and triage failures. Use when validating changes, before declaring work complete, or when a gate or CI command fails and you need the next action.
---

# Validate

## Mode table

| Situation | Command |
| --- | --- |
| After editing Python files (edit loop) | `scripts/checks.sh changed` |
| Agent completion with the repo `Stop` hook available | No manual command; the hook runs `scripts/checks.sh completion` |
| Completion when the repo `Stop` hook is unavailable or bypassed | `scripts/checks.sh completion` |
| After a `Stop` hook failure | Use the smallest mode that reproduces the first failure |
| Python-only full gates | `scripts/checks.sh py` |
| OpenAPI/generated-client drift only | `scripts/checks.sh api` |
| Frontend gates only | `scripts/checks.sh web` |
| Browser keyboard/axe E2E | `scripts/checks.sh e2e` |
| Wheel/sdist and installed-package gates | `scripts/checks.sh package` |
| Installed-package performance record | `scripts/checks.sh performance` |
| Docs bundle conformance | `scripts/checks.sh docs` |
| Architecture boundary / naming rules | `scripts/checks.sh arch` |
| Inspect one failing test | `scripts/checks.sh test <pytest-node-id>` |
| Deep-debug one failing test | `uv run pytest <pytest-node-id> -q --tb=long -s --show-capture=all` |

`scripts/checks.sh` wraps the authoritative commands in `docs/development/harness.md`. If the script is missing or itself broken, run those commands directly.

The wrapper discards successful gate output and reports one pass line. A failed
gate reports only a bounded tail and retains the complete combined output at the
printed temporary path. Use progressive diagnostics:

1. Act on the bounded failure first.
2. Reproduce only the first failure with the smallest mode; for pytest, use the
   reported node id with `scripts/checks.sh test`.
3. If the cause is still unclear, inspect a larger tail or a targeted range from
   the retained log. Do not read the whole log by default.
4. Run the exact failed command with full output only when the focused evidence
   remains insufficient. For pytest, the deep-debug command is the final step.

The wrapper requires an explicit mode and assumes dependencies are already
installed. Run `uv sync --locked --dev` after checkout or Python dependency
changes. Install frontend dependencies in `web/`. Do not reinstall dependencies
during ordinary edit loops or validation reruns.

Do not run `scripts/checks.sh completion` immediately before a normal Codex handoff.
The `Stop` hook cannot reuse a manual success, so doing both repeats the complete
completion check. Run it manually only when the hook is unavailable or bypassed,
a hook failure needs direct diagnosis, or an environment-only repair must be
verified. Environment-only repairs do not change the repository fingerprint, so
verify them manually before attempting completion again. Run `scripts/checks.sh
all` only when the user explicitly requests the full aggregate gate or when
diagnosing CI-equivalent behavior.

## Triage table

Fix the first failing gate before looking at later ones.

| First failure | Likely cause | Next action |
| --- | --- | --- |
| `uv` / `npm` / command not found | environment | Install per README; do not edit product code |
| `npm ci` fails | lockfile out of sync | Report it; do not hand-edit `package-lock.json` |
| `ModuleNotFoundError` for a dependency | env not synced | `uv sync` (Python) or `cd web && npm ci` (frontend) |
| generated API check fails | Pydantic/OpenAPI or client drift | Run `cd web && npm run api:generate`, review, and commit the coordinated schema/client change |
| static audit fails | stale or unsafe ignored output | Re-run `npm run build`, then `scripts/sync_web_static.py`; do not hand-edit `static_dist/` |
| package smoke imports `src/` | wrong interpreter or `PYTHONPATH` | Use the clean-install virtual-environment Python outside the checkout and clear `PYTHONPATH` |
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
3. If it fails, follow the progressive diagnostic flow above, find the first
   failure in the triage table, and take its next action.
4. Apply a suppression only as a last resort, per the suppression rules above, with a justification comment on the same line.
5. Re-run the same focused command until it passes.
6. Attempt completion and let the repo `Stop` hook run the path-aware completion gate. If the hook is unavailable or bypassed, run `scripts/checks.sh completion` manually instead.
7. After a hook failure, reproduce only the first failure with the smallest applicable mode. A repository edit changes the fingerprint and causes the hook to validate again; after an environment-only repair, run the completion gate manually because the fingerprint is unchanged.

## Done means

- Dependencies are synchronized when their manifests or lockfiles changed.
- Focused checks for the changed area pass.
- The final repository fingerprint is validated by the repo `Stop` hook, or by a manual `scripts/checks.sh completion` fallback when the hook is unavailable or bypassed.

## Stop and report when

- The failure requires a product decision, contract change, unavailable credential, or environment change outside the task's authority.
- Repeated evidence rules out the current hypotheses and no safe in-scope diagnostic remains; report the failure output and what was ruled out.
