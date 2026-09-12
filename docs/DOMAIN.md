---
type: Domain Model
title: Domain
description: Entity catalog with contractual fields, domain invariants, and UUIDv7 ID policy; the authoritative home for domain concepts.
tags: [domain-model, entities, invariants, artist-names, companions, unprocessed, operations, id-design]
timestamp: 2026-07-18T12:00:00+09:00
---

# Domain

Authoritative for OMYM2 domain concepts, domain invariants, and ID design policy. Execution semantics: [execution/](execution/). Persistence and path storage: [STORAGE.md](STORAGE.md), [contracts/path-identity-storage.md](contracts/path-identity-storage.md). Storage representations mentioned here are domain-facing summaries. Core concepts are independent of CLI, Web UI, SQLite, TOML, filesystem APIs, and metadata extraction libraries.

## AppConfig

In-memory representation of user settings, used by usecases. Loaded from TOML by a ConfigStore adapter; domain and usecases never read TOML directly. Pure domain services receive narrow config objects (e.g. PathPolicy receives PathPolicyConfig, not AppConfig). Schema and defaults: [contracts/config.md](contracts/config.md).

* Artist IDs are compact internal path values generated only when PathPolicy renders `{artist_id}`. AppConfig holds only generation tunables; per-artist IDs are not user-editable settings and not entity identities like `track_id` or `library_id`.
* Editable romanized artist-name mappings are feature data in SQLite, not AppConfig. They replace only display text used by artist path placeholders and supply the string passed to automatic compact-ID generation; they never rewrite raw tags.

## FileScanEntry

Cheap filesystem discovery result from scanning (output of FileScanner or a single-file FileStatReader observation). Fields: path, size, mtime, file_extension. Carries no music metadata, content hash, or metadata hash. Must not decide duplicates, metadata validity, or final movement by itself; it is only input for later inspection.

## FileSnapshot

Complete observed state of one file at a point in time, created by a snapshot-capturing port after stat, metadata read, and hash calculation (FileScanner never creates one). Fields: path, size, mtime, file_extension, content_hash, metadata_hash, metadata, filesystem_identity, captured_at. Not the identity of a managed track.

* A fresh filesystem capture carries an ephemeral token (device, inode, size, nanosecond mtime, nanosecond ctime), accepted only when the same state is observed before and after metadata and hash reads. Apply requires that token plus the captured content hash from its fresh precondition capture. FileMover verifies the token before claiming a target, and both token and bytes before unlinking the source. The token is not persisted; snapshots reconstructed from trusted Track stat baselines carry no token and are never sufficient for Apply.
* `size` and `mtime` are optimization hints, not proof of content equality; default workflows and apply must not rely on them alone. Explicit CLI `--trust-stat` may reconstruct a snapshot from the last verified Track state only under the eligibility and risk rules of the organize, refresh, and check execution contracts.

## TrackMetadata

Metadata read from a music file tag: title, artist, album, album_artist, genre, year, track_number, track_total, disc_number, disc_total. Filesystem attributes (extension, size) are not TrackMetadata. Missing, empty, malformed, or inconsistent values are allowed at this layer; validation and fallback belong to usecases or PathPolicy per AppConfig.

Raw TrackMetadata is never overwritten by a derived artist display name. Metadata hashes, Track persistence, album grouping, and artist-ID lookup keep using raw tag values even when a user-edited or automatic mapping supplies different display text.

## ArtistNameSourceKey

`derive_artist_name_source_key` produces the sole lookup key for editable artist-name mappings, treating the complete artist or album-artist value as one opaque string:

1. Missing input produces no key.
2. Normalize to Unicode NFC.
3. Replace each Unicode-whitespace run with one ASCII space; trim leading/trailing whitespace.
4. Empty result produces no key.

Derivation preserves case, punctuation, compatibility characters, source order, and multi-artist separators. It never applies PathPolicy sanitization, case folding, transliteration, or multi-artist splitting; canonically equivalent spellings and whitespace-only variants share a cache entry, other distinctions stay separate. Naming usecases derive the key before every accepted-name cache lookup and insertion. The exact raw string remains as the accepted record's `source_name`; deriving a key never changes TrackMetadata.

