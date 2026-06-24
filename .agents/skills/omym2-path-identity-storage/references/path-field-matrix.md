# OMYM2 Path Field Matrix

This file is a review aid for the `omym2-path-identity-storage` skill.

It is not an authoritative specification. The authoritative sources are:

* `docs/domain.md`
* `docs/storage.md`
* `docs/execution.md`
* `src/omym2/shared/paths.py`

Use this matrix to classify path-like fields before changing schema, repositories, PathPolicy, PathResolver, library registration, relink, organize, apply, undo, or refresh behavior.

## Field Matrix

| Field                                   | Owner / likely location          | Representation                                                               | Scope                                          | Mutable?                                       | Rule                                                                                                                                                                          |
| --------------------------------------- | -------------------------------- | ---------------------------------------------------------------------------- | ---------------------------------------------- | ---------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `libraries.root_path`                   | Library record / storage         | Absolute path                                                                | Local filesystem                               | Yes, via relink                                | This is the current physical root of the library. Changing it must not create a new Library identity or duplicate Library-managed records.                                    |
| `library_id`                            | Library record / related records | Stable ID                                                                    | OMYM2 database                                 | No, except migration                           | Library identity is not derived from `root_path`. Moving a library requires relink, not re-registration as a different library.                                               |
| `tracks.current_path`                   | Track record                     | Library-root-relative path                                                   | Library-managed file                           | Yes                                            | Must never be stored as an absolute path. Must be normalized and must not escape the Library root.                                                                            |
| `tracks.canonical_path`                 | Track record or Plan target      | Library-root-relative path                                                   | Library-managed file                           | Yes, through reviewed change                   | Represents the desired organized path. Must not include a file extension placeholder unless the actual filename includes one.                                                 |
| `plan_actions.source_path`              | PlanAction                       | Library-root-relative path, or external source path depending on action type | Depends on action                              | No after plan creation                         | For Library-managed files, store relative paths. For external import sources, keep the representation explicitly external and do not confuse it with Library-managed storage. |
| `plan_actions.target_path`              | PlanAction                       | Library-root-relative path                                                   | Library-managed destination                    | No after plan creation                         | Apply must use the recorded target path. Do not recalculate from latest AppConfig or latest PathPolicy at apply time.                                                         |
| `file_events.source_path`               | FileEvent                        | Same representation as attempted source                                      | Audit / recovery                               | No after event creation, except status details | Records what was actually attempted. Must be written before Library music file mutation when mutation is attempted.                                                           |
| `file_events.target_path`               | FileEvent                        | Same representation as attempted target                                      | Audit / recovery                               | No after event creation, except status details | Records what was actually attempted. Must match the mutation attempt, not a later recomputation.                                                                              |
| `runs.library_root_at_run`              | Run record, if stored            | Absolute path snapshot                                                       | Local filesystem                               | No                                             | Used to detect root mismatch and explain what was applied against.                                                                                                            |
| `plans.library_root_at_plan`            | Plan record, if stored           | Absolute path snapshot                                                       | Local filesystem                               | No                                             | Apply must reject or expire a plan when the current library root no longer matches the reviewed plan context.                                                                 |
| `PathPolicy` input fields               | Config / policy                  | Values, not resolved paths                                                   | Pure policy                                    | Yes via config change                          | PathPolicy must remain pure and I/O-free. It produces relative path decisions, not filesystem mutations.                                                                      |
| `PathResolver` output                   | Domain/application service       | Library-root-relative path for Library-managed destinations                  | Library-managed file                           | Derived                                        | Must normalize output and reject parent traversal or absolute path leakage.                                                                                                   |
| CLI `--library` argument                | CLI adapter                      | User-provided path                                                           | Local filesystem                               | Per command invocation                         | This is input only. It must be resolved at the boundary and must not become Library identity.                                                                                 |
| CLI `--target` / import source argument | CLI adapter                      | User-provided path                                                           | External or Library-local depending on command | Per command invocation                         | Must be classified before use. Do not silently treat arbitrary external input as Library-managed storage.                                                                     |

## Representation Rules

Use these classifications when reviewing path changes.

| Classification        | Meaning                                        | Storage rule                                                                                           |
| --------------------- | ---------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| Library-root-relative | Path inside a registered Library root          | Store without root prefix. Normalize separators. Reject absolute paths and `..` escapes.               |
| Absolute local path   | Physical filesystem path                       | Allowed for library root snapshots, current root, CLI input, and external source references only.      |
| External source path  | Input file not yet managed by the Library      | Must be clearly distinguished from Library-managed paths.                                              |
| Derived path          | Computed output from PathPolicy / PathResolver | May be recomputed during planning, but not during apply for reviewed PlanActions.                      |
| Audit path            | Path recorded for attempted mutation           | Must reflect the actual attempted operation. Do not rewrite after the fact except for status metadata. |

## Review Checklist

Before accepting a change touching path or identity behavior, check:

* Library-managed paths are stored Library-root-relative.
* Absolute paths do not leak into `tracks.current_path`, `tracks.canonical_path`, or Library-managed `PlanAction` targets.
* `library_id` remains stable across root relocation.
* Relink updates the Library root without duplicating Library-managed records.
* Apply uses recorded `PlanAction` paths, not paths recalculated from current config.
* PathPolicy and PathResolver stay pure and do not perform filesystem mutation.
* Any path crossing a boundary is classified as Library-managed, external, or root snapshot.
* Tests cover absolute path rejection, parent traversal rejection, relink behavior, and apply path stability.

## Common Failure Patterns

Reject these patterns:

* Storing `/music/Library/Artist/Album/Track.flac` in `tracks.current_path`.
* Recomputing `target_path` during apply from the latest PathPolicy.
* Treating a changed `root_path` as a new Library.
* Duplicating Track rows after relink.
* Letting `../outside.flac` pass as a Library-relative path.
* Using CLI input paths directly inside domain records without classification.
* Putting filesystem existence checks inside PathPolicy.
* Updating FileEvent paths after mutation to match a newly computed value.

## Minimum Test Expectations

For path and identity changes, prefer tests that prove these contracts:

* absolute Library-managed paths are rejected
* parent traversal is rejected
* normalized Library-relative paths are stable
* relink changes `libraries.root_path` only
* relink does not duplicate Track records
* apply uses recorded `PlanAction.target_path`
* apply rejects or expires plans when the Library root changed after planning
* FileEvent records the attempted source and target paths before mutation
