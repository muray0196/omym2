# Domain

This document is authoritative for OMYM2 domain concepts, domain invariants, and ID design policy. Execution semantics are in [execution.md](execution.md), and persistence/path storage details are in [storage.md](storage.md). Any storage representation mentioned here is a domain-facing summary only.

The central concepts are independent from CLI, Web UI, SQLite, TOML, filesystem APIs, and metadata extraction libraries.

## AppConfig

Application behavior settings used by usecases.

AppConfig is the in-memory representation of user settings. It may be loaded from TOML by a ConfigStore adapter, but domain and usecases do not read TOML directly.

Usecases may receive AppConfig. Pure domain services should receive narrow config objects when possible. For example, PathPolicy should receive PathPolicyConfig instead of the entire AppConfig.

## FileScanEntry

A cheap filesystem discovery result produced while scanning a directory tree.

Representative fields:

* path
* size
* mtime
* file_extension

FileScanEntry is the output of FileScanner. It represents that a candidate file was found, but it does not contain music metadata, content hash, or metadata hash.

FileScanEntry must not be used to decide duplicates, metadata validity, or final movement by itself. It is only an input for later inspection.

## FileSnapshot

A complete observed state of one file at a certain point in time.

Representative fields:

* path
* size
* mtime
* file_extension
* content_hash
* metadata_hash
* metadata
* captured_at

FileSnapshot is created by a snapshot-capturing port after filesystem stat, metadata reading, and hash calculation have been performed. FileScanner does not create FileSnapshot.

FileSnapshot is not the identity of a managed track.

`size` and `mtime` may be used as optimization hints, but content equality must not rely only on them.

## TrackMetadata

Metadata read from a music file tag.

Representative fields:

* title
* artist
* album
* album_artist
* genre
* year
* track_number
* track_total
* disc_number
* disc_total

Filesystem attributes such as file extension or file size are not part of TrackMetadata.

Missing, empty, malformed, or inconsistent tag values are allowed at this layer. Validation and fallback are performed by usecases or PathPolicy according to AppConfig.

## PathPolicy

A pure domain service that generates the Library-root-relative canonical path for a track.

Input:

* TrackMetadata
* file_extension
* PathPolicyConfig

Output:

* canonical_path

`canonical_path` is a normalized relative path from the Library root. It is not an absolute path.

PathPolicy may normalize metadata values for path generation. This normalization is local to PathPolicy in the initial version and is not modeled as a separate domain object.

PathPolicy is deterministic and does not perform I/O. It does not join paths with the Library root and does not check whether the target path exists. Target existence is handled by usecases through filesystem ports and CollisionPolicy.

Initial template:

```text
{album_artist}/{year}_{album}/{disc}-{track}_{title}.{ext}
```

The initial template does not include hash-based suffixes. If the generated target path already exists, the PlanAction becomes blocked as a conflict. PathPolicy does not solve collisions by itself.

The GUI provides a PathPolicy preview.

```text
Metadata:
  album_artist: Aimer
  year: 2024
  album: Example Album
  disc: 1
  track: 3
  title: Example Song
  ext: flac

Template:
  {album_artist}/{year}_{album}/{disc}-{track}_{title}.{ext}

Preview:
  Aimer/2024_Example Album/1-03_Example Song.flac
```

## Library

A music Library managed by OMYM2.

A Library has stable identity independent of its current root path. The current root path is the filesystem location used to resolve Library-root-relative paths at runtime, but it is not the Library identity.

Representative fields:

* library_id
* root_path
* path_policy_hash
* registered_at
* status
* created_at
* updated_at

The `library_id` is the stable internal identity of the Library. The initial implementation uses UUIDv7 for `library_id`.

`root_path` is mutable because a Library may move to another directory. Moving a Library must preserve `library_id` and must not duplicate Tracks, Plans, PlanActions, FileEvents, or Library-managed history records.

