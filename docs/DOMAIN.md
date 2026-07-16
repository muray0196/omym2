---
type: Domain Model
title: Domain
description: Defines OMYM2's core entities, including metadata, companion identity, trackless unprocessed-file evidence, Plan dependencies, durable mutations, snapshots, and UUIDv7 identity policy.
tags: [domain-model, entities, invariants, artist-names, companions, unprocessed, operations, id-design]
timestamp: 2026-07-16T04:51:16+09:00
---

# Domain

This document is authoritative for OMYM2 domain concepts, domain invariants, and ID design policy. Execution semantics are in [execution/](execution/), and persistence/path storage details are in [STORAGE.md](STORAGE.md) and [contracts/path-identity-storage.md](contracts/path-identity-storage.md). Any storage representation mentioned here is a domain-facing summary only.

The central concepts are independent from CLI, Web UI, SQLite, TOML, filesystem APIs, and metadata extraction libraries.

## AppConfig

Application behavior settings used by usecases.

AppConfig is the in-memory representation of user settings. It may be loaded from TOML by a ConfigStore adapter, but domain and usecases do not read TOML directly.

Usecases may receive AppConfig. Pure domain services should receive narrow config objects when possible. For example, PathPolicy should receive PathPolicyConfig instead of the entire AppConfig.

The config schema and defaults are authoritative in [contracts/config.md](contracts/config.md).

Artist IDs are user-facing config/path values inside AppConfig. They are
editable TOML settings and must not be modeled as internal OMYM2 identity in
the way `track_id` and `library_id` are.

Full artist display-name preferences are also user-facing AppConfig values,
but are independent from artist IDs. They replace only the display text used
by artist path placeholders; they do not rewrite compact IDs.

## FileScanEntry

A cheap filesystem discovery result produced while scanning a directory tree.

Representative fields:

* path
* size
* mtime
* file_extension

FileScanEntry is the output of FileScanner or a single-file FileStatReader observation. It represents that a candidate file was found, but it does not contain music metadata, content hash, or metadata hash.

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
* filesystem_identity
* captured_at

FileSnapshot is created by a snapshot-capturing port after filesystem stat, metadata reading, and hash calculation have been performed. FileScanner does not create FileSnapshot.

FileSnapshot is not the identity of a managed track.

A fresh filesystem capture carries an ephemeral token containing device,
inode, size, nanosecond mtime, and nanosecond ctime. Capture accepts the token
only when the same state is observed before and after metadata and hash reads.
Apply requires that token and the captured content hash from its fresh
precondition capture. The FileMover verifies the token before claiming a
target and both the token and bytes before unlinking the source. The token is
not persisted; snapshots reconstructed from trusted Track stat baselines carry
no filesystem token and are never sufficient for Apply.

`size` and `mtime` are optimization hints, not proof of content equality. Default workflows and apply must not rely on them alone. The explicit CLI `--trust-stat` mode may reconstruct a snapshot from the last verified Track state only under the eligibility and risk rules owned by the organize, refresh, and check execution contracts.

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

Raw TrackMetadata is never overwritten by a derived artist display name.
Metadata hashes, Track persistence, album grouping, and artist-ID lookup keep
using the raw tag values even when a preference, accepted provider result, or
new provider result supplies different display text.

## ArtistNameSourceKey

`derive_artist_name_source_key` produces the sole lookup key used for accepted
provider artist names. It treats the complete source artist or album-artist
value as one opaque string and applies these rules in order:

1. Missing input produces no key.
2. Normalize the string to Unicode NFC.
3. Replace each run of Unicode whitespace with one ASCII space and remove
   leading and trailing whitespace.
4. If no text remains, produce no key.

Key derivation preserves case, punctuation, compatibility characters, source
order, and multi-artist separators. It never applies PathPolicy sanitization,
case folding, transliteration, or multi-artist splitting. Consequently,
canonically equivalent spellings and whitespace-only variations share a cache
entry while other textual distinctions remain separate.

Naming usecases derive the key with this function before every accepted-name
cache lookup and insertion. The exact raw metadata string remains available as
the accepted record's `source_name`; deriving a key never changes TrackMetadata.

## ArtistNameProjection

An immutable derived value containing the effective `artist` and
`album_artist` display strings for one raw TrackMetadata value.

