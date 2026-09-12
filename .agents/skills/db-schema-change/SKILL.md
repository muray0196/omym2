---
name: db-schema-change
description: Check SQLite schema, migrations, and repository persistence changes. Distinguish schema changes needing a migration from query or row-mapping fixes.
---

# DB Schema Change

Authoritative docs: [docs/contracts/db-schema.md](../../../docs/contracts/db-schema.md), [docs/development/testing.md](../../../docs/development/testing.md)
(Contract Change Test Requirements), [docs/STORAGE.md](../../../docs/STORAGE.md).

## Non-negotiable invariants

1. Migration-safety rules (never edit or rename an applied migration; strict
   lexicographic filename ordering; single-transaction apply) are owned by
   [docs/contracts/db-schema.md](../../../docs/contracts/db-schema.md)'s Migration Safety Rules section — read it
   before writing a migration.

## Procedure

1. Determine whether the stored schema changes. Query, row-mapping, or transaction
   fixes using the existing schema need no migration or table-definition edit.
   For a schema change, add a file under `src/omym2/adapters/db/sqlite/migrations/` named
   `<prefix>_<description>.sql`, following the existing numeric prefix
   convention (see `202607160001_baseline.sql`). Discovery is
   automatic (packaged `*.sql` resources); no registration step is needed.
2. When a migration is needed, write it so it either fully applies or fails: the runner
   (`src/omym2/adapters/db/sqlite/migration_runner.py`) wraps each migration
   file and its `schema_migrations` marker in one transaction.
3. If any path column is touched, open `path-identity-safety`. When both
   skills apply, follow this skill's procedure first and apply
   `path-identity-safety`'s invariants throughout the work.

## Done means

- Changed table definitions are reflected in [docs/contracts/db-schema.md](../../../docs/contracts/db-schema.md) in
  the same change (open `update-docs`). Persistence-only fixes need focused
  regression coverage for the affected query, mapping, or transaction.
- Schema changes have tests per [docs/development/testing.md](../../../docs/development/testing.md)'s Contract Change Test Requirements
  table, DB schema contract row. Anchor:
  `tests/adapters/db/sqlite/test_sqlite_foundation.py`.

## Stop and report when

- A migration would drop or rewrite managed state beyond the requested change.
- The fix seems to require editing or renaming an already-applied migration.
- A migration would have to sort before existing ones to take effect.
- A repository would need to inspect stored JSON shape to make a business
  decision.
