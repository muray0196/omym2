---
name: omym2-path-identity-storage
description: Review changes touching stored paths, PathPolicy, Library identity, registration, relink, or DB storage boundaries.
---

# OMYM2 Path Identity Storage

## Inputs
- changed_files
- whether the change touches DB schema/repository/config/path logic
- whether library registration or relink behavior changes

## Read first
- docs/DOMAIN.md
- docs/STORAGE.md
- docs/contracts/path-identity-storage.md
- docs/contracts/db-schema.md
- docs/execution/organize.md

## Read when config or path-policy behavior is in scope
- docs/contracts/config.md

## Read when implementation or tests are in scope
- src/omym2/shared/paths.py
- tests/shared/test_paths.py

## Steps
1. Identify every path field touched by the change:
   - current_path
   - canonical_path
   - source_path
   - target_path
   - root_path
2. Classify each field as:
   - Library-root-relative
   - absolute external path
   - mutable Library root path used for runtime resolution, not Library identity
3. Check identity rules:
   - library_id is stable
   - track_id is path-independent
   - relink updates root_path only
4. Check storage rules:
   - Library-managed paths are normalized relative paths
   - repositories do not invent business rules
   - PathPolicy stays pure and I/O-free
5. Require tests for every changed representation or transition.

## Checks
- no absolute path leaks into Library-managed storage
- no parent-path escape is allowed
- path policy changes invalidate registration as documented
- relink does not duplicate Library-managed records

## Outputs
- path representation verdict
- blocking issues
- identity risks
- required schema/repository/usecase tests
- required docs updates
- docs checked
