---
type: Codebase Reference
title: Ports And UnitOfWork
description: Defines OMYM2's ports and UnitOfWork contract, including editable artist-name mappings, provider cadence transactions, durable Operations, Config revision CAS, atomic Apply claims, cross-platform retained-object mutation preconditions, and FileEvent ordering.
tags: [ports, unit-of-work, transactions, architecture, artist-names, musicbrainz]
timestamp: 2026-07-17T22:43:57+09:00
---

# Ports And UnitOfWork

This document is authoritative for OMYM2 port shapes and usage, UnitOfWork
policy, Clock/IdGenerator ports, exclusive-operation coordination interfaces,
atomic-claim persistence interface, transaction boundaries, and the distinct
durability roles of Operation and FileEvent. Config CAS semantics are owned by
[the Config contract](../contracts/config.md#raw-storage-revision-and-atomic-save);
this document owns only its port shape.

Detailed execution order is in [../execution/apply.md](../execution/apply.md), and DB consistency details are in [../STORAGE.md](../STORAGE.md).

## Ports

External I/O is expressed as ports.

Representative examples:

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

`check_runs` and `check_issues` persist each Library's latest completed check
diagnostics. Their replacement and browsing rules are authoritative in
[../contracts/db-schema.md](../contracts/db-schema.md#check_runs).

```python
class AcceptedArtistNameRepository(Protocol):
    def find_by_source_key(self, source_key: str) -> AcceptedArtistName | None: ...
    def insert_if_absent(self, accepted_name: AcceptedArtistName) -> bool: ...
    def list_all(self) -> tuple[AcceptedArtistName, ...]: ...
    def save(self, accepted_name: AcceptedArtistName) -> None: ...
    def delete_by_source_key(self, source_key: str) -> None: ...
```

The repository treats its already-derived source key as an exact opaque lookup
value. Automatic lookup uses `insert_if_absent`; revision-checked Settings
editing uses deterministic listing, upsert, and deletion. Provider matching,
normalization, and edit validation are feature rules, not repository behavior.

```python
class ArtistNameResolutionReader(Protocol):
    def resolve_many(
        self,
        source_names: Sequence[str | None],
    ) -> tuple[ArtistNameResolution, ...]: ...
```

`ArtistNameResolutionReader` is the consumer-facing shared batch boundary. It
returns one result for each input in input order, including repeated inputs.
It reads the saved mapping before provider work, while whole-string source-key
deduplication keeps mapping and provider calls bounded.
The resolution and acceptance rules are authoritative in
[Artist Name Batch Resolution](../DOMAIN.md#artist-name-batch-resolution).

`add`, `organize`, and `refresh` all consume this same port. Normal Plan
composition shares one lazy language predictor and one
provider for the process. Persisted `musicbrainz` settings select provider
bounds; the model is an application-owned package resource. Saved mappings
remain available while automatic lookup is disabled.
Latin-only cache misses become romanization-not-required observations and
cannot trigger a provider request; explicit disablement is a distinct
automatic-lookup-disabled observation. Enabling the provider changes only new
eligible cache-miss resolution, not the Plan usecase contract.

Add and partial Refresh reject an executable resolved-name move when other
active Tracks would remain at an obsolete canonical artist path. Organize owns
that whole-Library reconciliation.

The `artist_names` feature owns a narrower outbound port:

```python
class ArtistNameProvider(Protocol):
    def search_artists(self, source_name: str) -> ArtistNameSearchResult: ...
```

`ArtistNameSearchResult` carries scored provider candidates, their MusicBrainz
identities, canonical names, and alias facts. The ports report typed external
facts; they do not decide ambiguity, display-name tiering,
stickiness, or fallback. Those decisions stay in the feature resolver.

```python
class FileScanner(Protocol):
    def scan(self, root: PathLike) -> list[FileScanEntry]: ...

class FileStatReader(Protocol):
    def observe(self, path: PathLike) -> FileScanEntry: ...
```

`FileScanner` discovers a whole tree; `FileStatReader` observes one regular file. Both return cheap size, modification-time, path, and extension facts without metadata or hashes. The filesystem scanner adapter implements both contracts. Organize and check reuse tree-scan observations for their explicit trust-stat decisions, while refresh uses the single-file port for selected Tracks.

```python
class FileSnapshotReader(Protocol):
    def capture(self, path: PathLike) -> FileSnapshot: ...

@dataclass(frozen=True)
class FileSnapshotCaptureRequest:
    path: PathLike

class BatchFileSnapshotReader(Protocol):
    def capture_many(
        self,
        requests: Sequence[FileSnapshotCaptureRequest],
    ) -> Sequence[FileSnapshot | None]: ...
```

`BatchFileSnapshotReader` is the bounded, input-order-preserving read path used by add, organize, refresh, and check. A `None` result represents `FileNotFoundError` for the corresponding request. Apply, undo, and inspect keep using single-file `FileSnapshotReader.capture()`; in particular, apply never batches the source precondition that immediately precedes a move.

Every complete capture performs its own fresh stat. Trust eligibility and trusted-snapshot reconstruction are domain/usecase decisions above the filesystem adapter; filesystem adapters only return observations and complete snapshots.

```python
class MetadataReader(Protocol):
    def read(self, path: PathLike) -> TrackMetadata: ...
```

```python
class FileMover(Protocol):
    def move(
        self,
        source: PathLike,
        target: PathLike,
        *,
        source_root: PathLike | None = None,
        target_root: PathLike | None = None,
        expected_source_identity: FilesystemIdentity | None = None,
        expected_source_content_hash: str | None = None,
    ) -> None: ...
```

Every live `FileSnapshotReader.capture()` result carries an ephemeral
`FilesystemIdentity` containing device, inode, size, modification time, and
change time. Apply passes that exact token and the captured content hash as
`expected_source_identity` and `expected_source_content_hash`; a trusted
snapshot reconstructed without live I/O has no token and cannot authorize a
filesystem mutation.

Apply independently supplies the verified open Library root as `source_root`
and `target_root` whenever the corresponding path is Library-relative. The
adapter traverses descendants without following link-like entries, retains the
opened root, parent, source, and claimed-target objects, rechecks source
identity and containment, creates the target exclusively, and deletes only the
exact revalidated source object. Copy claims also verify the target and
retained source bytes against the expected content hash before deletion.
External Add sources use `source_root=None` but are still copied from a retained
source object; absolute Undo restore targets use `target_root=None` only for
the separately verified external-restore exception. Omitting one root must not
weaken the other anchored boundary. POSIX realizes this port with `dir_fd` and
`O_NOFOLLOW`; native Windows uses retained `CreateFileW` handles. The exact
platform mechanics are authoritative in the
[Path Identity And Storage Contract](../contracts/path-identity-storage.md#retained-observation-and-mutation-boundary).

```python
class ConfigStore(Protocol):
    def load_with_revision(self) -> ConfigReadResult: ...
    def save_if_revision(
        self,
        config: AppConfig,
        expected_revision: ConfigRevision,
    ) -> ConfigRevision: ...
```

`ConfigReadResult` carries an opaque raw-storage `ConfigRevision`, the parsed
`AppConfig` when parsing and validation succeed, and typed validation state
when they do not. It never exposes raw TOML to a usecase. The revision must
distinguish a missing file, invalid raw TOML, valid config, and an external
rewrite even when the resulting config values are identical.

`save_if_revision` rechecks the raw-storage revision and rejects a mismatch as
a typed Config conflict. A successful save uses an atomic file replacement and
returns the new revision. Web and CLI saves use this same method while holding
the shared exclusive-operation lock; neither path may implement a
last-write-wins save or parse and write TOML in a usecase. Concrete TOML
parsing, serialization, revision derivation, and atomic replacement remain
config-adapter responsibilities.

```python
class ExclusiveOperationLock(Protocol):
    def hold(
        self,
        request: ExclusiveOperationRequest,
    ) -> AbstractContextManager[ExclusiveOperationLease]: ...
```

`ExclusiveOperationLock` is the common Web/CLI cross-process boundary. The
coordinator that enters its context retains the lease across the complete
state-changing operation, including all work performed by a background worker.
It is not scoped only to request acceptance, one DB transaction, or worker
dispatch. Read-only snapshot requests do not acquire it. Concrete crash-safe
lock mechanics belong to the outbound adapter; operation eligibility and the
409 conflict decision remain usecase/orchestration rules.

```python
class Clock(Protocol):
    def now(self) -> datetime: ...
```

```python
class IdGenerator(Protocol):
    def new_library_id(self) -> LibraryId: ...
    def new_check_run_id(self) -> CheckRunId: ...
    def new_track_id(self) -> TrackId: ...
    def new_plan_id(self) -> PlanId: ...
    def new_action_id(self) -> ActionId: ...
    def new_run_id(self) -> RunId: ...
    def new_event_id(self) -> EventId: ...
    def new_operation_id(self) -> OperationId: ...
```

`Clock` and `IdGenerator` are ports. This makes it possible to fix time and IDs during tests.

In the initial implementation, IdGenerator returns UUIDv7-backed IDs. Domain
and usecases depend on typed IDs such as LibraryId, CheckRunId, TrackId, PlanId,
ActionId, RunId, EventId, and OperationId, not on a concrete UUID library.

## Operation And FileEvent Responsibilities

Operation is the shared durable control-plane model for an accepted background
request. It records identity, kind, status, idempotency, typed result,
and interruption state. An Operation may complete without creating a Run or a
FileEvent, for example when Check finishes or Organize registers a clean
Library without a Plan.

FileEvent is the durable mutation-evidence model for one attempted Library
music file mutation inside a Run. It is persisted as `pending` before that
mutation and then updated only when the outcome is known. An Operation never
replaces, embeds, or weakens this FileEvent ordering. A crashed worker may leave
its Operation `interrupted` while a FileEvent remains `pending` for manual
review.

Operation is shared because Add, Organize, Refresh, Check, and Apply use the
same durable acceptance and lifecycle substrate. FileEvent remains specific to
actual Library music file mutations. Repositories persist both models but do
not infer operation availability, Plan capability, mutation outcome, or repair
policy.

## UnitOfWork Policy

The baseline policy is `1 usecase = 1 UnitOfWork` object.

A usecase coordinates domain behavior and persistence through ports. Concrete repositories and transactions stay behind the UnitOfWork adapter.

`UnitOfWork.usecase_scope()` defines the outer lifetime of adapter resources that may be reused by multiple transaction scopes in one usecase. Apply uses it to retain one same-thread SQLite connection. The outer resource scope is not a transaction and must not merge, move, or remove any inner `with uow` transaction boundary. Other usecases may continue using one ordinary transaction scope without an outer resource scope.

## Transaction Boundary

Usecases define the business transition. The UnitOfWork adapter defines the concrete DB transaction mechanics.

Every `with uow` block starts and completes an independent transaction, even inside `usecase_scope()`. No transaction stays open across hashing, provider HTTP calls, or a Library music file mutation. Plan creators therefore close their Library/Track read transaction before snapshot and artist-name resolution work, then use a later transaction for the resulting Plan, PlanActions, and terminal Operation state. Apply's committed PENDING FileEvent remains visible and durable before the mover runs; connection reuse changes checkpoint timing, not commit ordering or durability. The SQLite-specific FULL/WAL rationale is authoritative in [../STORAGE.md](../STORAGE.md#db-consistency).

Repositories persist and restore domain models. They must not decide conflicts, duplicates, canonical paths, metadata validity, PlanAction status, or retry policy.

## Artist Name Mapping Coordination

One batch resolution uses these transaction boundaries:

1. Derive the distinct source keys without opening a DB transaction.
2. Open one short mapping-read transaction, load saved rows for those keys,
   and close the transaction.
3. Run MusicBrainz work only for eligible non-Latin misses,
   with no DB transaction open.
4. If positive results were accepted, open one short final transaction and call
   `insert_if_absent` for their source keys. When insertion loses a race, read
   the persisted row in that same transaction and use that sticky winner.
   Commit before returning the corresponding resolutions.

No final automatic write transaction is needed for ineligible values, misses,
ambiguity, or provider failures. A consumer may keep an outer nontransactional
resource scope if its concrete UnitOfWork supports one, but that scope must not
merge the cache-read and final-persistence transactions or span the external
work as an open SQLite transaction. A Settings mapping save compares its
revision and applies user additions, edits, and deletions in one separate short
transaction. The storage-level summary is in
[Artist-Name Mapping Transactions](../STORAGE.md#artist-name-mapping-transactions).

## Atomic Apply Claim

`UnitOfWork.claim_plan_for_apply` is the single persistence capability for
accepting Apply. It is called only while the shared exclusive-operation lease
is held and after the usecase has verified the current Library root against
`library_root_at_plan`.

Within one transaction, the capability must:

1. look up and classify the idempotency key: return the exact retained
   Operation for a matching kind/fingerprint, return a typed reuse conflict for
   a mismatch, or continue only when the key is new
2. compare-and-set the Plan from `ready` to `applying`
3. insert the associated Run as `running`
4. insert the associated Operation as `queued`
5. persist the Plan, Run, and Operation associations needed to recover or find
   the active operation

An existing key never reaches Plan compare-and-set. If the Plan compare-and-set
fails, the transaction inserts neither the Run nor the Operation and returns a
typed claim conflict. The usecase decides whether
Apply is permitted; the adapter supplies the atomic conditional write and does
not infer capability from status for presentation.

The claim transaction commits before any background Apply work is dispatched.
No hashing, snapshot capture, FileMover call, or other
filesystem I/O occurs inside that transaction. The exclusive lease remains
held after the commit and across the background worker's full execution.

## Durable Mutation Transaction Exception

`apply` and `undo` are practical exceptions to the simple `1 usecase = 1 UnitOfWork` shape because Library music file operations and DB transactions cannot be made fully atomic.

After the atomic Apply claim, each Library music file mutation retains the
existing independent transaction ordering:

1. verify the action preconditions outside a transaction
2. insert and commit the FileEvent as `pending`
3. execute the Library music file mutation outside a transaction
4. update FileEvent, Track, and PlanAction state in a later transaction when the
   outcome is known

No transaction remains open across hashing or a Library music file mutation.
The initial Plan/Run/Operation claim does not merge or remove any of these
per-action transaction boundaries.

Architecture preserves these boundaries:

* Usecases coordinate the operation.
* Adapters perform I/O through ports.
* FileEvents record Library music file mutations before they are executed.
* Operations record background-request lifecycle and never substitute for FileEvents.
* Platform or inbound orchestration chains features; adding Operation support does not permit direct feature-to-feature imports.
* The lock, Config, and persistence adapters implement mechanics but do not decide business capabilities, conflicts, or recovery outcomes.
