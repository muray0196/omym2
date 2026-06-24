---
name: omym2-quality-triage
description: Run the documented quality gates for OMYM2, classify failures as environment/setup vs code/doc issues, and return the minimum next action.
---

# OMYM2 Quality Triage

## Inputs
- changed_files
- failing_command_or_ci_log
- whether local environment is available

## Read first
- docs/development.md
- pyproject.toml
- .github/workflows/ci.yml

## Steps
1. Confirm whether the task changed code, tests, or docs that affect generated formatting.
2. During the edit loop, run or inspect only the checks that apply to changed Python files:
   - files=$(git diff --name-only --diff-filter=ACMR -- '*.py' '*.pyi')
   - [ -n "$files" ] && uv run ruff check $files --fix --output-format=concise
   - [ -n "$files" ] && uv run ruff format $files -q
   - [ -n "$files" ] && uv run basedpyright $files --level error
3. If the same error remains after two focused fix attempts, stop and report the likely cause.
4. Before marking implementation work complete, run or inspect the final documented quality gates:
   - uv run ruff check . --output-format=concise
   - uv run ruff format . --check -q
   - uv run basedpyright
   - uv run pytest -q --maxfail=1 --tb=line --show-capture=stdout
5. When checking CI parity or worktree cleanliness, also inspect:
   - git diff --exit-code
6. Classify the first failure:
   - environment/setup
   - tool configuration
   - code logic
   - test expectation
   - generated diff only
7. If the failure is environment/setup, stop proposing product-code edits until the environment issue is isolated.
8. If the failure is code/test/doc related, identify the smallest affected file set.
9. Re-run only the narrowest relevant command, then the full documented quality gates.

## Checks
- Do not invent substitute commands when the repo already defines commands.
- Do not run full-project Ruff or Basedpyright diagnostics during the edit loop unless the change crosses many modules or focused checks cannot explain the failure.
- Do not mark work complete without running the full documented gate sequence when runnable.
- Do not present `git diff --exit-code` as a documented quality gate; it is a CI/worktree cleanliness check.
- Distinguish install/runtime failures from product-code failures.

## Outputs
- classification
- first failing step
- minimum fix scope
- exact commands run
- remaining blockers
- docs checked