The current projection is a pure, exact lookup in the configured full-name
preferences. Missing entries preserve the original strings, and a composite
multi-artist string is treated as one opaque key. It does not load accepted
cache state, run a language model, or contact a provider.

The shared resolver below returns `ArtistNameResolution` values for explicit
consumers. Any consumer that turns those results into an
`ArtistNameProjection` must do so explicitly and pass that projection onward;
defining the resolver does not make PathPolicy or ordinary path projection
perform cache, model, or provider work.

## Artist Name Batch Resolution

The shared artist-name resolver accepts artist and album-artist source values
as one batch and resolves each complete value with this precedence:

```text
exact configured display-name preference
-> accepted provider result by ArtistNameSourceKey
-> newly accepted MusicBrainz result when eligible
-> original source value
```

Preference lookup compares the complete raw source string exactly. It does not
apply ArtistNameSourceKey normalization. An exact preference ends resolution
for that occurrence and does not require a cache read, language-model call, or
provider request.

For remaining values, the resolver derives the whole-string source key and
deduplicates the batch by that key. It performs at most one accepted-cache
lookup and, on an eligible miss, at most one provider lookup for each distinct
key. The resulting display value is reused for every occurrence of that key;
the resolver never splits a source into artist components or changes their
order. Missing and whitespace-only values produce no key and remain unchanged.

The resolver returns one `ArtistNameResolution` for each input in input order.
Each result retains `source_name` and `source_key`, supplies the effective
`resolved_name`, and records provenance as `user_preference`,
`accepted_musicbrainz`, `new_musicbrainz`, or `original`. A result that keeps
the original may also carry a stable issue describing ineligibility,
unavailability, low confidence, no confident match, or ambiguity. Provider
provenance is carried by the associated immutable `AcceptedArtistName`; it does
not modify TrackMetadata.

Only positive provider results are accepted and persisted. Accepted results
are sticky: a later lookup cannot replace the row selected for the same source
key. If another writer wins an insert race, the persisted winner supplies the
resolved value. Misses, ambiguity, ineligibility, model or provider
unavailability, malformed responses, timeouts, and other provider failures are
not negative cache entries and preserve the original source value. These
fallbacks are normal resolution outcomes rather than errors for the caller.

### Plan Review Diagnostics

When an Add, Organize, or Refresh candidate reaches artist-name resolution and
becomes a PlanAction, that action records a review-only diagnostic pair for its
artist and album-artist fields. Each field snapshots the source value, resolved
value, resolution provenance, and nullable resolution issue observed while the
target path was calculated. A missing field remains an explicit resolution
outcome inside the pair.

Candidates blocked before artist-name resolution and Undo actions record no
artist-name diagnostic pair. Plan review reads only this recorded snapshot; it
does not reload preferences, consult the accepted-name cache, run fastText, or
contact MusicBrainz. Apply preserves the snapshot while changing action status
and continues to execute only the recorded paths.

### Automatic lookup eligibility

A cache miss is eligible for a new MusicBrainz lookup only when all of these
conditions hold:

* persisted automatic lookup is enabled
* the complete source contains at least one alphabetic code point and every
  alphabetic code point is non-Latin
* the source does not contain the ASCII comma (`U+002C`); comma-composite
  values remain unresolved by automatic lookup
* fastText returns the exact label `__label__ja` with finite confidence in the
  inclusive range from the persisted `fasttext.minimum_confidence` through
  `1.0`; the default minimum is `0.8`

Preferences and accepted cache entries still apply to comma-composite or
otherwise ineligible values. Persisted opt-out records
`automatic_lookup_disabled`; an absent runtime/model or unusable prediction
records `detector_unavailable`; confidence below the threshold records
`low_language_confidence`. Each disables only the new provider lookup and does
not disable preference or cache resolution.

### Deterministic MusicBrainz acceptance

MusicBrainz search candidates are ranked by numeric score descending. The top
candidate is considered only when its score is at least `95`. The resolver then
finds the highest-scoring runner-up with a different MusicBrainz artist
identity. When that distinct runner-up is within `5` score points of the top
candidate, including a difference of exactly `5`, the result is ambiguous and
is not accepted. Repeated rows for the same artist identity do not create
runner-up ambiguity; they are coalesced by identity, and their alias facts are
treated as one unordered set.

