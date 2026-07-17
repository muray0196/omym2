---
type: Codebase Reference
title: Ports And UnitOfWork
description: Port catalog and constraints, UnitOfWork policy, transaction boundaries, atomic Apply claim, and mutation ordering.
tags: [ports, unit-of-work, transactions, architecture, artist-names, musicbrainz]
timestamp: 2026-07-18T12:00:00+09:00
---

# Ports And UnitOfWork

Authoritative for port shapes and usage, UnitOfWork policy, Clock/IdGenerator ports, exclusive-operation coordination interfaces, atomic-claim persistence interface, transaction boundaries, and the distinct durability roles of Operation and FileEvent. Config CAS semantics are owned by [the Config contract](../contracts/config.md#raw-storage-revision-and-atomic-save); this document owns only its port shape. Execution order: [../execution/apply.md](../execution/apply.md); DB consistency: [../STORAGE.md](../STORAGE.md).

## Ports

External I/O is expressed as ports. The central persistence port:

```python
class UnitOfWork(Protocol):
    accepted_artist_names: AcceptedArtistNameRepository
    libraries: LibraryRepository
    check_runs: CheckRunRepository
    check_issues: CheckIssueRepository
    tracks: TrackRepository
    plans: PlanRepository
    plan_actions: PlanActionRepository
    runs: RunRepository
    file_events: FileEventRepository
    operations: OperationRepository

    def usecase_scope(self) -> AbstractContextManager[None]: ...
    def claim_plan_for_apply(self, claim: ApplyClaim) -> ApplyClaimResult: ...
    def __enter__(self) -> "UnitOfWork": ...
    def __exit__(self, exc_type, exc, tb) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
```

`check_runs`/`check_issues` persist each Library's latest completed check diagnostics; replacement and browsing rules: [../contracts/db-schema.md](../contracts/db-schema.md#check_runs).

The other ports, each with its binding constraint:

* `AcceptedArtistNameRepository` — `find_by_source_key`, `insert_if_absent`, `list_all`, `save`, `delete_by_source_key`. Treats the already-derived source key as an exact opaque lookup value. Automatic lookup uses `insert_if_absent`; revision-checked Settings editing uses deterministic listing, upsert, deletion. Provider matching, normalization, and edit validation are feature rules, not repository behavior.
* `ArtistNameResolutionReader` — `resolve_many(source_names)` is the consumer-facing shared batch boundary: one result per input in input order (including repeats); reads the saved mapping before provider work; whole-string source-key deduplication bounds mapping and provider calls. Resolution/acceptance rules: [Artist Name Batch Resolution](../DOMAIN.md#artist-name-batch-resolution). `add`, `organize`, and `refresh` all consume this port; normal Plan composition shares one lazy language predictor and one provider per process; persisted `musicbrainz` settings select provider bounds. Saved mappings stay available while automatic lookup is disabled; Latin-only cache misses become romanization-not-required observations (never provider requests); explicit disablement is a distinct automatic-lookup-disabled observation. Add and partial Refresh reject an executable resolved-name move when other active Tracks would remain at an obsolete canonical artist path; Organize owns whole-Library reconciliation.
* `ArtistNameProvider` (owned by the `artist_names` feature) — `search_artists(source_name)` returns scored provider candidates with MusicBrainz identities, canonical names, and alias facts. Ports report typed external facts; ambiguity, display-name tiering, stickiness, and fallback stay in the feature resolver.
* `FileScanner` / `FileStatReader` — `scan(root)` discovers a whole tree; `observe(path)` observes one regular file. Both return cheap size/mtime/path/extension facts without metadata or hashes; one filesystem adapter implements both. Organize and check reuse tree-scan observations for trust-stat decisions; refresh uses the single-file port.
* `FileSnapshotReader` / `BatchFileSnapshotReader` — `capture(path)` and bounded, input-order-preserving `capture_many(requests)` (a `None` result represents `FileNotFoundError`). Add, organize, refresh, and check use the batch path; apply, undo, and inspect use single-file capture — apply never batches the source precondition that immediately precedes a move. Every complete capture performs its own fresh stat; trust eligibility and trusted-snapshot reconstruction are domain/usecase decisions above the adapter.
* `MetadataReader` — `read(path) -> TrackMetadata`.
* `FileMover` — `move(source, target, *, source_root, target_root, expected_source_identity, expected_source_content_hash)`. Every live capture carries an ephemeral `FilesystemIdentity` (device, inode, size, mtime, ctime); Apply passes that exact token plus the captured content hash — a trusted snapshot reconstructed without live I/O has no token and cannot authorize a mutation. Apply supplies the verified open Library root as `source_root`/`target_root` for Library-relative paths; the adapter traverses without following link-like entries, retains root/parent/source/claimed-target objects, rechecks identity and containment, creates the target exclusively, and deletes only the exact revalidated source. Copy claims verify target and retained source bytes against the expected hash before deletion. External Add sources use `source_root=None` but still copy from a retained source object; absolute Undo restore targets use `target_root=None` only for the verified external-restore exception; omitting one root never weakens the other boundary. Platform mechanics: [Path Identity And Storage Contract](../contracts/path-identity-storage.md#retained-observation-and-mutation-boundary).
* `ConfigStore` — `load_with_revision()` returns `ConfigReadResult` (opaque raw-storage `ConfigRevision`, parsed `AppConfig` on success, typed validation state on failure; never raw TOML). The revision distinguishes missing file, invalid raw TOML, valid config, and an external rewrite with identical values. `save_if_revision(config, expected_revision)` rechecks the revision, rejects mismatch as a typed conflict, saves via atomic replacement, and returns the new revision. Web and CLI both use it under the shared exclusive lock; no last-write-wins saves, no TOML parsing/writing in usecases.
* `ExclusiveOperationLock` — `hold(request) -> AbstractContextManager[ExclusiveOperationLease]`. The coordinator retains the lease across the complete state-changing operation, including background-worker work — not just acceptance, one transaction, or dispatch. Read-only snapshot requests do not acquire it. Crash-safe mechanics belong to the adapter; eligibility and the 409 decision stay usecase/orchestration rules.
* `Clock` — `now()`. `IdGenerator` — `new_library_id`, `new_check_run_id`, `new_track_id`, `new_plan_id`, `new_action_id`, `new_run_id`, `new_event_id`, `new_operation_id`. Both are ports so tests can fix time and IDs. IdGenerator returns UUIDv7-backed typed IDs; domain and usecases depend on the typed IDs, not a concrete UUID library.

## Operation And FileEvent Responsibilities

Operation is the shared durable control-plane model for an accepted background request: identity, kind, status, idempotency, typed result, interruption state. It may complete without a Run or FileEvent (Check completion; clean Organize registration). FileEvent is the durable mutation-evidence model for one attempted Library music file mutation inside a Run: persisted `pending` before the mutation, updated only when the outcome is known. An Operation never replaces, embeds, or weakens FileEvent ordering; a crashed worker may leave its Operation `interrupted` while a FileEvent stays `pending` for manual review. Repositories persist both models but never infer operation availability, Plan capability, mutation outcome, or repair policy.

## UnitOfWork Policy

Baseline: `1 usecase = 1 UnitOfWork` object. Usecases coordinate domain behavior and persistence through ports; concrete repositories and transactions stay behind the UnitOfWork adapter.

`usecase_scope()` defines the outer lifetime of adapter resources reused by multiple transaction scopes in one usecase — Apply uses it to retain one same-thread SQLite connection. The outer scope is not a transaction and must not merge, move, or remove any inner `with uow` transaction boundary; other usecases may use one ordinary transaction scope without it.

## Transaction Boundary

Usecases define the business transition; the UnitOfWork adapter defines concrete DB transaction mechanics. Every `with uow` block starts and completes an independent transaction, even inside `usecase_scope()`. No transaction stays open across hashing, provider HTTP calls, or a Library music file mutation. Plan creators close their Library/Track read transaction before snapshot and artist-name resolution work, then use a later transaction for the Plan, PlanActions, and terminal Operation state. Apply's committed PENDING FileEvent remains visible and durable before the mover runs; connection reuse changes checkpoint timing, not commit ordering or durability (SQLite FULL/WAL rationale: [../STORAGE.md](../STORAGE.md#db-consistency)). Repositories persist and restore domain models; they never decide conflicts, duplicates, canonical paths, metadata validity, PlanAction status, or retry policy.

## Artist Name Mapping Coordination

One batch resolution uses these transaction boundaries:

1. Derive the distinct source keys without opening a DB transaction.
2. Open one short mapping-read transaction, load saved rows for those keys, close it.
3. Run MusicBrainz work only for eligible non-Latin misses, with no DB transaction open.
4. If positive results were accepted, open one short final transaction and call `insert_if_absent`; when insertion loses a race, read the persisted row in that same transaction and use the sticky winner. Commit before returning the resolutions.

No final automatic write transaction for ineligible values, misses, ambiguity, or provider failures. A consumer may keep an outer nontransactional resource scope, but it must not merge the cache-read and final-persistence transactions or span external work as an open SQLite transaction. A Settings mapping save compares its revision and applies user additions, edits, and deletions in one separate short transaction. Storage-level summary: [Artist-Name Mapping Transactions](../STORAGE.md#artist-name-mapping-transactions).

## Atomic Apply Claim

`UnitOfWork.claim_plan_for_apply` is the single persistence capability for accepting Apply, called only while the shared exclusive lease is held and after the usecase verified the current Library root against `library_root_at_plan`. Within one transaction it must:

1. classify the idempotency key: return the exact retained Operation for a matching kind/fingerprint, return a typed reuse conflict for a mismatch, continue only when new
2. compare-and-set the Plan `ready` → `applying`
3. insert the associated Run as `running`
4. insert the associated Operation as `queued`
5. persist the Plan/Run/Operation associations needed to recover or find the active operation

An existing key never reaches Plan compare-and-set. If the compare-and-set fails, neither Run nor Operation is inserted and a typed claim conflict returns. The usecase decides whether Apply is permitted; the adapter supplies the atomic conditional write and does not infer capability from status. The claim transaction commits before any background Apply work is dispatched; no hashing, snapshot capture, FileMover call, or other filesystem I/O occurs inside it. The exclusive lease stays held after commit and across the worker's full execution.

## Durable Mutation Transaction Exception

`apply` and `undo` are practical exceptions to `1 usecase = 1 UnitOfWork` because Library music file operations and DB transactions cannot be made fully atomic. After the atomic Apply claim, each mutation keeps independent transaction ordering:

1. verify action preconditions outside a transaction
2. insert and commit the FileEvent as `pending`
3. execute the Library music file mutation outside a transaction
4. update FileEvent, Track, and PlanAction state in a later transaction when the outcome is known

No transaction stays open across hashing or a mutation; the initial Plan/Run/Operation claim does not merge or remove per-action boundaries. Architecture preserves: usecases coordinate; adapters perform I/O through ports; FileEvents record mutations before execution; Operations record lifecycle and never substitute for FileEvents; platform/inbound orchestration chains features (Operation support does not permit direct feature-to-feature imports); lock/Config/persistence adapters implement mechanics without deciding business capabilities, conflicts, or recovery outcomes.
