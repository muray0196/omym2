---
name: omym2-architecture-guardrails
description: Review any structural change in OMYM2 for dependency direction, port usage, file naming, and layer responsibility.
---

# OMYM2 Architecture Guardrails

## Inputs
- changed_files
- proposed_new_modules
- any new imports between layers

## Read first
- docs/development.md
- docs/testing.md
- tests/architecture/test_dependency_boundaries.py
- tests/architecture/test_source_files.py

## Steps
1. Map each changed file to one layer:
   - adapters
   - features
   - domain
   - shared
   - platform
2. For every new import, check whether it crosses a forbidden boundary.
3. For every new module, check snake_case naming and banned vague names.
4. For every usecase change, verify that concrete filesystem/DB/framework code stays behind a port.
5. For every adapter change, verify that business rules are not being introduced into repositories or I/O helpers.
6. Run architecture tests, then full quality gates if code changed.

## Checks
- domain must not import adapters or platform
- features must not import concrete adapters
- orchestration belongs in CLI/Web/platform, not cross-feature internals
- vague names such as utils/helpers/manager/service/common are not introduced

## Outputs
- boundary verdict: safe / unsafe
- blocking issues
- exact violating imports or files
- required refactor path
- required tests
- tests that prove compliance
- docs checked
