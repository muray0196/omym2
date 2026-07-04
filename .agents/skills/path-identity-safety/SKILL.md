---
name: path-identity-safety
description: Safety checklist for changes touching stored paths, PathPolicy, Library identity, registration, relink, or DB storage of paths. Use before designing or reviewing such a change.
---

# Path / Identity Safety

Authoritative docs: `docs/contracts/path-identity-storage.md`, `docs/contracts/db-schema.md`, `docs/DOMAIN.md`, `docs/STORAGE.md`.

## Non-negotiable invariants

1. Library identity is `library_id` (stable UUIDv7), never the root path. Relinking a Library updates `root_path` only; `library_id` and all Tracks are untouched.
2. Track identity is path-independent: moving a file never changes its `track_id`.
3. Every Library-managed stored path is Library-root-relative and normalized. Absolute paths are stored only for explicitly external locations (e.g. import sources).
4. No stored path may escape its root: reject `..` segments and absolute values at the boundary.
5. `PathPolicy` is a pure domain service: no filesystem access, no config loading, deterministic output for the same input.
6. Repositories store and restore path values verbatim; they never normalize, resolve, or judge paths (that is domain/usecase work).

## Procedure

1. List every path field the change touches, then classify each one:

   | Field | Class |
   | --- | --- |
   | `current_path`, `canonical_path` (Track) | Library-root-relative |
   | `source_path` on add/import | absolute external path |
   | `target_path` (PlanAction) | Library-root-relative |
   | `root_path` (Library) | mutable absolute runtime root, NOT identity |

   If a field is not in this table, find its class in `docs/contracts/path-identity-storage.md` before continuing.
2. For each field, verify the invariant that matches its class still holds after your change.
3. Check the identity rules: does anything key on a path where it should key on `library_id` / `track_id`?
4. If the DB schema changes, follow `docs/contracts/db-schema.md` and add a migration under `adapters/db/sqlite/migrations/`.
5. Add tests for every changed representation or transition: normalization, relink, identity stability, root-relative persistence (`tests/shared/test_paths.py` and mirror locations are the anchors).

## Stop and report when

- A design needs an absolute path inside Library-managed storage.
- Library or Track identity would change as a side effect of a move, rename, or relink.
- PathPolicy would need I/O or config access to produce a result.
