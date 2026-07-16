---
type: Contract
title: Path Identity And Storage Contract
description: Defines Library, Track, and CompanionAsset identity, retained-root layouts and stored paths, protected inventory, cross-platform retained-object observation and mutation, and escape prevention.
tags: [paths, identity, storage, library, companions, unprocessed]
timestamp: 2026-07-16T06:02:32+09:00
---

# Path Identity And Storage Contract

This document is authoritative for Library, Track, and CompanionAsset identity,
relink behavior, stored path representation, PathResolver boundaries,
absolute-path exceptions, and path escape prevention.

Domain concepts are in [../DOMAIN.md](../DOMAIN.md). Storage responsibility is summarized in [../STORAGE.md](../STORAGE.md). Library registration behavior is in [../execution/organize.md](../execution/organize.md).

## Identity Rules

Library identity is stable by `library_id`, not by root path.

Track identity is stable by `track_id`, not by path, canonical path, content hash, or metadata hash.

CompanionAsset identity is stable by `companion_asset_id`, not by path,
content hash, owning action, or FileEvent.

Every Library-managed record belongs to exactly one Library through `library_id`.

`libraries.root_path` is mutable. It is used for runtime path resolution and must not be treated as Library identity.

Relink is an internal future concept, not an MVP user-facing operation. When it
is implemented, it must preserve `library_id`, update only
`libraries.root_path`, and not duplicate Tracks, CompanionAssets, Plans,
PlanActions, FileEvents, or Library-managed history records. It must not rewrite
Library-relative paths. Until then, `organize --library PATH` refuses an
unmatched path when another Library exists rather than guessing whether the
path is a moved Library or a second Library.

## Stored Path Representation

Stored paths are separated from filesystem execution paths.

| Field | Representation |
| --- | --- |
| `libraries.root_path` | Current absolute filesystem location for the Library |
| `config.paths.library` | Optional user-facing default or shortcut; not Library identity |
| `tracks.current_path` | Normalized path relative to the Library root |
| `tracks.canonical_path` | Normalized path relative to the Library root |
| `companion_assets.current_path` / `canonical_path` | Normalized paths relative to the Library root, including for removed assets |
| `plans.source_root_at_plan` | Nullable exact absolute source root retained by an external Add Plan |
| `plan_actions.target_path` | Library-root-relative when managed; absolute for unprocessed collection below the retained Add root and for Undo restoring an external import |
| `plan_actions.source_path` | Library-root-relative for managed Library sources; absolute for external Add audio/companion sources and both directions of an unprocessed move |
| `file_events.source_path` / `file_events.target_path` | Same path-reference convention as the corresponding PlanAction |

Stored Library-managed paths are relative to the Library root.

Relative Library paths must use `/` as the logical separator, must not start with `/`, and must not escape the Library root with `..`.

## PathResolver Boundary

When filesystem I/O is required, PathResolver combines `libraries.root_path` with a Library-root-relative path to create an absolute path.

Domain models and repositories do not resolve absolute paths.

PathPolicy generates Library-root-relative canonical paths. It does not join paths with the Library root and does not check filesystem existence.

Target-path collision comparison is an exact string match on the normalized Library-root-relative path — intentionally platform-independent, so it is case- and Unicode-form-sensitive rather than folding for case-insensitive or Unicode-normalization-insensitive filesystems. Filesystem-level differences that this comparison cannot see, such as a case-insensitive filesystem treating two distinct normalized paths as the same file, are caught fail-closed at apply time by the exclusive-create FileMover.

## Retained Observation And Mutation Boundary

Rooted observation and mutation share one platform-neutral invariant: a source
or target is authorized by the identity of opened filesystem objects below its
recorded root, never by a lexical or resolved pathname check alone. Observation
opens a no-follow root-to-leaf chain, reads identity and content from the opened
source, and revalidates the chain before returning the ephemeral
`FilesystemIdentity`. Mutation independently opens the chain after the pending
FileEvent commit, compares the live source with that token and the captured
content hash, and retains the required root, parent, source, and claimed-target
objects until the operation finishes.

Library-relative audio and companion paths are anchored to the opened Library
root. Unprocessed paths use the same boundary anchored to the retained Add
source root. Parent-directory segments and link-like descendants are rejected
inside the boundary. The target is claimed exclusively, its bytes and the
retained source bytes are verified against the captured hash, and the source is
deleted only after its identity and containment are rechecked. Failure cleanup
may delete only the exact target object claimed by this attempt. External
sources are still copied from a retained source object even though they have no
Library root. Any root, parent, source, or target replacement must fail closed
instead of redirecting the reviewed mutation.

### POSIX Mechanics

