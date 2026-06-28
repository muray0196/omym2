# Path Identity And Storage Contract

This document is authoritative for Library identity, Track identity, relink behavior, stored path representation, PathResolver boundaries, absolute-path exceptions, and path escape prevention.

Domain concepts are in [../domain.md](../domain.md). Storage responsibility is summarized in [../storage.md](../storage.md). Library registration behavior is in [../execution/organize.md](../execution/organize.md).

## Identity Rules

Library identity is stable by `library_id`, not by root path.

Track identity is stable by `track_id`, not by path, canonical path, content hash, or metadata hash.

Every Library-managed record belongs to exactly one Library through `library_id`.

`libraries.root_path` is mutable. It is used for runtime path resolution and must not be treated as Library identity.

Relink is an internal concept. It preserves `library_id`, updates only `libraries.root_path`, and does not duplicate Tracks, Plans, PlanActions, FileEvents, or Library-managed history records. It does not rewrite Library-relative paths.

## Stored Path Representation

Stored paths are separated from filesystem execution paths.

| Field | Representation |
| --- | --- |
| `libraries.root_path` | Current absolute filesystem location for the Library |
| `config.paths.library` | Optional user-facing default or shortcut; not Library identity |
| `tracks.current_path` | Normalized path relative to the Library root |
| `tracks.canonical_path` | Normalized path relative to the Library root |
| `plan_actions.target_path` | Library-root-relative path when the target is a Library music file location; absolute path only for undo restoring an imported file outside the Library |
| `plan_actions.source_path` | Library-root-relative path for managed Library sources; absolute path for external sources such as Incoming |
| `file_events.source_path` / `file_events.target_path` | Same path-reference convention as the corresponding PlanAction |

Stored Library-managed paths are relative to the Library root.

Relative Library paths must use `/` as the logical separator, must not start with `/`, and must not escape the Library root with `..`.

## PathResolver Boundary

When filesystem I/O is required, PathResolver combines `libraries.root_path` with a Library-root-relative path to create an absolute path.

Domain models and repositories do not resolve absolute paths.

PathPolicy generates Library-root-relative canonical paths. It does not join paths with the Library root and does not check filesystem existence.

## Absolute External Path Exceptions

Absolute paths are allowed only where the path points outside Library-managed storage:

* an external add source, such as Incoming
* an undo target that restores an imported file outside the Library
* user-facing config shortcuts such as `config.paths.library`
* `libraries.root_path`

Library-managed Track paths must not be stored as absolute paths.

## PathPolicy Change

Changing PathPolicy invalidates prior registration for that Library.

After a PathPolicy change, `add` refuses to create a plan until the Library is registered again under the new PathPolicy. The expected remedy is `omym2 organize --library PATH`.

## Tests

Any path identity contract change requires tests for the affected representation or transition:

* path normalization
* parent-path escape rejection
* relink behavior
* Library identity stability
* Track identity stability
* repository persistence of Library-root-relative paths