Library registration behavior is defined in [execution.md](execution.md#library-registration-behavior), and storage is defined in [storage.md](storage.md#libraries).

## Track

The current managed state of one music file known to OMYM2.

Track is a DB-persisted domain entity. It represents OMYM2's last known state, not a guarantee that the actual file still exists at the recorded path.

Representative fields:

* track_id
* library_id
* current_path
* canonical_path
* content_hash
* metadata_hash
* metadata
* status
* first_seen_at
* last_seen_at
* updated_at

`current_path` and `canonical_path` are normalized paths relative to the Library root. They must not be stored as absolute paths for Library-managed Tracks.

The `track_id` is the stable internal identity of the Track. The initial implementation uses UUIDv7 for `track_id`.

`track_id` is generated when a Track is first recorded as managed state in OMYM2. It must not be derived from file path, canonical path, content hash, or metadata hash. Those values may change during normal operations such as add, organize, refresh, undo, and external tag correction.

Every Track belongs to exactly one Library through `library_id`. Track rows do not define whether the Library is registered.

Initial Track status examples:

* active
* removed

`missing` is reported by `check` in the initial version rather than automatically persisted as Track status.

## Plan

A scheduled set of actions before execution.

A Plan describes what OMYM2 intends to do, but no Library music file mutation has occurred yet. Plan creation is the boundary between calculation and execution.

Representative fields:

* plan_id
* library_id
* plan_type
* status
* created_at
* config_hash
* library_root_at_plan
* summary
* actions

Plan types:

* add
* organize
* refresh
* undo

Initial Plan status examples:

* ready
* applying
* applied
* partial_failed
* failed
* cancelled
* expired

Execution summary: a Plan stores reviewed action data, including `library_root_at_plan`, for later apply. The authoritative apply contract is in [execution.md](execution.md#apply-behavior), including stale-root handling in [Apply-Time Precondition Failure Behavior](execution.md#apply-time-precondition-failure-behavior).

A Plan is single-use in the initial version.

## PlanAction

A planned action for one file or one managed track inside a Plan.

PlanAction separates the kind of intended operation from its current status and from the reason why it may be blocked.

Representative fields:

* action_id
* plan_id
* library_id
* track_id (nullable)
* action_type
* source_path
* target_path
* content_hash_at_plan
* metadata_hash_at_plan
* status
* reason
* sort_order

Path representation summary: for Library music file destinations, `target_path` is stored as a normalized path relative to the owning Library root. `source_path` is stored as a Library-root-relative path when it points to an already managed Library file, and as an absolute path when it points outside the Library, such as an Incoming file. The authoritative storage policy is in [storage.md](storage.md#path-representation-policy).

File operations must resolve path references through PathResolver.

Initial action types:

* move
* skip

Initial action status examples:

* planned
* blocked
* applied
* failed

Execution summary: `apply` handles blocked and eligible PlanActions according to [execution.md](execution.md#apply-behavior).

Issues detected during plan creation are represented as `blocked`. Precondition failures detected during apply are represented as `failed`.

Blocked reason examples:

* target_exists
* missing_required_metadata
* invalid_path
* source_missing
* source_changed

Skip reason examples:

* duplicate_hash

`conflict` and `error` are not action types. They are represented as status and reason.

`track_id` may be nullable for PlanActions that target files not yet registered as Tracks, such as new files in an add plan.

## Run

An execution attempt for applying a Plan.

Execution summary: Run creation and status transitions follow [execution.md](execution.md#run-behavior).

Representative fields:

* run_id
* plan_id
* library_id
* status
* started_at
* completed_at
* error_summary

Run status examples:

* running
* succeeded
* partial_failed
* failed

A Run is not merely a historical label. It is the parent unit for FileEvents and the main unit used by history and undo.

## FileEvent

A durable operation log entry for one Library music file mutation.

Execution summary: FileEvent creation and result updates follow [execution.md](execution.md#fileevent-behavior).

Representative fields:

* event_id
* library_id
* run_id
* plan_action_id
* event_type
* source_path
* target_path
* status
* started_at
* completed_at
* error_code
* error_message
* sequence_no

Initial event type:

* move_file

DB-only state changes such as registering or updating Tracks are not FileEvents. They are performed by usecases and persisted in tracks / plan_actions / runs.

FileEvents are used for:

* run detail display
* diagnosing partial failures
* crash inspection
* undo plan creation

## CheckIssue

An inconsistency detected between OMYM2's last known managed state and the actual filesystem state.

Representative issue types:

* db_file_missing
* unmanaged_file_exists
* content_hash_changed
* metadata_hash_changed
* current_path_differs_from_canonical_path
* duplicate_candidate
* plan_source_changed
* pending_file_event_exists
* library_unregistered
* library_stale
* library_blocked

CheckIssue is not persisted as primary state in the initial version. It is calculated by `check` from the DB and filesystem observations.

Reported CheckIssues that refer to Library-managed files identify the owning Library through `library_id`.

## Domain Invariants

The following invariants belong to the domain / usecase layer, not to adapters:

* A Track has a stable `track_id` independent from path, canonical path, content hash, and metadata hash.
* A Library has stable identity independent of its current root path.
* Library-managed records belong to exactly one Library through `library_id`.
* The initial implementation generates `library_id` and `track_id` as UUIDv7.
* A Plan is reviewed and applied through recorded PlanActions.
* A Plan is single-use in the initial version.
* Applying a Plan must not recalculate target paths from the latest AppConfig.
* `canonical_path` and Track `current_path` are Library-root-relative paths, not absolute paths.
* Library music file mutations must be represented by FileEvents.
* FileEvents represent Library music file mutations only, not DB-only updates.
* Conflict judgment is not performed by DB repositories.
* PathPolicy is pure and does not check filesystem existence.
* Absolute path resolution is performed at I/O boundaries through PathResolver.
* Config loading and saving are adapter concerns.
* Metadata reading is an adapter concern.

## ID Design Policy

The file hash is not treated as the Track identity.

The initial implementation uses UUIDv7 for stable internal IDs.

```text
track_id        UUIDv7 generated when a Track is first recorded as managed state
library_id      UUIDv7 generated when a Library is first recorded
plan_id         UUIDv7 generated when a Plan is created
run_id          UUIDv7 generated when an apply attempt starts
action_id       UUIDv7 generated when a PlanAction is created
event_id        UUIDv7 generated when a FileEvent is created
```

`track_id` must not be derived from:

* file path
* canonical path
* content_hash
* metadata_hash

The reason is that paths, file contents, and metadata may change during normal OMYM2 operations such as add, organize, refresh, undo, and external tag correction.

The concepts are separated.

```text
track_id        stable internal ID in OMYM2
library_id      stable internal ID for the owning Library
content_hash    hash of the current file contents
metadata_hash   hash of the current metadata
current_path    last known Library-root-relative location
canonical_path  Library-root-relative location where the file should exist according to PathPolicy
```

The initial version may use a full-file hash for `content_hash`.

`metadata_hash` is used as a change detection hint. It must not be used as Track identity and must not decide file movement by itself.

Short IDs may be shown in CLI output for readability, but they are display aliases only. Persisted IDs and internal references use full UUIDv7 values.
