---
name: db-schema-change
description: Safety checklist for SQLite schema changes, migration files, and repository persistence updates. Use before designing or reviewing any change to DB tables, columns, indexes, or migrations.
---

# DB Schema Change

Authoritative docs: `docs/contracts/db-schema.md`, `docs/development/testing.md`
(Contract Change Test Requirements), `docs/STORAGE.md`.

## Non-negotiable invariants

1. Migrations preserve existing managed state or fail explicitly before
   partially changing schema state. No silent partial migrations.
2. Migration-safety rules (never edit or rename an applied migration; strict
   lexicographic filename ordering; single-transaction apply) are owned by
   `docs/contracts/db-schema.md`'s Migration Safety Rules section — read it
   before writing a migration.
3. Repositories persist and restore typed domain models verbatim; stored
   JSON shape (`metadata_json`, `summary_json`) never decides business
   policy.
4. Every Library-managed record carries `library_id`.

## Procedure

1. Add a new file under `src/omym2/adapters/db/sqlite/migrations/` named
   `<prefix>_<description>.sql`, following the existing numeric prefix
   convention (see `202606220001_initial_schema.sql`). Discovery is
   automatic (packaged `*.sql` resources); no registration step is needed.
2. Write the migration so it either fully applies or fails: the runner
   (`src/omym2/adapters/db/sqlite/migration_runner.py`) wraps each migration
   file and its `schema_migrations` marker in one transaction.
3. Update repositories and domain models in the same change so
   persist/restore stays verbatim.
4. If any path column is touched, open `path-identity-safety`. When both
   skills apply, follow this skill's procedure first and apply
   `path-identity-safety`'s invariants throughout the work.

## Done means

- The table definitions in `docs/contracts/db-schema.md` are updated in the
  same change (open `update-docs`).
- Tests are added per `docs/development/testing.md`'s Contract Change Test Requirements
  table, DB schema contract row. Anchor:
  `tests/adapters/db/sqlite/test_sqlite_foundation.py`.

## Stop and report when

- A migration would drop or rewrite existing managed state.
- The fix seems to require editing or renaming an already-applied migration.
- A migration would have to sort before existing ones to take effect.
- A repository would need to inspect stored JSON shape to make a business
  decision.
