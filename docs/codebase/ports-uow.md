---
type: Codebase Reference
title: Ports And UnitOfWork
description: Defines OMYM2's port protocols (UnitOfWork, FileScanner, Clock, IdGenerator, etc.), the 1-usecase-1-UnitOfWork policy, transaction boundaries, and the FileEvents durable operation log exception for apply/undo.
tags: [ports, unit-of-work, transactions, architecture]
timestamp: 2026-06-30T23:47:13+09:00
---

# Ports And UnitOfWork

This document is authoritative for OMYM2 port usage, UnitOfWork policy, Clock and IdGenerator ports, transaction boundaries, and the apply / undo durable operation log exception.

Detailed execution order is in [../execution/apply.md](../execution/apply.md), and DB consistency details are in [../STORAGE.md](../STORAGE.md).

## Ports

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
    def new_track_id(self) -> TrackId: ...
    def new_plan_id(self) -> PlanId: ...
    def new_action_id(self) -> ActionId: ...
    def new_run_id(self) -> RunId: ...
    def new_event_id(self) -> EventId: ...
```

`Clock` and `IdGenerator` are ports. This makes it possible to fix time and IDs during tests.

In the initial implementation, IdGenerator returns UUIDv7-backed IDs. Domain and usecases depend on typed IDs such as LibraryId, TrackId, PlanId, ActionId, RunId, and EventId, not on a concrete UUID library.

## UnitOfWork Policy

The baseline policy is `1 usecase = 1 UnitOfWork`.

A usecase coordinates domain behavior and persistence through ports. Concrete repositories and transactions stay behind the UnitOfWork adapter.

## Transaction Boundary

Usecases define the business transition. The UnitOfWork adapter defines the concrete DB transaction mechanics.

Repositories persist and restore domain models. They must not decide conflicts, duplicates, canonical paths, metadata validity, PlanAction status, or retry policy.

## Durable Operation Log Exception

`apply` and `undo` are practical exceptions to the simple `1 usecase = 1 UnitOfWork` shape because Library music file operations and DB transactions cannot be made fully atomic.

They must use FileEvents as a durable operation log rather than relying on one huge transaction.

Architecture preserves these boundaries:

* Usecases coordinate the operation.
* Adapters perform I/O through ports.
* FileEvents record Library music file mutations before they are executed.
