# Implementation Plan

This document is authoritative for implementation order.

The implementation order is dependency-first and then vertical-slice-first. The goal is to avoid completing a command before the domain policy, persistence, and filesystem observation pieces required by that command exist.

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

## Phase 1: Project skeleton / architectural guardrails

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

## Phase 2: Domain model / pure policies

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

## Phase 3: Ports / usecase contracts / in-memory fakes

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

## Phase 4: Config adapter and validation

* default config
* TOML loader / saver
* config validation
* config hash calculation
* path policy validation
* config path resolution
* config show CLI
* config validate CLI

This phase should not perform Library scanning or DB registration yet.

## Phase 5: SQLite foundation

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

## Phase 6: Filesystem / metadata read adapters

* FileScanner implementation
* MetadataReader implementation using mutagen
* hash calculation
* FileSnapshotReader implementation
* PathResolver implementation
* inspect file usecase
* inspect CLI

This phase is read-only except for internal temporary test fixtures. File moving is deferred until apply.

## Phase 7: Setup vertical slice

* setup usecase implementation
* create config / DB
* initial Library scan
* capture file snapshots
* generate canonical paths
* register Tracks
* store Track paths as Library-root-relative paths
* setup CLI

`setup` is completed only after Config, SQLite, FileScanner, FileSnapshotReader, MetadataReader, hash calculation, PathPolicy, and IdGenerator are connected.

## Phase 8: Add plan vertical slice

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

## Phase 9: Apply vertical slice

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

## Phase 10: Refresh / organize vertical slices

* refresh usecase
* refresh CLI
* organize usecase
* organize CLI
* relocation plan creation for existing Library files
* `refresh --apply` orchestration
* `organize --apply` orchestration

Both refresh and organize reuse Plan creation and apply rather than moving files directly.

## Phase 11: Check / history / undo

* check usecase
* check CLI
* history usecase
* history CLI
* run detail usecase
* undo plan creation from succeeded FileEvents
* undo CLI
* `undo --apply` orchestration

Undo depends on Run and FileEvent history, so it comes after apply is durable enough to inspect.

## Phase 12: Web settings console

* local Web app skeleton
* settings display
* settings edit
* settings validation
* settings diff display
* path policy preview

The Web UI remains a settings console. It does not apply Plans in the initial version.

## Phase 13: Web read-only inspection

* history screen
* run detail screen
* check result screen
* tracks screen

These screens read existing usecases. They must not perform direct filesystem operations from routes or templates.
