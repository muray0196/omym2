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
- AGENTS.md
- docs/development.md
- pyproject.toml
- .github/workflows/ci.yml

## Steps
1. Confirm whether the task changed code, tests, or docs that affect generated formatting.
2. Run or inspect commands in the documented order:
   - uv sync --locked --all-extras --dev
   - uv run ruff check --fix -q
   - uv run ruff format .
   - uv run basedpyright
   - uv run pytest -q --maxfail=1 --tb=line --show-capture=stdout
   - git diff --exit-code
3. Classify the first failure:
   - environment/setup
   - tool configuration
   - code logic
   - test expectation
   - generated diff only
4. If the failure is environment/setup, stop proposing product-code edits until the environment issue is isolated.
5. If the failure is code/test/doc related, identify the smallest affected file set.
6. Re-run only the narrowest relevant command, then the full documented sequence.

## Checks
- Do not invent substitute commands when the repo already defines commands.
- Do not mark work complete without running the full documented gate sequence when runnable.
- Distinguish install/runtime failures from product-code failures.

## Outputs
- classification
- first failing step
- minimum fix scope
- exact commands run
- remaining blockers