An accepted candidate must carry a valid MusicBrainz artist identity and a
usable Latin display name. Name selection uses these tiers in order:

1. an English-locale Latin alias
2. another Latin alias
3. the Latin canonical artist name

Aliases are an unordered set; provider response order is never a tie-breaker.
Within one tier, duplicate aliases are removed and the lexicographically first
`(name, locale-or-empty)` pair by Unicode code-point order is selected. An
English locale is matched case-insensitively by primary language subtag `en`.
A usable Latin display name is nonblank, contains at least one Latin-script
alphabetic code point, and contains no non-Latin alphabetic code point.
`sort-name` is not a fallback tier.

## PathPolicy

A pure domain service that generates the Library-root-relative canonical path for a track.

Input:

* TrackMetadata
* file_extension
* PathPolicyConfig
* optional already-derived ArtistNameProjection

Output:

* canonical_path

`canonical_path` is a normalized relative path from the Library root. It is not an absolute path.

PathPolicy may normalize metadata values for path generation. Artist and album
artist display values are resolved before rendering and passed explicitly;
PathPolicy does not read AppConfig preferences or provider state. Source file
extensions are normalized to lowercase when appended to generated paths.

PathPolicy is deterministic and does not perform I/O. It does not join paths with the Library root and does not check whether the target path exists. Target existence is handled by usecases through filesystem ports and CollisionPolicy.

Path policy templates render a library-root-relative destination path stem.
Templates must not include file extensions.

OMYM2 derives the destination extension from the source music file suffix
and appends it after rendering the template. The final PlanAction target path
is recorded with the extension included. Apply uses the recorded target path
without recalculating it.