## ArtistNameProjection

Immutable derived value with the effective `artist` and `album_artist` display strings for one raw TrackMetadata value, assembled from resolver output before PathPolicy receives it. Missing mappings preserve the original strings; a composite multi-artist string is one opaque key. PathPolicy never loads mapping state, runs a language model, or contacts a provider. Any consumer turning resolver `ArtistNameResolution` results into a projection must do so explicitly and pass it onward; the resolver's existence does not make PathPolicy or ordinary path projection perform cache, model, or provider work.

## Artist Name Batch Resolution

The shared resolver accepts artist and album-artist source values as one batch and resolves each complete value with this precedence:

```text
saved original-to-English mapping by ArtistNameSourceKey
-> newly accepted MusicBrainz result when eligible
-> original source value
```

* Deduplicates the batch by whole-string source key; at most one accepted-cache lookup and, on an eligible miss, at most one provider lookup per distinct key. The resolved display value is reused for every occurrence of that key. The resolver never splits a source into artist components or reorders them. Missing and whitespace-only values produce no key and remain unchanged.
* Returns one `ArtistNameResolution` per input, in input order, retaining `source_name` and `source_key`, supplying the effective `resolved_name`, and recording provenance: `user_preference`, `accepted_musicbrainz`, `new_musicbrainz`, or `original`. A kept-original result may carry a stable issue (ineligibility, unavailability, low confidence, no confident match, ambiguity). Provider provenance is carried by the associated `AcceptedArtistName` mapping; TrackMetadata is never modified. `user_preference` means the saved mapping was added or last corrected by the user — no second TOML preference layer exists.
* Only positive provider results are accepted automatically. Automatic insertion is sticky: a later lookup cannot replace the row for the same source key. Users may add, edit, or delete mappings in Settings; an edit marks the row user-supplied and removes provider provenance. If another writer wins an automatic insert race, the persisted winner supplies the resolved value. Misses, ambiguity, ineligibility, model/provider unavailability, malformed responses, timeouts, and other provider failures are not negative cache entries; they preserve the original value and are normal outcomes, not caller errors.

### Plan Review Diagnostics

When an Add, Organize, or Refresh candidate reaches artist-name resolution and becomes a PlanAction, the action records a review-only diagnostic pair for its artist and album-artist fields: source value, resolved value, provenance, and nullable issue as observed while the target path was calculated. A missing field is still an explicit resolution outcome. Candidates blocked before resolution and Undo actions record no pair. Plan review reads only the recorded snapshot — no mapping reload, no MusicBrainz. Apply preserves the snapshot while changing action status and executes only recorded paths.

### Automatic lookup eligibility

A cache miss triggers a new MusicBrainz lookup only when all hold:

* persisted automatic lookup is enabled
* the source contains no ASCII comma (`U+002C`); comma-composite values remain unresolved by automatic lookup
* the source contains at least one alphabetic character outside the Unicode Latin script

Latin-only names (including diacritics) and values without alphabetic characters never contact MusicBrainz. Japanese, Chinese, Korean, Cyrillic, and mixed-script sources are eligible. Saved mappings still apply to ineligible values. Persisted opt-out records `automatic_lookup_disabled`; an otherwise eligible source not requiring romanization records `romanization_not_required`. Each disables only the new provider lookup, not mapping resolution.

### Deterministic MusicBrainz acceptance

* Candidates rank by numeric score descending. The top candidate is considered only when its score is at least `95`. If the highest-scoring runner-up with a different MusicBrainz artist identity is within `5` score points (including exactly `5`), the result is ambiguous and not accepted. Repeated rows for the same artist identity are coalesced by identity and never create runner-up ambiguity; their alias facts are one unordered set.
* An accepted candidate must carry a valid MusicBrainz artist identity and a usable Latin display name. Name selection tiers, in order:
  1. a primary `ja-Latn` alias, its Latin `sort-name` before its Latin `name`
  2. the Latin artist `sort-name`
