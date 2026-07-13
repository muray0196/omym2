---
name: implement-change
description: Default end-to-end procedure for any OMYM2 Python code change. Use at the start of every implementation task to place files in the right layer, follow naming, validate, and route to the safety skills.
---

# Implement Change

## Procedure

1. **Classify the task** — Read `ARCHITECTURE.md` first if you have not read it this session. Then open every skill whose row matches the change, before writing code:

   | The change touches... | Open skill |
   | --- | --- |
   | Plan, PlanAction, Run, FileEvent, apply, undo, refresh, or any Library music file mutation | `plan-apply-safety` |
   | Stored paths, PathPolicy, Library identity, relink, or DB path columns | `path-identity-safety` |
   | DB tables, columns, indexes, migration files, or repository persistence | `db-schema-change` |
   | AppConfig shape, TOML config keys, defaults, allowed values, validation rules, or config serialization | `config-schema-change` |
   | A new module or package, or a new import between layers | `architecture-boundaries` |
   | Anything under `web/` or Web adapter routes | `web-frontend-change` |
   | Anything under `docs/` | `update-docs` |

2. **Place the code** — put new files where they belong and name them per convention:

   | Kind of code | Location | Naming |
   | --- | --- | --- |
   | Pure domain model | `src/omym2/domain/models/` | noun, e.g. `plan_action.py` |
   | Pure domain rule / policy | `src/omym2/domain/services/` | noun; never a `_service` suffix |
   | Usecase (one user goal) | `src/omym2/features/<feature>/usecases/` | `{verb}_{object}.py` |
   | Port definition | `src/omym2/features/<feature>/ports.py` or `src/omym2/features/common_ports.py` | — |
   | DTO | `src/omym2/features/<feature>/dto.py` | — |
   | SQLite / filesystem / metadata / config I/O | `src/omym2/adapters/{db,fs,metadata,config}/` | technical names allowed |
   | CLI command | `src/omym2/adapters/cli/commands/` | command name |
   | Web API route | `src/omym2/adapters/web/routes/` | — |
   | Wiring concrete adapters to feature ports / app assembly | `src/omym2/platform/` | composition module, e.g. `{concern}_composition.py` |
   | Pure helper without domain knowledge | `src/omym2/shared/` | concrete concern name |

   Never create a banned file name or directory — see `architecture-boundaries`'s New file checklist for the full list.

3. **Implement**
   1. Find one existing module of the same kind and copy its structure, imports, and test style. Good anchors: `src/omym2/features/apply/usecases/apply_plan.py` for usecases, `src/omym2/adapters/db/sqlite/` for repositories.
   2. Make the smallest change that satisfies the request. Do not refactor, rename, or reformat unrelated code.
   3. After each edit round, run the check mode `validate` selects for the edit-loop situation. Fix what it reports before continuing.

4. **Prove it**
   1. Add or update tests for every behavior change — open `write-tests` for placement and fixtures.
   2. If the change alters behavior described anywhere under `docs/`, update those docs in the same change — open `update-docs`.
   3. Before declaring done, run the check mode `validate` selects for the completion situation.

## Done means

- The check mode `validate` selects for the completion situation passes.
- Every behavior change has a test.
- Affected docs and their `index.md` entries are updated.

## Stop and report when

- The task seems to require mutating Library music files outside a Plan.
- Making it work requires an import that `architecture-boundaries` forbids.
- The same gate failure persists after 2 focused fix attempts.
- The request conflicts with `ARCHITECTURE.md` or a `docs/` contract.

State the conflict and the exact rule; do not work around it silently.
