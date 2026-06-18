# omym2 Preliminary Design Document v1.01

## 1. Overview

omym2 is a local tool for safely importing music files into an organized library.

The primary usage model is execution through the CLI. The GUI is a local settings and status console.

omym2 is not a full GUI music management application. It has the following character:

```text
Headless domain/usecase core + CLI runner + Web settings console
```

The main value of omym2 is not moving files quickly, but moving files through a reviewed Plan while keeping enough state and history to diagnose failures and recover safely.

## 2. Basic Policy

The basic policies of omym2 are as follows.

* Configuration files and DB is contained under the root directory, making the application portable. (exclude music library, incoming folder)
* Execution is primarily performed from the CLI.
* Settings can be changed and checked from the local Web UI.
* Domain / UseCase are independent from CLI / Web UI / DB / filesystem.
* Library music file mutations must always go through a Plan.
* Read-only scans, metadata reads, hash calculations, and inspections do not require a Plan.
* Feature-oriented Hexagonal Architecture is adopted.
* The src layout and file naming rules are fixed as part of the architecture.
* Core concepts such as Track / Plan / Run / FileEvent / PathPolicy are shared as a shared domain kernel.
* External I/O is confined to adapters.
* Execution history is recorded in the DB.
* Settings are managed as human-readable TOML files.
* Library-managed paths stored in the DB are normalized paths relative to the Library root. Absolute paths are resolved only at I/O boundaries.
* Tag editing is not supported.
* Relocation after tag correction is handled by refresh.

## 3. Primary Use Case

The primary use case of omym2 is to safely add new music files from an Incoming folder into the Library.

```text
Incoming folder
  ↓
scan
  ↓
create plan
  ↓
review
  ↓
apply
  ↓
Library
```

The daily entry point is `omym2 add`.

omym2 is not a tool that reorganizes the entire existing library every time. In daily use, it is treated as a tool for safely importing newly added tracks.

On first use, the existing Library must be registered into omym2's managed state. During setup, config / DB are created, and the existing Library is scanned.

```text
setup
  ↓
create config / DB
  ↓
scan existing Library
  ↓
record tracks
```

`setup` does not move or mutate Library music files. It may register existing files in the DB without creating a Plan because it does not perform Library music file mutations.

Relocation of the existing Library is separated from the daily `add` flow. When needed, `omym2 organize` creates an organization plan.

## 4. Non-Goals for the Initial Version

The initial version does not cover the following.

* Tag editing
* Automatic monitoring
* Electron / Tauri packaging
* Complex duplicate resolution
* Advanced library management
* Large-scale file operations through a full GUI
* Associated file handling such as cover images, cue files, lyrics, or booklets
* Audio-part hashing
* GUI-based plan application
* Automatic filesystem repair
* Retrying partially failed Plans

Tag correction is delegated to external tools. omym2 is responsible for re-evaluation and relocation after correction.

## 5. Usage Image

