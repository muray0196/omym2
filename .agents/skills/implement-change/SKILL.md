---
name: implement-change
description: Route OMYM2 implementation work to the applicable architecture, safety, frontend, test, documentation, and validation guidance. Use at the start of every code implementation task.
---

# Implement Change

## Procedure

1. Read `ARCHITECTURE.md` if it has not been read in this session.
2. Open every skill whose row matches the change before editing:

   | The change touches... | Open skill |
   | --- | --- |
   | Plan, PlanAction, Run, FileEvent, apply, undo, refresh, or any Library music file mutation | `plan-apply-safety` |
   | Stored paths, PathPolicy, Library identity, relink, or DB path columns | `path-identity-safety` |
   | DB tables, columns, indexes, migration files, or repository persistence | `db-schema-change` |
   | AppConfig shape, TOML config keys, defaults, allowed values, validation rules, or config serialization | `config-schema-change` |
   | A new module or package, or a new import between layers | `architecture-boundaries` |
   | Anything under `web/` or Web adapter routes | `web-frontend-change` |
   | Behavior documented under `docs/`, or any file under `docs/` | `update-docs` |

3. Use `docs/codebase/index.md` for placement and naming details not decided by a safety skill.
4. Open `write-tests` when adding or changing tests. Open `update-docs` when behavior described under `docs/` changes.
5. Use `validate` to select edit-loop and completion checks.

## Done means

- The applicable safety skills' completion conditions are satisfied.
- The completion check selected by `validate` passes.

## Stop and report when

- The request conflicts with `ARCHITECTURE.md` or an authoritative contract.
- Completion would require compatibility work or an architectural exception the user did not authorize.

State the conflict and the exact rule; do not work around it silently.
