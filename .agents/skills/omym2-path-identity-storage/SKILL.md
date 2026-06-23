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
- AGENTS.md
- docs/domain.md
- docs/storage.md
- docs/execution.md
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
   - mutable root path
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
- identity risks
- required schema/repository/usecase tests
- required docs updates