Allowed placeholders, initial template, preview behavior, and config validation rules are authoritative in [contracts/config.md](contracts/config.md#pathpolicyconfig).

When the template includes `{artist_id}`, PathPolicy resolves it from
already-loaded config and raw metadata only. The optional display-name
projection cannot change its source key. Language detection, fastText model
loading, and MusicBrainz HTTP lookup are feature/adapter concerns and must not
run during canonical path generation.

Planning usecases check generated targets through filesystem ports and
CollisionPolicy. If a target is occupied, the usecase records the PlanAction
as blocked with the documented conflict reason; PathPolicy neither performs
that I/O nor solves collisions itself.

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

`root_path` is mutable so a future relink can update a Library's location. When
relink is implemented, it must preserve `library_id` and must not duplicate
Tracks, Plans, PlanActions, FileEvents, or Library-managed history records.

Allowed Library status values are in [contracts/status-reason-catalog.md](contracts/status-reason-catalog.md#library-status). Library registration behavior is defined in [execution/organize.md](execution/organize.md#library-registration-behavior), and storage representation is defined in [contracts/path-identity-storage.md](contracts/path-identity-storage.md).

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
* size (nullable)
* mtime (nullable)
* metadata
* status
* first_seen_at
* last_seen_at
* updated_at

`current_path` and `canonical_path` are normalized paths relative to the Library root. They must not be stored as absolute paths for Library-managed Tracks.

The `track_id` is the stable internal identity of the Track. The initial implementation uses UUIDv7 for `track_id`.

`track_id` is generated when a Track is first recorded as managed state in OMYM2. It must not be derived from file path, canonical path, content hash, or metadata hash. Those values may change during normal operations such as add, organize, refresh, undo, and external tag correction.

Every Track belongs to exactly one Library through `library_id`. Track rows do not define whether the Library is registered.

`size` and `mtime` are the optional filesystem stat baseline associated with a
verified snapshot of the managed file. Existing Tracks may have no baseline.
They are change-detection optimization hints only: neither value is Track
identity, and their presence does not by itself prove content equality. Only an
explicit trust-stat workflow may treat an exact complete match as permission to
reuse the last verified hashes and metadata; apply always captures the source.

Allowed Track status values are in [contracts/status-reason-catalog.md](contracts/status-reason-catalog.md#track-status). `missing` is reported by `check` in the initial version rather than automatically persisted as Track status.

## CompanionAsset

The current managed state of one lyrics or artwork file associated with a
Track. A CompanionAsset is not a Track: it has its own stable
`companion_asset_id`, carries no music metadata, and never changes
`track_id` identity or meaning.

Representative fields:

* companion_asset_id
* library_id
* kind (`lyrics` or `artwork`)
* owner_track_id
* current_path
* canonical_path
* content_hash
* size and mtime (nullable)
* status (`active` or `removed`)
* first_seen_at, last_seen_at, and updated_at

`current_path` and `canonical_path` are normalized Library-root-relative
paths even after an external Add Undo marks the asset removed. Identity is
independent from path, hash, owner action, and Plan history. Organize may
create or refresh an already canonical asset from a verified observation
without a file mutation. A successful relocation preserves the ID and
`first_seen_at`; failed or unknown mutations never advance managed state.

### Companion Association

Companion classification is deterministic over regular, non-symlink source
inventory:

* a case-insensitive `.lrc` suffix is lyrics and associates with the single
  same-directory audio candidate having the same stem;
* a case-insensitive `.jpg` or `.png` suffix is directory artwork and is
  represented once per source file, not once per Track;
* artwork uses the first audio candidate in source-path order as its semantic
  owner and depends on every audio candidate in that source directory;
* artwork has a target only when every associated audio target has the same
  parent, and it preserves its source basename below that parent.

An ambiguous lyrics owner or divergent artwork target parents produce a
reviewable blocked companion action rather than a guessed association.
Planning records the semantic owner separately from every execution dependency.

When companion processing is enabled, Add may turn these claims into new
companion actions. When unprocessed processing alone requests inventory, the
same classification reserves recognized companion paths from leftover
collection but creates no companion action, content snapshot, asset ID, or
dependency. Check performs this classification for unmanaged-companion
discovery only when companion processing is enabled; managed assets and
recorded Plan/event diagnostics are checked regardless of the current toggle.

## Unprocessed Collection Evidence

An unprocessed file is a regular, non-symlink Add source left unclaimed after
audio and companion classification. Unprocessed-only Add inventory still uses
classification-only companion claims, so a recognized `.lrc`, `.jpg`, or
`.png` path is not a leftover even when new companion actions are disabled.
Collection does not create a third kind of managed Library entity: the file is
neither a Track nor a CompanionAsset and has no stable entity ID, owner,
metadata, or Library-relative managed path.

Its durable identity is the reviewed `PlanAction.action_id` followed by the
attempted `FileEvent.event_id`. A forward `move_unprocessed` action records:

* `track_id`, `companion_asset_id`, and `owner_action_id` as null;
* no dependencies or artist-name diagnostics;
* an absolute source and absolute target anchored below the Plan's retained
  `source_root_at_plan`;
* a target shaped exactly as
  `<source-root>/<portable-directory>/<source-relative-path>`;
* `content_hash_at_plan` from a rooted content-only snapshot and a null
  `metadata_hash_at_plan`.

The inverse action keeps the same trackless, content-only shape and swaps the
recorded paths only after exact succeeded-event provenance is proven. Current
Config does not relabel either path.

## Plan

A scheduled set of actions before execution.

A Plan describes what OMYM2 intends to do, but no Library-managed file
mutation has occurred yet. Plan creation is the boundary between calculation
and execution.

Representative fields:

* plan_id
* library_id
* plan_type
* status
* created_at
* config_hash
* library_root_at_plan
* source_root_at_plan (nullable)
* source_run_id (nullable; set only for undo Plans)
* summary
* actions

Plan types:

* add
* organize
* refresh
* undo

Allowed Plan status values are in [contracts/status-reason-catalog.md](contracts/status-reason-catalog.md#plan-status).

Execution summary: a Plan stores reviewed action data, including
`library_root_at_plan`, for later apply. An Add Plan also retains
`source_root_at_plan` so absolute external audio, companion, and unprocessed
sources and targets remain anchored to the exact reviewed source root. An Undo
Plan copies that root from the source Plan when reversing an external import;
Organize and Refresh leave it null. The authoritative apply contract is in
[execution/apply.md](execution/apply.md), including stale-root handling in
[Apply-Time Precondition Failures](execution/apply.md#apply-time-precondition-failures).

A Plan is single-use in the initial version.

An undo Plan records the terminal Run it reverses in `source_run_id`. This is
provenance and deduplication state, not a path or display-only link. Non-undo
Plans have no source Run.

## PlanAction

A planned action for one file or one managed Track inside a Plan.

PlanAction separates the kind of intended operation from its current status and from the reason why it may be blocked.

Representative fields:

* action_id
* plan_id
* library_id
* track_id (nullable)
* action_type
* source_path
* target_path
* reverses_event_id (nullable; set only for Undo actions)
* companion_asset_id (nullable)
* owner_action_id (nullable)
* content_hash_at_plan
* metadata_hash_at_plan
* status
* reason
* sort_order

Path representation summary: managed Library destinations are stored as
normalized paths relative to the owning Library root. External Add sources are
absolute. A reviewed unprocessed action stores both paths as absolute values
below the retained source root; an Undo of an external import also has an
absolute target. The authoritative storage policy is in
[contracts/path-identity-storage.md](contracts/path-identity-storage.md).

File operations must resolve path references through PathResolver.

Allowed action types, statuses, and reasons are in [contracts/status-reason-catalog.md](contracts/status-reason-catalog.md#planaction-action-type).

Execution summary: `apply` handles blocked and eligible PlanActions according to [execution/apply.md](execution/apply.md#apply-behavior).

Issues detected during plan creation are represented as `blocked`. Precondition failures detected during apply are represented as `failed`.

`conflict` and `error` are not action types. They are represented as status and reason.

`track_id` may be nullable for PlanActions that target files not yet registered
as Tracks, such as new files in an Add Plan. It is necessarily null for an
unprocessed-file action because collection creates no Track.

Lyrics and artwork actions preallocate or reuse `companion_asset_id`; Plan
creation does not create managed companion state before a reviewed mutation
succeeds. The semantic owner is the existing `track_id`, an optional same-Plan
audio `owner_action_id`, or both when the Track already exists. Apply resolves
the final owner Track from this evidence. The separate durable PlanAction
dependency relation records every action that must be applied first.
Dependencies are same-Plan, cannot point to the action itself, and are not
inferred from sort order or ownership. Shared artwork can therefore have one
semantic owner while depending on every associated audio action.

Each Undo PlanAction records the succeeded source FileEvent it reverses in
`reverses_event_id`. Non-Undo actions leave it null. This durable provenance
lets later Undo generation distinguish an event already reversed by a prior
partial attempt from one still eligible; path/Track matching alone is not
identity.

## Run

An execution attempt for applying a Plan.

Execution summary: Run creation and status transitions follow [execution/model.md](execution/model.md#run-behavior) and [execution/apply.md](execution/apply.md#run-status).

Representative fields:

* run_id
* plan_id
* library_id
* status
* started_at
* completed_at
* error_summary

Allowed Run status values are in [contracts/status-reason-catalog.md](contracts/status-reason-catalog.md#run-status).

A Run is not merely a historical label. It is the parent unit for FileEvents and the main unit used by history and undo.

## FileEvent

A durable mutation-log entry for one reviewed audio, companion, or
unprocessed-file mutation.

Execution summary: FileEvent creation and result updates follow [execution/model.md](execution/model.md#fileevent-behavior) and [execution/apply.md](execution/apply.md#fileevent-status).

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
* companion_asset_id (nullable)

Allowed FileEvent types, statuses, and error-code policy are in [contracts/status-reason-catalog.md](contracts/status-reason-catalog.md#fileevent-event-type).

Companion events retain `companion_asset_id` and use their closed lyrics or
artwork event type. DB-only state changes such as registering an already
canonical Track or CompanionAsset are not FileEvents.

An unprocessed event uses `move_unprocessed_file`, retains absolute paths below
the source Plan's root, and has no Track or CompanionAsset identity. Its
succeeded state is durable evidence for Check and Undo, not managed Library
state.

FileEvents are used for:

* run detail display
* diagnosing partial failures
* crash inspection
* undo plan creation

## CheckIssue

An inconsistency detected between OMYM2's last known managed state and the actual filesystem state.

Allowed issue types are in [contracts/status-reason-catalog.md](contracts/status-reason-catalog.md#checkissue-issue-type).

A finding may identify a Track, Plan, or CompanionAsset. Companion findings
retain nullable `companion_asset_id`; unmanaged companion findings have no
managed asset identity.

CheckIssue is calculated by `check` from DB and filesystem observations, then persisted as part of the owning Library's latest CheckRun (below) so Web and CLI browsing read stored findings instead of recomputing them on every request.

Reported CheckIssues that refer to Library-managed files identify the owning Library through `library_id`.

## CheckRun

The persisted record of one Library's latest completed check run.

Representative fields:

* check_run_id
* library_id
* checked_at
* total_count

A Library has at most one CheckRun at a time: each new check run for a Library replaces its prior CheckRun and prior CheckIssues wholesale. CheckRun and CheckIssue persistence is authoritative in [contracts/db-schema.md](contracts/db-schema.md#check_runs).

## Operation

A durable record of one accepted background application request.

Operation is a shared typed entity because Add, Organize, Refresh, Check, Apply,
and Undo use the same lifecycle, persistence, idempotency, and recovery
contract. It contains no HTTP, thread, worker-pool, FastAPI, SQLite, or
filesystem behavior.

Representative fields:

* operation_id
* library_id (nullable before a Library exists or can be selected)
* kind
* status
* idempotency_key
* request_fingerprint
* stage_code (nullable)
* completed_units / total_units (nullable pair)
* progress_message (nullable and redacted)
* result (nullable typed union)
* error_code / error_message (nullable and redacted)
* plan_id / run_id (nullable durable links)
* requested_at / started_at / completed_at
* result_expires_at / tombstone_expires_at

Operation identity is stable by `operation_id`, generated as UUIDv7. An
idempotency key identifies a client request replay; it is not Operation
identity and is never reused as `operation_id`.

Operation is distinct from Run and FileEvent. A Run remains one Apply attempt,
and a FileEvent remains the pre-mutation durable record for one Library music
file change. Operation lifecycle and recovery are authoritative in
[contracts/operations.md](contracts/operations.md).

## Domain Invariants

The following invariants belong to the domain / usecase layer, not to adapters:

* A Track has a stable `track_id` independent from path, canonical path, content hash, and metadata hash.
* A CompanionAsset has a stable `companion_asset_id` and is not a Track.
* A Library has stable identity independent of its current root path.
* Library-managed records belong to exactly one Library through `library_id`.
* The initial implementation generates Library, Track, CompanionAsset, Plan,
  action, event, Run, CheckRun, and Operation IDs as UUIDv7.
* A Plan is reviewed and applied through recorded PlanActions.
* A Plan is single-use in the initial version.
* Applying a Plan must not recalculate target paths from the latest AppConfig.
* Artist display-name resolution and projection must not mutate raw
  TrackMetadata or alter artist-ID lookup keys.
* Track and CompanionAsset current/canonical paths are Library-root-relative.
* Reviewed audio, companion, and unprocessed-file mutations must be represented
  by FileEvents.
* FileEvents represent file mutations only, not DB-only updates.
* A companion mutation may execute only after every recorded dependency has
  applied successfully.
* An unprocessed mutation is trackless, metadata-free, dependency-free, and
  anchored to the retained Add source root.
* Conflict judgment is not performed by DB repositories.
* PathPolicy is pure and does not check filesystem existence.
* Absolute path resolution is performed at I/O boundaries through PathResolver.
* Config loading and saving are adapter concerns.
* Metadata reading is an adapter concern.
* Durable Operations never replace FileEvents or weaken their
  pending-before-mutation ordering.

## ID Design Policy

The file hash is not treated as the Track identity.

The initial implementation uses UUIDv7 for stable internal IDs.

```text
track_id        UUIDv7 generated when a Track is first recorded as managed state
companion_asset_id UUIDv7 allocated for one managed lyrics or artwork identity
library_id      UUIDv7 generated when a Library is first recorded
plan_id         UUIDv7 generated when a Plan is created
run_id          UUIDv7 generated when an apply attempt starts
action_id       UUIDv7 generated when a PlanAction is created
event_id        UUIDv7 generated when a FileEvent is created
check_run_id    UUIDv7 generated when a check run is persisted
operation_id    UUIDv7 generated when a background request is accepted
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
companion_asset_id stable internal ID for one managed companion asset
library_id      stable internal ID for the owning Library
content_hash    hash of the current file contents
metadata_hash   hash of the current metadata
current_path    last known Library-root-relative location
canonical_path  Library-root-relative location where the file should exist according to PathPolicy
```

The initial version may use a full-file hash for `content_hash`.

`metadata_hash` is used as a change detection hint. It must not be used as Track identity and must not decide file movement by itself.

Short IDs may be shown in CLI output for readability, but they are display aliases only. Persisted IDs and internal references use full UUIDv7 values.