This section shows the intended user flow. Detailed command variants are listed in [16. Expected Commands](#16-expected-commands).

### 5.1 First Use

```bash
omym2 setup
```

`setup` creates config / DB and, unless disabled, scans the existing Library to register the current track state.

```text
setup
  ↓
create config / DB
  ↓
scan existing Library
  ↓
record tracks
```

`setup` does not move or mutate Library music files and does not require a Plan.

### 5.2 Daily Add Flow

```bash
omym2 add
```

The daily entry point is `add`. It scans Incoming or a specified source directory, creates an add plan, and leaves the user to review and apply it.

```text
Incoming folder
  ↓
scan
  ↓
create plan
  ↓
review
  ↓
apply
  ↓
Library
```

When direct execution is desired, `add --apply` creates and applies the plan in the same command. Confirmation skipping is represented by `ApplyOptions.yes` and shared by `apply` and commands that apply a created plan within the same command.

### 5.3 Plan Review and Apply

```bash
omym2 plans
omym2 apply <plan-id>
omym2 apply latest
```

`plans` displays created plans. `apply` applies a reviewed Plan. `latest` means the most recently created Plan with status `ready`.

A Plan is single-use in the initial version. Once apply starts, the same Plan must not be applied again. If recovery or retry is needed, the user creates a new Plan from the current DB and filesystem state.

### 5.4 Maintenance Flow

```bash
omym2 refresh <library-file>
omym2 organize
omym2 history
omym2 undo <run-id>
omym2 check
omym2 inspect <file>
omym2 settings
```

`refresh` re-evaluates metadata after external tag correction and creates a relocation plan when needed.

`organize` creates a move plan for existing Library files whose current path differs from the canonical path.

`history` and `undo` use Run and FileEvent history for review and rollback planning.

`check` is read-only and reports inconsistencies between the DB and the filesystem.

`settings` opens the local settings screen in a browser.

## 6. Role of the UI

The GUI in omym2 is a settings console, not an execution screen.

The main roles of the GUI are as follows.

* Setting the Library path
* Setting the Incoming path
* Editing the path policy
* Setting required metadata fields
* Setting behavior for duplicates
* Setting behavior for conflicts
* Validating settings
* Displaying diffs before and after settings changes
* Reviewing execution history
* Checking the state of the DB and filesystem

In the initial stage, the GUI focuses on read/write settings and read-only history / check views.

Large-scale file movement is left to the CLI.

## 7. Domain Concepts

The central concepts of omym2 are defined as domain-level concepts. They are independent from CLI, Web UI, SQLite, TOML, filesystem APIs, and metadata extraction libraries.

This section intentionally defines only the concepts required to build the initial foundation.

### AppConfig

Application behavior settings used by usecases.

AppConfig is the in-memory representation of user settings. It may be loaded from TOML by a ConfigStore adapter, but domain and usecases do not read TOML directly.

Usecases may receive AppConfig. Pure domain services should receive narrow config objects when possible. For example, PathPolicy should receive PathPolicyConfig instead of the entire AppConfig.

### FileScanEntry

A cheap filesystem discovery result produced while scanning a directory tree.

Representative fields:

* path
* size
* mtime
* file_extension

FileScanEntry is the output of FileScanner. It represents that a candidate file was found, but it does not contain music metadata, content hash, or metadata hash.

FileScanEntry must not be used to decide duplicates, metadata validity, or final movement by itself. It is only an input for later inspection.

### FileSnapshot

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

### TrackMetadata

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

### PathPolicy

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

### Track

The current managed state of one music file known to omym2.

Track is a DB-persisted domain entity. It represents omym2's last known state, not a guarantee that the actual file still exists at the recorded path.

Representative fields:

* track_id
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

`track_id` is generated when a Track is first registered in omym2. It must not be derived from file path, canonical path, content hash, or metadata hash. Those values may change during normal operations such as add, organize, refresh, undo, and external tag correction.

Initial Track status examples:

* active
* removed

`missing` is reported by `check` in the initial version rather than automatically persisted as Track status.

### Plan

A scheduled set of actions before execution.

A Plan describes what omym2 intends to do, but no Library music file mutation has occurred yet. Plan creation is the boundary between calculation and execution.

Representative fields:

* plan_id
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

A Plan must contain enough information to apply the reviewed operations safely. Applying a Plan must use recorded PlanActions. It must not recalculate target paths from the latest AppConfig because the user may have reviewed a different plan.

`library_root_at_plan` is the resolved Library root used when the Plan was created. If the current resolved Library root differs at apply time, the Plan must not be applied in the initial version and should be marked `expired` or `failed` according to the failure point.

A Plan is single-use in the initial version.

### PlanAction

A planned action for one file or one managed track inside a Plan.

PlanAction separates the kind of intended operation from its current status and from the reason why it may be blocked.

Representative fields:

* action_id
* plan_id
* track_id (nullable)
* action_type
* source_path
* target_path
* content_hash_at_plan
* metadata_hash_at_plan
* status
* reason
* sort_order

For Library music file destinations, `target_path` is stored as a normalized path relative to the Library root. `source_path` is stored as a Library-root-relative path when it points to an already managed Library file, and as an absolute path when it points outside the Library, such as an Incoming file. File operations must resolve these path references through PathResolver.

Initial action types:

* move
* skip

Initial action status examples:

* planned
* blocked
* applied
* failed

A Plan may be applied even if it contains blocked PlanActions. `apply` executes eligible planned actions and ignores blocked actions.

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

### Run

An execution attempt for applying a Plan.

A Run is created before executing Library music file mutations. It may succeed, fail, or partially fail.

Representative fields:

* run_id
* plan_id
* status
* started_at
* completed_at
* error_summary

Run status examples:

* running
* succeeded
* partial_failed
* failed
* cancelled

A Run is not merely a historical label. It is the parent unit for FileEvents and the main unit used by history and undo.

### FileEvent

A durable operation log entry for one Library music file mutation.

A FileEvent is created as `pending` before the Library music file mutation. After the mutation, it is updated to `succeeded` or `failed`.

Representative fields:

* event_id
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

### CheckIssue

An inconsistency detected between omym2's last known managed state and the actual filesystem state.

Representative issue types:

* db_file_missing
* unmanaged_file_exists
* content_hash_changed
* metadata_hash_changed
* current_path_differs_from_canonical_path
* duplicate_candidate
* plan_source_changed
* pending_file_event_exists

CheckIssue is not persisted as primary state in the initial version. It is calculated by `check` from the DB and filesystem observations.

### Domain Invariants

The following invariants belong to the domain / usecase layer, not to adapters:

* A Track has a stable `track_id` independent from path, canonical path, content hash, and metadata hash.
* The initial implementation generates `track_id` as UUIDv7.
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

## 8. Plan-Centered Execution Model

In omym2, Library music file mutations are not executed directly.

They must follow this flow.

```text
scan
  ↓
create plan
  ↓
review
  ↓
start run
  ↓
for each plan action:
    verify preconditions
    record file_event as pending
    execute Library music file mutation
    update file_event
    update track / plan_action
  ↓
finish run
```

This allows the CLI / GUI / tests to share the same processing model.

User-facing commands should be purpose-based. Internal Plan concepts should not dominate primary command names.

```text
user command     internal behavior
------------     -----------------
setup            initialize workspace and scan Library
add              create add plan
organize         create Library organize plan
refresh          create metadata refresh / relocate plan
apply            apply selected plan
check            compare DB and filesystem state
```

`setup` may register Tracks without creating a Plan because it does not perform Library music file mutations.

## 9. Config Design

Settings are managed in TOML, not SQLite.

Initial example:

```toml
version = 1

[paths]
library = "/Users/me/Music/Library"
incoming = "/Users/me/Music/Incoming"

[setup]
scan_library_on_setup = true

[add]
default_mode = "plan_first"
auto_apply = false

[organize]
default_mode = "plan_first"
auto_apply = false
only_misplaced = true

[refresh]
default_mode = "plan_first"
auto_apply = false

[path_policy]
template = "{album_artist}/{year}_{album}/{disc}-{track}_{title}.{ext}"
unknown_artist = "Unknown Artist"
unknown_album = "Unknown Album"
sanitize = true
max_filename_length = 180

[metadata]
prefer_album_artist = true
require_title = true
require_artist = true
require_album = false

[collision]
on_target_exists = "conflict"
on_duplicate_hash = "skip"
on_missing_metadata = "block"

[ui]
theme = "system"
show_advanced_settings = false
```

Expected location of the settings file:

```text
~/omym2/config/config.toml
```

Expected location of the SQLite DB:

```text
~/omym2/.data/omym2.sqlite3
```

The `.data/` directory is reserved for omym2 internal data under the application root.

Config has a version so that future migrations can be supported.

The initial config intentionally avoids associated-file handling, unprocessed-folder routing, delete-empty-directory policy, and hash suffix configuration. Those can be added later without changing the core Plan / Run / FileEvent model.

## 10. PathPolicy Design

File and folder naming rules are isolated as a pure domain service named PathPolicy and can be changed from Config.

Inputs to PathPolicy:

* TrackMetadata
* file extension
* PathPolicyConfig

Output from PathPolicy:

* canonical_path

The output `canonical_path` is a normalized relative path from the Library root. PathPolicy does not return an absolute path and does not join the path with `paths.library`.

Initial template:

```text
{album_artist}/{year}_{album}/{disc}-{track}_{title}.{ext}
```

The initial template does not include hash-based suffixes. If the generated target path already exists, the PlanAction becomes blocked as a conflict. PathPolicy does not solve collisions by itself.

The GUI provides a PathPolicy preview.

Example:

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

### 10.1 Path Representation Policy

Stored paths are separated from filesystem execution paths.

| Field | Representation |
| --- | --- |
| `config.paths.library` | User-configured Library path, resolved to an absolute path at runtime |
| `tracks.current_path` | Normalized path relative to the Library root |
| `tracks.canonical_path` | Normalized path relative to the Library root |
| `plan_actions.target_path` | Library-root-relative path when the target is a Library music file location |
| `plan_actions.source_path` | Library-root-relative path for managed Library sources; absolute path for external sources such as Incoming |
| `file_events.source_path` / `file_events.target_path` | Same path-reference convention as the corresponding PlanAction |

Relative Library paths must use `/` as the logical separator, must not start with `/`, and must not escape the Library root with `..`.

When filesystem I/O is required, PathResolver combines the resolved Library root with a Library-root-relative path to create an absolute path. Domain models and repositories should not perform this resolution themselves.

## 11. Role of the DB

The DB records omym2's last known managed state, scheduled plans, execution attempts, and durable Library music file operation logs.

The DB is not used as the editable settings store. Settings are managed as human-readable TOML files.

The DB is not the source of truth for the actual filesystem. The filesystem can diverge from the DB because users or external tools may move, delete, rename, or modify files. Such divergence is detected by `check`.

Main information to store:

```text
tracks
plans
plan_actions
runs
file_events
```

The DB adapter persists and restores domain models. It must not contain business rules such as conflict judgment, duplicate judgment, canonical path calculation, or metadata validation.

### DB Responsibility Boundary

The DB is responsible for:

* persisting managed track state
* persisting created plans and plan actions
* persisting apply attempts as runs
* persisting Library music file mutation logs as file_events
* supporting history, undo, check, and crash inspection
* enforcing basic relational consistency with primary keys and foreign keys

The DB is not responsible for:

* storing editable user settings
* reading TOML
* reading music metadata
* scanning the filesystem
* moving files
* calculating canonical paths
* deciding conflicts
* deciding duplicates
* validating metadata policy

### tracks

The current managed state of files known to omym2.

Minimum representative fields:

* track_id
* current_path
* canonical_path
* content_hash
* metadata_hash
* metadata_json
* status
* timestamps

`track_id` is generated by omym2 and remains stable for the lifetime of the managed Track. The DB stores omym2's last known Library-root-relative path and hashes. It does not prove that the file still exists or that the content has not changed.

### plans

Scheduled operations before execution.

Minimum representative fields:

* plan_id
* plan_type
* status
* created_at
* config_hash
* library_root_at_plan
* summary_json

A Plan must be applied based on its recorded PlanActions. It must not recalculate target paths from the latest AppConfig. The apply usecase must reject or expire a Plan if the current resolved Library root differs from `library_root_at_plan`.

### plan_actions

Each scheduled operation inside a Plan.

Minimum representative fields:

* action_id
* plan_id
* track_id (nullable)
* action_type
* source_path
* target_path
* content_hash_at_plan
* metadata_hash_at_plan
* status
* reason
* sort_order

`track_id` may be null for PlanActions that target files not yet registered as Tracks, such as new files in an add plan.

For actions that mutate Library music files, `target_path` is a Library-root-relative path. `source_path` is absolute only when the source is outside the Library.

`conflict` and `error` should not be stored as action types. They should be represented by `status` and `reason`.

### runs

Execution attempts for applying Plans.

Minimum representative fields:

* run_id
* plan_id
* status
* started_at
* completed_at
* error_summary

A Run is created before applying plan actions. If a failure occurs after some Library music file operations have succeeded, the Run becomes `partial_failed`.

### file_events

A durable operation log for Library music file mutations.

A file_event is recorded before executing a Library music file mutation as `pending`. After the mutation, it is updated to `succeeded` or `failed`.

Minimum representative fields:

* event_id
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

file_events are used for:

* run detail display
* diagnosing partial failures
* crash inspection
* undo plan creation

### Apply and DB Consistency

Library music file operations and DB transactions cannot be made fully atomic. Therefore, apply does not rely on one large transaction that covers the whole run.

Expected flow:

```text
1. Create a run as running.
2. Mark the Plan as applying.
3. Ignore blocked actions and process each eligible planned move action:
   a. Verify preconditions.
   b. If a precondition fails, mark the PlanAction as failed without executing a Library music file mutation.
   c. Record a file_event as pending.
   d. Execute the Library music file mutation.
   e. Update the file_event to succeeded or failed.
   f. Update tracks and plan_actions as needed.
4. Mark the run as succeeded, failed, or partial_failed.
5. Mark the Plan as applied, failed, or partial_failed.
```

If the process crashes, pending or partially recorded file_events are used to inspect what may have happened. The initial recovery policy is conservative: report the state through `check` and require manual review rather than automatically repairing the filesystem.

### Config and Reproducibility

The DB does not store editable settings. However, a Plan must preserve enough information to explain and safely apply the reviewed result.

In the initial version, this means:

* store concrete path references in plan_actions, using the path representation policy above
* store `config_hash` and `library_root_at_plan` in plans
* apply recorded plan_actions instead of recalculating paths from the latest Config
* reject or expire unapplied Plans when the resolved Library root has changed since plan creation

Full config snapshots or path policy snapshots are deferred until long-lived unapplied Plans require stronger reproducibility.

## 12. ID Design Policy

The file hash is not treated as the Track identity.

The initial implementation uses UUIDv7 for stable internal IDs.

```text
track_id        UUIDv7 generated when a Track is first registered
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

The reason is that paths, file contents, and metadata may change during normal omym2 operations such as add, organize, refresh, undo, and external tag correction.

The concepts are separated.

```text
track_id        stable internal ID in omym2
content_hash    hash of the current file contents
metadata_hash   hash of the current metadata
current_path    last known Library-root-relative location
canonical_path  Library-root-relative location where the file should exist according to PathPolicy
```

The initial version may use a full-file hash for `content_hash`.

`metadata_hash` is used as a change detection hint. It must not be used as Track identity and must not decide file movement by itself.

Short IDs may be shown in CLI output for readability, but they are display aliases only. Persisted IDs and internal references use full UUIDv7 values.

## 13. Role of refresh

refresh is an operation for re-evaluation and relocation after tag correction.

Targets can be file / directory / all.

```bash
omym2 refresh <file>
omym2 refresh <dir>
omym2 refresh --all
```

Expected flow:

```text
Correct tags with an external tag editor
  ↓
omym2 refresh <file>
  ↓
reload metadata
  ↓
recalculate canonical path
  ↓
create move plan if needed
  ↓
apply
  ↓
update DB
```

refresh does not move files directly. As a rule, it creates a Plan.

Stable `track_id` allows refresh to treat tag changes and canonical path changes as changes to the same managed Track, not as removal of one Track and creation of another.

Only when `--apply` is specified is the created plan applied within the same command.

```bash
omym2 refresh <file> --apply
```

## 14. Roles of setup / add / organize / check

Primary CLI commands are aligned with user goals, not internal processing names. Detailed command forms are listed in [16. Expected Commands](#16-expected-commands).

| Command | Primary responsibility | Creates Plan? | Mutates Library music files directly? |
| --- | --- | --- | --- |
| `setup` | Create config / DB, set Library / Incoming paths, and register existing Library tracks | No | No |
| `add` | Create an add plan from Incoming or a specified source directory | Yes | No, except through `--apply` orchestration |
| `organize` | Create a relocation plan for existing Library files whose current path differs from the canonical path | Yes | No, except through `--apply` orchestration |
| `check` | Detect inconsistencies between the DB and the filesystem | No | No |

`setup` may register Tracks without a Plan because it does not perform Library music file mutations.

`add` is the primary command name. `import` may be treated as an alias, but it is not the primary command name.

`organize` can operate on the entire existing Library, so it is always plan-first in the initial state.

`check` is read-only in the initial version. It reports issues such as missing DB files, unmanaged files, changed hashes, path differences, duplicate candidates, and pending file_events. `doctor` may be treated as an alias, but it is not the primary command name.

## 15. Role of undo

undo is performed per Run.

```text
run
  ↓
trace succeeded file_events in reverse order
  ↓
create undo plan
  ↓
apply
  ↓
restore to original paths
```

undo does not modify the filesystem directly. It goes through a Plan.

```bash
omym2 undo <run-id>
omym2 apply <undo-plan-id>
```

Only when applying within the same command is `--apply` used.

```bash
omym2 undo <run-id> --apply
```

If the restore destination is already occupied during undo, it is not overwritten automatically. It stops as a conflict and requires manual review.

Undo uses Run and FileEvent history. Stable `track_id` keeps the relationship between Track state and FileEvents even when paths, metadata, or hashes have changed.

## 16. Expected Commands

The initial CLI is expected to include the following.

```bash
# Initial setup
omym2 setup
omym2 setup --library ~/Music/Library --incoming ~/Music/Incoming
omym2 setup --no-scan

# Add new tracks
omym2 add
omym2 add <source-dir>
omym2 add --apply
omym2 add --apply --yes

# Organize existing Library
omym2 organize
omym2 organize --apply

# Plan
omym2 plans
omym2 apply <plan-id>
omym2 apply <plan-id> --yes
omym2 apply latest

# Re-evaluate after tag correction
omym2 refresh <file>
omym2 refresh <dir>
omym2 refresh --all
omym2 refresh <file> --apply

# History and recovery
omym2 history
omym2 undo <run-id>
omym2 undo <run-id> --apply

# Status check
omym2 check
omym2 inspect <file>

# Settings
omym2 config show
omym2 config validate
omym2 settings
```

Primary commands are purpose-based.

Internally, `add` / `organize` / `refresh` create Plans, and `apply` applies a Plan.

The following may be allowed as compatibility or auxiliary aliases.

```bash
omym2 import   # alias of add
omym2 runs     # alias of history
omym2 doctor   # alias of check
```

The CLI is the primary execution interface. Complex settings editing is left to the GUI.

## 17. Web UI Screen Ideas

Initial screens:

* Settings
* Path Policy Preview
* Runs
* Run Detail
* Check
* Tracks

In the initial stage, Web UI screens are for settings, preview, and read-only inspection. Applying Plans from the GUI is deferred.

## 18. Architecture

omym2 adopts Feature-oriented Hexagonal Architecture.

Core concepts such as Track / Plan / Run / FileEvent / PathPolicy are not split by feature. They are placed in `domain/` as the shared domain kernel for all of omym2.

Features are divided by user goal, such as `setup`, `add`, `organize`, `refresh`, `apply`, `undo`, `check`, `plans`, `history`, `inspect`, and `settings`.

CLI / Web call feature usecases as inbound adapters. DB / filesystem / metadata reader / config loader implement ports as outbound adapters.

### 18.1 Directory Structure

The Python package adopts the `src/` layout.

```text
src/
  omym2/
    domain/
      models/
        app_config.py
        track.py
        track_metadata.py
        file_scan_entry.py
        file_snapshot.py
        plan.py
        plan_action.py
        run.py
        file_event.py
        check_issue.py
      services/
        path_policy.py
        plan_builder.py
        collision_policy.py
        duplicate_policy.py
        metadata_fingerprint.py
        content_fingerprint.py
      errors.py

    features/
      common_ports.py

      setup/
        usecases/
          setup_workspace.py
        ports.py
        dto.py

      add/
        usecases/
          create_add_plan.py
        ports.py
        dto.py

      organize/
        usecases/
          create_organize_plan.py
        ports.py
        dto.py

      refresh/
        usecases/
          create_refresh_plan.py
        ports.py
        dto.py

      apply/
        usecases/
          apply_plan.py
        ports.py
        dto.py

      undo/
        usecases/
          create_undo_plan.py
        ports.py
        dto.py

      check/
        usecases/
          check_library.py
        ports.py
        dto.py

      plans/
        usecases/
          list_plans.py
          get_plan_detail.py
        ports.py
        dto.py

      history/
        usecases/
          list_runs.py
          get_run_detail.py
        ports.py
        dto.py

      inspect/
        usecases/
          inspect_file.py
        ports.py
        dto.py

      settings/
        usecases/
          load_settings.py
          save_settings.py
          validate_settings.py
          preview_path_policy.py
        ports.py
        dto.py

    adapters/
      cli/
        main.py
        app.py
        commands/
          setup.py
          add.py
          organize.py
          refresh.py
          apply.py
          undo.py
          check.py
          plans.py
          history.py
          inspect.py
          config.py
          settings.py
        args/
          paths.py
          apply_options.py
          output_options.py

      web/
        app.py
        routes/
          settings.py
          plans.py
          history.py
          check.py
          tracks.py
        schemas/
          settings_form.py
          path_policy_preview_form.py
        templates/
        static/

      db/
        sqlite/
          unit_of_work.py
          repositories.py
          migrations/
            202606160001_initial_schema.sql

      fs/
        file_scanner.py
        file_snapshot_reader.py
        file_mover.py
        path_resolver.py
        hash_calculator.py

      metadata/
        mutagen_reader.py

      config/
        toml_config_store.py
        config_validator.py
        default_config.py

    platform/
      wiring.py
      runtime.py
      app_context.py

    shared/
      result.py
      ids.py
      paths.py
      time.py
      typing.py
```

`empty_dir_cleaner.py` is deferred until delete-empty-directory behavior is explicitly designed.

### 18.2 Dependency Direction

```text
adapters/cli, adapters/web
  ↓
features/*/usecases/*.py
  ↓
domain/
  ↓
shared/
```

```text
adapters/db, adapters/fs, adapters/metadata, adapters/config
  ↓
features/*/ports.py or features/common_ports.py
  ↓
domain/
```

`platform/` is the composition root and wires features and adapters together.

### 18.3 Forbidden Dependencies

```text
domain → adapters
domain → platform
domain → db
domain → fs
domain → web
domain → cli

features → concrete db/fs/web/cli implementations
features → internal implementations of other features

adapters/web/routes → direct filesystem operations
adapters/cli/commands → direct filesystem operations
templates → filesystem operations
```

Direct imports between features are prohibited in principle. When multiple usecases are chained, it is done through orchestration in CLI / Web / platform.

For example, `omym2 add --apply` does not have `features/add` call `features/apply` directly. Instead, the CLI or platform calls ApplyPlanUseCase after executing AddUseCase.

### 18.4 Responsibilities of domain

`domain/` contains the core concepts of omym2 and pure domain rules.

Main targets:

* AppConfig
* Track
* TrackMetadata
* FileScanEntry
* FileSnapshot
* Plan
* PlanAction
* Run
* FileEvent
* PathPolicy
* CollisionPolicy
* DuplicatePolicy
* CheckIssue

`domain/` performs no I/O. It does not import DB / filesystem / HTTP / CLI / Web / TOML / mutagen.

PathPolicy is a pure domain service.

```text
metadata + file extension + path policy config
  ↓
Library-root-relative canonical_path
```

This process does not call `path.exists()` and does not join with the Library root. The usecase checks the existence of actual files through ports after PathResolver has resolved the Library-root-relative path to an absolute filesystem path.

### 18.5 Responsibilities of features

`features/` contains usecases divided by user goal.

* `setup`: create config / DB, initial Library scan
* `add`: create an add plan from Incoming / specified source
* `organize`: create a relocation plan for the existing Library
* `refresh`: reload metadata and create a relocation plan
* `apply`: apply a Plan and update run / file_events / tracks
* `undo`: create an undo plan from a run and apply it if needed
* `check`: detect inconsistencies between the DB and the filesystem
* `plans`: get plan lists and details
* `history`: get runs / file_events
* `inspect`: check metadata / hash / canonical path for a single file
* `settings`: read and write config, validate it, and preview path policy

Usecases access the external world through ports. They do not depend on concrete implementations such as SQLite / shutil / mutagen / FastAPI / Typer.

When a usecase needs files from a directory, it uses FileScanner only to discover FileScanEntry values. When it needs metadata or hashes, it captures FileSnapshot values through a separate port.

### 18.6 Responsibilities of adapters

`adapters/` implement ports and handle external I/O.

* `adapters/db/sqlite`: SQLite repositories / UnitOfWork
* `adapters/fs`: file discovery / snapshot capture / move / path operations / hash calculation
* `adapters/metadata`: metadata reading with mutagen
* `adapters/config`: TOML config store / validator / defaults
* `adapters/cli`: CLI commands
* `adapters/web`: local Web UI

Adapters may create and restore domain models. However, they must not contain business rules.

Bad example:

```python
# adapters/db/sqlite/repositories.py

if target_path_exists:
    action = PlanAction.conflict(...)
```

Conflict judgment is the responsibility of a domain service or usecase.

Good example:

```python
# adapters/db/sqlite/repositories.py

return Track(
    id=row["id"],
    current_path=row["current_path"],
    metadata_hash=row["metadata_hash"],
)
```

This only restores a domain model from persisted data, so it is allowed.

### 18.7 Ports and UnitOfWork

External I/O is expressed as ports.

Representative examples:

```python
class UnitOfWork(Protocol):
    tracks: TrackRepository
    plans: PlanRepository
    runs: RunRepository
    file_events: FileEventRepository

    def __enter__(self) -> "UnitOfWork": ...
    def __exit__(self, exc_type, exc, tb) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
```

```python
class FileScanner(Protocol):
    def scan(self, root: PathLike) -> list[FileScanEntry]: ...
```

```python
class FileSnapshotReader(Protocol):
    def capture(self, path: PathLike) -> FileSnapshot: ...
```

```python
class MetadataReader(Protocol):
    def read(self, path: PathLike) -> TrackMetadata: ...
```

FileScanner must not read tags or calculate hashes. FileSnapshotReader may compose filesystem stat, MetadataReader, hash calculation, and Clock, but it must not decide conflicts, duplicates, canonical paths, or PlanAction status.

```python
class FileMover(Protocol):
    def move(self, source: PathLike, target: PathLike) -> None: ...
```

```python
class ConfigStore(Protocol):
    def load(self) -> AppConfig: ...
    def save(self, config: AppConfig) -> None: ...
```

```python
class Clock(Protocol):
    def now(self) -> datetime: ...
```

```python
class IdGenerator(Protocol):
    def new_track_id(self) -> TrackId: ...
    def new_plan_id(self) -> PlanId: ...
    def new_run_id(self) -> RunId: ...
```

`Clock` and `IdGenerator` are also ports. This makes it possible to fix time and IDs during tests.

In the initial implementation, IdGenerator returns UUIDv7-backed IDs. Domain and usecases depend on typed IDs such as TrackId / PlanId / RunId, not on a concrete UUID library.

### 18.8 Transaction and Durable Operation Log

The basic policy is `1 usecase = 1 UnitOfWork`.

`apply` / `undo` are exceptions in practice because Library music file operations and DB transactions cannot be made fully atomic. They must use FileEvents as a durable operation log rather than relying on one huge transaction.

The detailed apply order is defined in [11. Role of the DB](#11-role-of-the-db), especially [Apply and DB Consistency](#apply-and-db-consistency). Architecture must only preserve the boundary: usecases coordinate the operation, adapters perform I/O through ports, and FileEvents record Library music file mutations before they are executed.

### 18.9 Responsibilities of shared

`shared/` contains only pure auxiliary primitives.

* Result type
* ID value object helpers
* Pure functions for path string processing
* Time type helpers
* Typing helpers

`shared/` does not depend on domain / features / adapters / platform.

## 19. src File Naming Rules

File naming under `src` is treated as part of Feature-oriented Hexagonal Architecture. Naming rules are constraints for preserving responsibility boundaries.

### 19.1 Common Rules

```text
Python module name   snake_case.py
Class name           PascalCase
Function / variable  snake_case
Constant             UPPER_SNAKE_CASE
```

Avoid ambiguous names.

```text
Names to avoid:
  utils.py
  helpers.py
  common.py
  manager.py
  service.py
```

Even when placing shared processing as an exception, use a concrete concern name.

### 19.2 Naming in domain

`domain/` is noun-based. Do not place names that imply I/O or execution procedures.

Examples:

```text
domain/models/
  track.py
  track_metadata.py
  file_scan_entry.py
  file_snapshot.py
  plan.py
  plan_action.py
  run.py
  file_event.py
  check_issue.py

domain/services/
  path_policy.py
  plan_builder.py
  collision_policy.py
  duplicate_policy.py
  metadata_fingerprint.py
  content_fingerprint.py
```

Even under `domain/services/`, do not append `_service.py` to file names. The directory already indicates that they are services.

### 19.3 Naming in features

`features/{feature}/` is divided by user goal.

```text
features/{feature}/
  usecases/
    {verb}_{object}.py
  ports.py
  dto.py
```

Examples:

```text
features/add/usecases/create_add_plan.py
features/apply/usecases/apply_plan.py
features/undo/usecases/create_undo_plan.py
features/check/usecases/check_library.py
```

Do not create `features/{feature}/domain/` or `features/{feature}/adapters/` in principle.

### 19.4 Naming in adapters

Adapter names may include technical names or role names.

Examples:

```text
adapters/cli/commands/add.py
adapters/web/routes/settings.py
adapters/db/sqlite/unit_of_work.py
adapters/fs/file_scanner.py
adapters/fs/file_snapshot_reader.py
adapters/fs/file_mover.py
adapters/metadata/mutagen_reader.py
adapters/config/toml_config_store.py
```

Do not use the name DAO in the DB adapter.

### 19.5 Naming Not Adopted

The following are not adopted.

```text
features/{feature}/domain/
features/{feature}/adapters/
platform/*_dao.py
*_service.py
utils.py
helpers.py
manager.py
common.py
```

## 20. Technical Policy

Initial assumptions:

```text
Language: Python
DB: SQLite
Config: TOML
Web: FastAPI + Jinja2 + htmx
CLI: Typer or argparse
Test: pytest
E2E: Playwright
Metadata extractor: mutagen
```

The Web UI runs on localhost as a local settings console.

## 21. Basic Policy on Failures

| Case | Policy |
| --- | --- |
| target path exists | conflict. Do not overwrite automatically |
| metadata is insufficient during plan creation | block the PlanAction |
| duplicate hash exists | skip candidate with `duplicate_hash` as the reason |
| source file missing during plan creation | block the PlanAction |
| source file missing at apply | fail the PlanAction and mark Run as failed or partial_failed |
| source hash changed during plan creation | block the PlanAction |
| source hash changed after plan creation at apply | fail the PlanAction and mark Run as failed or partial_failed |
| failure during move | mark file_event as failed and Run as partial_failed if prior Library music file mutations succeeded |
| tag mistake after apply | relocate with refresh |
| another file exists at undo destination | mark undo plan as conflict and do not overwrite automatically |
| DB and filesystem are out of sync | detect with check |
| pending file_event exists | report through check and require manual review |

## 22. Initial Implementation Order

The implementation order is dependency-first and then vertical-slice-first.

The goal is to avoid completing a command before the domain policy, persistence, and filesystem observation pieces required by that command exist.

```text
pure foundation
  ↓
ports and test fakes
  ↓
config / DB / read-only filesystem adapters
  ↓
setup vertical slice
  ↓
add plan vertical slice
  ↓
apply vertical slice
  ↓
refresh / organize / check / undo
  ↓
web UI
```

### Phase 1: Project skeleton / architectural guardrails

* `src/` package layout
* package entry point skeleton
* pytest setup
* source file naming convention test
* forbidden dependency import test
* basic shared primitives
* Result type
* typed ID value helpers
* pure path string helpers
* time type helpers

Phase 1 exists to make later implementation hard to place in the wrong layer.

### Phase 2: Domain model / pure policies

* AppConfig
* TrackId / PlanId / RunId / ActionId / EventId
* TrackMetadata
* FileScanEntry
* FileSnapshot
* Track
* Plan
* PlanAction
* Run
* FileEvent
* CheckIssue
* PathPolicy
* path normalization rules for Library-root-relative paths
* metadata fingerprint calculation policy
* content fingerprint calculation policy
* CollisionPolicy
* DuplicatePolicy

PathPolicy belongs here because setup, add, organize, and refresh all need canonical Library-root-relative paths.

### Phase 3: Ports / usecase contracts / in-memory fakes

* UnitOfWork port
* TrackRepository port
* PlanRepository port
* PlanActionRepository port
* RunRepository port
* FileEventRepository port
* FileScanner port
* FileSnapshotReader port
* MetadataReader port
* FileMover port
* ConfigStore port
* Clock port
* IdGenerator port using UUIDv7-backed IDs
* in-memory repositories for usecase tests
* setup / add / apply usecase skeletons
* refresh / organize / check / history / undo / inspect usecase skeletons

Usecase skeletons may exist early, but they should remain thin until their required adapters exist.

### Phase 4: Config adapter and validation

* default config
* TOML loader / saver
* config validation
* config hash calculation
* path policy validation
* config path resolution
* config show CLI
* config validate CLI

This phase should not perform Library scanning or DB registration yet.

### Phase 5: SQLite foundation

* SQLite schema
* migrations
* migration runner
* DB creation under `omym2/.data/`
* UnitOfWork implementation
* tracks repository
* plans repository
* plan_actions repository
* runs repository
* file_events repository

Plan and Track persistence must exist before completing setup scan, add plan creation, or apply.

### Phase 6: Filesystem / metadata read adapters

* FileScanner implementation
* MetadataReader implementation using mutagen
* hash calculation
* FileSnapshotReader implementation
* PathResolver implementation
* inspect file usecase
* inspect CLI

This phase is read-only except for internal temporary test fixtures. File moving is deferred until apply.

### Phase 7: Setup vertical slice

* setup usecase implementation
* create config / DB
* initial Library scan
* capture file snapshots
* generate canonical paths
* register Tracks
* store Track paths as Library-root-relative paths
* setup CLI

`setup` is completed only after Config, SQLite, FileScanner, FileSnapshotReader, MetadataReader, hash calculation, PathPolicy, and IdGenerator are connected.

### Phase 8: Add plan vertical slice

* create add plan usecase
* scan Incoming / specified source
* capture file snapshots
* generate target canonical paths
* duplicate hash skip judgment
* missing metadata block judgment
* target conflict block judgment
* persist Plan / PlanActions
* plans list usecase
* plan detail usecase
* add CLI
* plans CLI

This phase creates reviewed work, but does not move Library music files.

### Phase 9: Apply vertical slice

* FileMover implementation
* apply usecase
* precondition verification
* create Run before Library music file mutation
* mark Plan as applying
* record FileEvent as pending before each Library music file mutation
* execute file move
* update FileEvent / PlanAction / Track / Run / Plan statuses
* reject already-used Plan
* reject, expire, or fail Plan when Library root changed according to the failure point
* apply CLI
* `add --apply` orchestration

Apply is the first phase that mutates Library music files.

### Phase 10: Refresh / organize vertical slices

* refresh usecase
* refresh CLI
* organize usecase
* organize CLI
* relocation plan creation for existing Library files
* `refresh --apply` orchestration
* `organize --apply` orchestration

Both refresh and organize reuse Plan creation and apply rather than moving files directly.

### Phase 11: Check / history / undo

* check usecase
* check CLI
* history usecase
* history CLI
* run detail usecase
* undo plan creation from succeeded FileEvents
* undo CLI
* `undo --apply` orchestration

Undo depends on Run and FileEvent history, so it comes after apply is durable enough to inspect.

### Phase 12: Web settings console

* local Web app skeleton
* settings display
* settings edit
* settings validation
* settings diff display
* path policy preview

The Web UI remains a settings console. It does not apply Plans in the initial version.

### Phase 13: Web read-only inspection

* history screen
* run detail screen
* check result screen
* tracks screen

These screens read existing usecases. They must not perform direct filesystem operations from routes or templates.

## 23. Tests to Write First

```text
test_source_files_follow_naming_convention
test_usecase_does_not_import_concrete_sqlite_or_filesystem_adapter
test_domain_does_not_import_adapters_or_platform
test_config_loads_default
test_config_validation_fails_invalid_path_policy
test_db_path_is_under_app_root_data
test_track_id_is_generated_by_id_generator
test_track_id_is_not_derived_from_path_hash_or_metadata
test_track_paths_are_stored_relative_to_library_root
test_path_policy_generates_relative_path_without_hash_suffix
test_file_scanner_returns_file_scan_entries_not_snapshots
test_file_snapshot_reader_captures_metadata_and_hash
test_sqlite_migrations_create_required_tables
test_setup_creates_workspace_config_and_db
test_setup_scans_existing_library_when_enabled
test_setup_registers_tracks_with_relative_paths
test_add_plan_contains_move_action
test_add_plan_detects_target_conflict
test_add_plan_skips_duplicate_hash
test_add_plan_blocks_missing_required_metadata
test_apply_creates_run_before_file_move
test_apply_records_file_event_pending_before_file_move
test_apply_moves_file_and_updates_track
test_apply_marks_run_partial_failed_when_move_fails
test_plan_cannot_be_applied_twice
test_apply_uses_recorded_plan_action_target_path_not_latest_config
test_apply_expires_plan_when_library_root_changed
test_refresh_keeps_same_track_id_after_metadata_change
test_organize_creates_plan_for_misplaced_library_file
test_check_detects_missing_file_from_db
test_undo_creates_undo_plan_from_run
```

## 24. MVP Completion Conditions

The MVP is complete when the following are satisfied.

* `setup` can create config / DB
* `setup` can scan the existing Library, capture file snapshots, and register tracks
* registered tracks receive stable UUIDv7-based `track_id` values
* config.toml can be loaded
* canonical paths can be generated as Library-root-relative paths according to path policy
* Track `current_path` and `canonical_path` are stored as Library-root-relative paths in the DB
* an `add` plan can be created from the CLI
* a plan can be applied from the CLI
* apply creates a Run before Library music file mutation
* apply records a file_event as pending before Library music file mutation
* apply updates file_event / run / plan status after execution
* run / file_events remain in the DB
* a Plan cannot be applied twice
* `refresh` can create a relocation plan
* `organize` can create an organization plan for the existing Library
* `check` can detect basic inconsistencies between the DB and the filesystem
* `undo` can create an undo plan, and apply can perform basic rollback
* the Web UI can edit the main settings
* the Web UI can validate settings