* Aliases are an unordered set; provider response order is never a tie-breaker. `ja-Latn` matching is case-insensitive and accepts a hyphen or underscore separator. Commas in an alias or artist `sort-name` normalize to spaces, preserving family-name order (`Sakamoto, Ryuichi` → `Sakamoto Ryuichi`). Duplicate aliases preserve primary status from any duplicate observation. English and other aliases do not outrank the artist `sort-name`. A usable Latin display name is nonblank, contains at least one Latin-script alphabetic code point, and contains no non-Latin alphabetic code point.

## PathPolicy

Pure domain service generating the Library-root-relative canonical path for a track. Input: TrackMetadata, file_extension, PathPolicyConfig, optional already-derived ArtistNameProjection. Output: `canonical_path`, a normalized relative path from the Library root (never absolute).

* Deterministic, no I/O. Does not join paths with the Library root or check target existence. Planning usecases check generated targets through filesystem ports and CollisionPolicy; an occupied target is recorded as a blocked PlanAction with the documented conflict reason — PathPolicy neither performs that I/O nor solves collisions.
* May normalize metadata values for path generation. Artist and album-artist display values are resolved before rendering and passed explicitly; PathPolicy reads no AppConfig preferences or provider state. Source extensions normalize to lowercase when appended.
* Sanitization (NFKC normalization, uniform unsafe-character replacement, UTF-8 component limits, Windows reserved-name protection, extension preservation) is an OMYM2 portability rule, not compatibility with another application. Exact behavior, allowed placeholders, initial template, preview, and validation: [contracts/config.md](contracts/config.md#pathpolicyconfig).
* Templates render a root-relative destination path stem and must not include file extensions. The destination extension is derived from the source suffix and appended after rendering; the final PlanAction target path is recorded with extension, and Apply uses the recorded path without recalculation.
* With `{artist_id}`: PathPolicy first checks an already-loaded internal ID by the raw metadata source key; on a miss it passes the already-derived Latin display name (falling back to raw source text) to the pure ID generator. MusicBrainz HTTP lookup is a feature/adapter concern and must not run during canonical path generation. The ID generator compatibility-decomposes Latin diacritics before retaining ASCII letters and digits, so accented letters keep their base character.

## Library

A music Library managed by OMYM2, with stable identity independent of its current root path.

Fields: library_id, root_path, path_policy_hash, registered_at, status, created_at, updated_at.

* `library_id` (UUIDv7) is the stable internal identity. `root_path` is the mutable current filesystem location used to resolve root-relative paths at runtime; it is not the identity.
* A future relink must preserve `library_id` and must not duplicate Tracks, Plans, PlanActions, FileEvents, or Library-managed history records.
* Status values: [contracts/status-reason-catalog.md](contracts/status-reason-catalog.md#library-status). Registration behavior: [execution/organize.md](execution/organize.md#library-registration-behavior). Storage: [contracts/path-identity-storage.md](contracts/path-identity-storage.md).

## Track

DB-persisted current managed state of one music file — OMYM2's last known state, not a guarantee the file still exists at the recorded path.

Fields: track_id, library_id, current_path, canonical_path, content_hash, metadata_hash, size (nullable), mtime (nullable), metadata, status, first_seen_at, last_seen_at, updated_at.

* `track_id` (UUIDv7) is generated when a Track is first recorded as managed state. It must not be derived from file path, canonical path, content hash, or metadata hash — those change during normal add, organize, refresh, undo, and external tag correction.
* `current_path` and `canonical_path` are normalized Library-root-relative; never absolute for Library-managed Tracks.
* Every Track belongs to exactly one Library through `library_id`; Track rows do not define Library registration.
* `size`/`mtime` are the optional stat baseline from a verified snapshot (existing Tracks may have none) — change-detection hints only, not identity or content-equality proof. Only an explicit trust-stat workflow may treat an exact complete match as permission to reuse the last verified hashes and metadata; apply always captures the source.
* Status values: [contracts/status-reason-catalog.md](contracts/status-reason-catalog.md#track-status). `missing` is reported by `check` in the initial version, not automatically persisted as Track status.

## CompanionAsset

Current managed state of one lyrics or artwork file associated with a Track. Not a Track: it has its own stable `companion_asset_id`, carries no music metadata, and never changes `track_id` identity or meaning.

Fields: companion_asset_id, library_id, kind (`lyrics` | `artwork`), owner_track_id, current_path, canonical_path, content_hash, size/mtime (nullable), status (`active` | `removed`), first_seen_at, last_seen_at, updated_at.

* `current_path`/`canonical_path` stay normalized Library-root-relative even after an external Add Undo marks the asset removed. Identity is independent of path, hash, owner action, and Plan history.
* Organize may create or refresh an already canonical asset from a verified observation without a file mutation. A successful relocation preserves the ID and `first_seen_at`; failed or unknown mutations never advance managed state.

### Companion Association

Deterministic classification over regular, non-symlink source inventory:

* case-insensitive `.lrc` is lyrics; associates with the single same-directory audio candidate having the same stem
* case-insensitive `.jpg`/`.png` is directory artwork; represented once per source file, not once per Track
* artwork's semantic owner is the first audio candidate in source-path order; it depends on every audio candidate in that source directory
* artwork has a target only when every associated audio target has the same parent, preserving its source basename below that parent

An ambiguous lyrics owner or divergent artwork target parents produce a reviewable blocked companion action, never a guessed association. Planning records the semantic owner separately from every execution dependency.

With companion processing enabled, Add may turn these claims into new companion actions. When unprocessed processing alone requests inventory, the same classification reserves recognized companion paths from leftover collection but creates no companion action, content snapshot, asset ID, or dependency. Check performs this classification for unmanaged-companion discovery only when companion processing is enabled; managed assets and recorded Plan/event diagnostics are checked regardless of the toggle.

## Unprocessed Collection Evidence

An unprocessed file is a regular, non-symlink Add source left unclaimed after audio and companion classification. Unprocessed-only Add inventory still uses classification-only companion claims, so a recognized `.lrc`, `.jpg`, or `.png` path is not a leftover even when new companion actions are disabled. Collection creates no third managed Library entity: the file is neither Track nor CompanionAsset and has no stable entity ID, owner, metadata, or Library-relative managed path.

Durable identity is the reviewed `PlanAction.action_id` followed by the attempted `FileEvent.event_id`. A forward `move_unprocessed` action records:

* `track_id`, `companion_asset_id`, and `owner_action_id` as null; no dependencies or artist-name diagnostics
* absolute source and target anchored below the Plan's retained `source_root_at_plan`
* a target shaped exactly `<source-root>/<portable-directory>/<source-relative-path>`
* `content_hash_at_plan` from a rooted content-only snapshot; null `metadata_hash_at_plan`

The inverse action keeps the same trackless, content-only shape and swaps the recorded paths only after exact succeeded-event provenance is proven. Current Config does not relabel either path.

## Plan

A scheduled set of actions before execution — the boundary between calculation and execution; no Library-managed mutation has occurred yet.

Fields: plan_id, library_id, plan_type, status, created_at, config_hash, library_root_at_plan, source_root_at_plan (nullable), source_run_id (nullable; undo Plans only), summary, actions.

Plan types: add, organize, refresh, undo. Status values: [contracts/status-reason-catalog.md](contracts/status-reason-catalog.md#plan-status).

* A Plan is single-use in the initial version.
* A Plan stores reviewed action data, including `library_root_at_plan`, for later apply. An Add Plan retains `source_root_at_plan` so absolute external audio, companion, and unprocessed sources/targets stay anchored to the exact reviewed source root. An Undo Plan copies that root from the source Plan when reversing an external import; Organize and Refresh leave it null. Apply contract, including stale-root handling: [Apply-Time Precondition Failures](execution/apply.md#apply-time-precondition-failures).
* An undo Plan records the terminal Run it reverses in `source_run_id` — provenance and deduplication state, not a display-only link. Non-undo Plans have no source Run.

## PlanAction

A planned action for one file or one managed Track inside a Plan. Separates the kind of intended operation from its current status and its blocked reason.

Fields: action_id, plan_id, library_id, track_id (nullable), action_type, source_path, target_path, reverses_event_id (nullable; Undo only), companion_asset_id (nullable), owner_action_id (nullable), content_hash_at_plan, metadata_hash_at_plan, status, reason, sort_order.

* Paths: managed Library destinations are normalized root-relative; external Add sources are absolute; a reviewed unprocessed action stores both paths absolute below the retained source root; an Undo of an external import also has an absolute target. Authoritative: [contracts/path-identity-storage.md](contracts/path-identity-storage.md). File operations resolve path references through PathResolver.
* Allowed action types, statuses, reasons: [contracts/status-reason-catalog.md](contracts/status-reason-catalog.md#planaction-action-type). Apply handling of blocked/eligible actions: [execution/apply.md](execution/apply.md#apply-behavior).
* Issues detected during plan creation are `blocked`; precondition failures during apply are `failed`. `conflict` and `error` are status/reason, not action types.
* `track_id` may be null for files not yet registered as Tracks (e.g. new Add files); necessarily null for unprocessed actions.
* Lyrics/artwork actions preallocate or reuse `companion_asset_id`; Plan creation never creates managed companion state before a reviewed mutation succeeds. The semantic owner is the existing `track_id`, an optional same-Plan audio `owner_action_id`, or both when the Track already exists; Apply resolves the final owner Track from this evidence. The separate durable dependency relation records every action that must be applied first: same-Plan, never the action itself, never inferred from sort order or ownership. Shared artwork can have one semantic owner while depending on every associated audio action.
* Each Undo PlanAction records the succeeded source FileEvent it reverses in `reverses_event_id` (null for non-Undo actions). This durable provenance lets later Undo generation distinguish an event already reversed by a prior partial attempt from one still eligible; path/Track matching alone is not identity.

## Run

An execution attempt for applying a Plan — the parent unit for FileEvents and the main unit for history and undo, not merely a historical label.

Fields: run_id, plan_id, library_id, status, started_at, completed_at, error_summary.

Creation and transitions: [execution/model.md](execution/model.md#run-behavior), [execution/apply.md](execution/apply.md#run-status). Status values: [contracts/status-reason-catalog.md](contracts/status-reason-catalog.md#run-status).

## FileEvent

Durable mutation-log entry for one reviewed audio, companion, or unprocessed-file mutation.

Fields: event_id, library_id, run_id, plan_action_id, event_type, source_path, target_path, status, started_at, completed_at, error_code, error_message, sequence_no, companion_asset_id (nullable).

* Behavior: [execution/model.md](execution/model.md#fileevent-behavior), [execution/apply.md](execution/apply.md#fileevent-status). Allowed types, statuses, error-code policy: [contracts/status-reason-catalog.md](contracts/status-reason-catalog.md#fileevent-event-type).
* Companion events retain `companion_asset_id` and use their closed lyrics or artwork event type. DB-only state changes (e.g. registering an already canonical Track or CompanionAsset) are not FileEvents.
* An unprocessed event uses `move_unprocessed_file`, retains absolute paths below the source Plan's root, and has no Track or CompanionAsset identity. Its succeeded state is durable evidence for Check and Undo, not managed Library state.
* Used for run detail display, diagnosing partial failures, crash inspection, and undo plan creation.

## CheckIssue

An inconsistency detected between OMYM2's last known managed state and the actual filesystem state. Allowed issue types: [contracts/status-reason-catalog.md](contracts/status-reason-catalog.md#checkissue-issue-type).

* A finding may identify a Track, Plan, or CompanionAsset. Companion findings retain nullable `companion_asset_id`; unmanaged companion findings have no managed asset identity.
* Calculated by `check` from DB and filesystem observations, persisted as part of the owning Library's latest CheckRun so Web and CLI browsing read stored findings instead of recomputing.
* Findings about Library-managed files identify the owning Library through `library_id`.

## CheckRun

Persisted record of one Library's latest completed check run. Fields: check_run_id, library_id, checked_at, total_count.

A Library has at most one CheckRun at a time: each new check replaces its prior CheckRun and CheckIssues wholesale. Persistence: [contracts/db-schema.md](contracts/db-schema.md#check_runs).

## Operation

Durable record of one accepted background application request. A shared typed entity: Add, Organize, Refresh, Check, Apply, and Undo use the same lifecycle, persistence, idempotency, and recovery contract. Contains no HTTP, thread, worker-pool, FastAPI, SQLite, or filesystem behavior.

Fields: operation_id, library_id (nullable before a Library exists or can be selected), kind, status, idempotency_key, request_fingerprint, result (nullable typed union), error_code/error_message (nullable, redacted), plan_id/run_id (nullable durable links), requested_at/started_at/completed_at, result_expires_at/tombstone_expires_at.

* `operation_id` is UUIDv7. An idempotency key identifies a client request replay; it is not Operation identity and is never reused as `operation_id`.
* Operation is distinct from Run (one Apply attempt) and FileEvent (the pre-mutation durable record for one Library music file change). Lifecycle and recovery: [contracts/operations.md](contracts/operations.md).

## Domain Invariants

These invariants belong to the domain/usecase layer, not to adapters:

* A Track has a stable `track_id` independent from path, canonical path, content hash, and metadata hash.
* A CompanionAsset has a stable `companion_asset_id` and is not a Track.
* A Library has stable identity independent of its current root path.
* Library-managed records belong to exactly one Library through `library_id`.
* The initial implementation generates Library, Track, CompanionAsset, Plan, action, event, Run, CheckRun, and Operation IDs as UUIDv7.
* A Plan is reviewed and applied through recorded PlanActions.
* A Plan is single-use in the initial version.
* Applying a Plan must not recalculate target paths from the latest AppConfig.
* Artist display-name resolution and projection must not mutate raw TrackMetadata or alter artist-ID lookup keys.
* Track and CompanionAsset current/canonical paths are Library-root-relative.
* Reviewed audio, companion, and unprocessed-file mutations must be represented by FileEvents.
* FileEvents represent file mutations only, not DB-only updates.
* A companion mutation may execute only after every recorded dependency has applied successfully.
* An unprocessed mutation is trackless, metadata-free, dependency-free, and anchored to the retained Add source root.
* Conflict judgment is not performed by DB repositories.
* PathPolicy is pure and does not check filesystem existence.
* Absolute path resolution is performed at I/O boundaries through PathResolver.
* Config loading and saving are adapter concerns.
* Metadata reading is an adapter concern.
* Durable Operations never replace FileEvents or weaken their pending-before-mutation ordering.

## ID Design Policy

The file hash is never Track identity. The initial implementation uses UUIDv7 for all stable internal IDs:

```text
track_id           UUIDv7 when a Track is first recorded as managed state
companion_asset_id UUIDv7 for one managed lyrics or artwork identity
library_id         UUIDv7 when a Library is first recorded
plan_id            UUIDv7 when a Plan is created
run_id             UUIDv7 when an apply attempt starts
action_id          UUIDv7 when a PlanAction is created
event_id           UUIDv7 when a FileEvent is created
check_run_id       UUIDv7 when a check run is persisted
operation_id       UUIDv7 when a background request is accepted
```

* `track_id` must not be derived from file path, canonical path, `content_hash`, or `metadata_hash` — those change during normal add, organize, refresh, undo, and external tag correction.
* `content_hash` is the hash of current file contents (a full-file hash is allowed initially). `metadata_hash` is a change-detection hint over current metadata — never Track identity and never sufficient to decide file movement. `current_path` is the last known root-relative location; `canonical_path` is the root-relative location PathPolicy says the file should occupy.
* Short IDs in CLI output are display aliases only; persisted IDs and internal references use full UUIDv7 values.
