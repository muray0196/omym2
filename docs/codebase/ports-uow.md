---
type: Codebase Reference
title: Ports And UnitOfWork
description: Defines OMYM2's port and UnitOfWork repository inventory, scan/stat/snapshot ports, ordered batch capture, independent transactions, durable FileEvents, and persisted check diagnostics.
tags: [ports, unit-of-work, transactions, architecture]
timestamp: 2026-07-11T21:32:22+09:00
---

# Ports And UnitOfWork

This document is authoritative for OMYM2 port usage, UnitOfWork policy, Clock and IdGenerator ports, transaction boundaries, and the apply / undo durable operation log exception.

Detailed execution order is in [../execution/apply.md](../execution/apply.md), and DB consistency details are in [../STORAGE.md](../STORAGE.md).

## Ports

External I/O is expressed as ports.

Representative examples:

```python
class UnitOfWork(Protocol):
    libraries: LibraryRepository
    check_runs: CheckRunRepository
    check_issues: CheckIssueRepository
    tracks: TrackRepository
    plans: PlanRepository
    plan_actions: PlanActionRepository
    runs: RunRepository
    file_events: FileEventRepository

    def usecase_scope(self) -> AbstractContextManager[None]: ...
    def __enter__(self) -> "UnitOfWork": ...
    def __exit__(self, exc_type, exc, tb) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
```

`check_runs` and `check_issues` persist each Library's latest completed check
diagnostics. Their replacement and browsing rules are authoritative in
[../contracts/db-schema.md](../contracts/db-schema.md#check_runs).

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
    def new_library_id(self) -> LibraryId: ...
    def new_check_run_id(self) -> CheckRunId: ...
    def new_track_id(self) -> TrackId: ...
    def new_plan_id(self) -> PlanId: ...
    def new_action_id(self) -> ActionId: ...
    def new_run_id(self) -> RunId: ...
    def new_event_id(self) -> EventId: ...
```

`Clock` and `IdGenerator` are ports. This makes it possible to fix time and IDs during tests.

In the initial implementation, IdGenerator returns UUIDv7-backed IDs. Domain and usecases depend on typed IDs such as LibraryId, CheckRunId, TrackId, PlanId, ActionId, RunId, and EventId, not on a concrete UUID library.

## UnitOfWork Policy

The baseline policy is `1 usecase = 1 UnitOfWork` object.

A usecase coordinates domain behavior and persistence through ports. Concrete repositories and transactions stay behind the UnitOfWork adapter.

`UnitOfWork.usecase_scope()` defines the outer lifetime of adapter resources that may be reused by multiple transaction scopes in one usecase. Apply uses it to retain one same-thread SQLite connection. The outer resource scope is not a transaction and must not merge, move, or remove any inner `with uow` transaction boundary. Other usecases may continue using one ordinary transaction scope without an outer resource scope.

## Transaction Boundary

Usecases define the business transition. The UnitOfWork adapter defines the concrete DB transaction mechanics.

Every `with uow` block starts and completes an independent transaction, even inside `usecase_scope()`. No transaction stays open across hashing or a Library music file mutation. Apply's committed PENDING FileEvent therefore remains visible and durable before the mover runs; connection reuse changes checkpoint timing, not commit ordering or durability. The SQLite-specific FULL/WAL rationale is authoritative in [../STORAGE.md](../STORAGE.md#db-consistency).

Repositories persist and restore domain models. They must not decide conflicts, duplicates, canonical paths, metadata validity, PlanAction status, or retry policy.

## Durable Operation Log Exception

`apply` and `undo` are practical exceptions to the simple `1 usecase = 1 UnitOfWork` shape because Library music file operations and DB transactions cannot be made fully atomic.

They must use FileEvents as a durable operation log rather than relying on one huge transaction.

Architecture preserves these boundaries:

* Usecases coordinate the operation.
* Adapters perform I/O through ports.
* FileEvents record Library music file mutations before they are executed.