On POSIX, rooted traversal uses `dir_fd` operations and `O_NOFOLLOW`. Root,
directory, source, and target file descriptors remain open while identity and
containment are revalidated. The no-overwrite target claim is an atomic hard
link or an `O_CREAT | O_EXCL` copy fallback, and source deletion and failure
cleanup are descriptor-relative operations against the exact revalidated
directory entry.

### Native Windows Mechanics

On native Windows, rooted traversal retains a chain of Win32 `HANDLE` values
opened with `CreateFileW`. Every component uses
`FILE_FLAG_OPEN_REPARSE_POINT`; directories also use
`FILE_FLAG_BACKUP_SEMANTICS`, and any `FILE_ATTRIBUTE_REPARSE_POINT` is
rejected. Observation retains the root, each traversed parent, and the source;
it validates their final paths, volume/file identities, entry types, and
reparse metadata before reading or hashing the source. All retained handles
omit delete sharing so their entries cannot be replaced while open. During
mutation, source and target handles also request delete access, and target
creation uses `CREATE_NEW` for the no-overwrite claim. Content copying and
hashing operate through binary descriptors duplicated from the retained
handles. Root, parent, and leaf identities are revalidated before success
deletes the source through its exact retained handle; failure cleanup deletes
only the exact retained target handle created by that attempt.

## Add Source Inventory And Collection Protection

An Add source root is recorded as an exact absolute path. It cannot equal or
descend from the selected Library root. A source may contain the Library or
OMYM2-owned paths as nested descendants, but those subtrees are excluded rather
than scanned.

The complete regular-file inventory is optional. Add requests it only when
`companions.enabled` or `unprocessed.enabled` is true. When both are false, Add
uses the native audio-planning path without a complete inventory, preserving
the default Windows behavior. Whenever inventory is requested, companion
classification claims reserve recognized lyrics/artwork paths. If companion
processing is disabled and unprocessed collection is enabled, those claims are
classification-only and create no companion action, content snapshot, asset
ID, or dependency.

Unprocessed classification sees only regular, non-symlink inventory entries
strictly below that source root. Audio and companion classification claims take
precedence. The inventory also excludes:

* the configured unprocessed destination subtree, preventing recursive
  recollection;
* the selected Library subtree;
* the exact application Config, database, internal data/config/log paths
  supplied by platform composition; and
* the current log plus numeric rotating-log siblings.

These are precise exclusions, not a blanket exclusion of every ordinary file
beside the application root. A collection target is the exact absolute
`<source-root>/<portable-directory>/<source-relative-path>` value. Planning
blocks it with `invalid_path` when that target enters the Library or any
internal protected path, including a rotating log. Existing entries, including
dangling symlinks, block with `target_exists`. Apply revalidates the exact
recorded root/layout and the recorded Library exclusion before observation.

## Absolute External Path Exceptions

Absolute paths are allowed only where the path points outside Library-managed storage:

* an external add source, such as Incoming
* an external Add companion source below the retained `source_root_at_plan`
* both paths of a forward or inverse unprocessed-file move, each below the
  retained `source_root_at_plan`
* an Undo target that restores imported audio or a companion below that same
  retained source root
* user-facing config shortcuts such as `config.paths.library`
* `libraries.root_path`

Library-managed Track and CompanionAsset paths must not be stored as absolute
paths. Restoring a companion externally marks the asset removed while retaining
its last Library-relative managed paths.

Replanning a definitively failed external companion requires the new Add
selection to equal the source Plan's retained root; containment under some
different selected ancestor is insufficient. Library-relative companion
recovery remains anchored to the current Library root.

An absolute Undo target must equal the external source of the succeeded
add/import FileEvent identified by that Undo PlanAction's `reverses_event_id`;
the originating PlanAction must have imported the same Track, and the restore
source must equal that Track's current Library path, which may differ from the
original import target after later in-Library moves. Merely attaching a Track
ID to an absolute PlanAction target is not sufficient provenance. Companion
Undo additionally requires matching action/event type, stable
`companion_asset_id`, owner Track, same-Plan dependency evidence, and a
source event anchored below the source Plan's retained root.

Unprocessed Undo uses a separate exact-shape rule: the succeeded source event
must be `move_unprocessed_file`, its action must have no Track, companion,
owner, metadata, diagnostic, or dependency identity, and the inverse swaps the
same two absolute rooted paths. No current Config value may relabel them.

## PathPolicy Change

Changing PathPolicy invalidates prior registration for that Library.

After a PathPolicy change, `add` refuses to create a plan until the Library is registered again under the new PathPolicy. The expected remedy is `omym2 organize --library PATH`.

## Tests

Any path identity contract change requires tests for the affected representation or transition:

* path normalization
* parent-path escape rejection
* relink behavior, when relink is implemented
* Library identity stability
* Track identity stability
* CompanionAsset identity stability
* unprocessed source-root containment, protected-path exclusions, and exact
  forward/inverse path shape
* repository persistence of Library-root-relative paths
