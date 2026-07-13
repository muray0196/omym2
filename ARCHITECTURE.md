# Architecture

This document is the top-level OMYM2 architecture contract and the always-read
architecture safety cache for code, Web, and test work.

It is authoritative for the architecture overview and non-negotiable global
rules. Focused docs own detailed implementation contracts.

## Architecture Model

OMYM2 adopts Feature-oriented Hexagonal Architecture.

Core concepts such as Library, Track, Plan, Run, FileEvent, Operation, CheckRun,
and PathPolicy are shared as a domain kernel. Features are divided by user
goal. CLI and Web are inbound adapters. DB, filesystem, metadata reader, and
config loader are outbound adapters.

The package uses the Python `src/` layout:

```text
src/
  omym2/
    domain/
    features/
    adapters/
    platform/
    shared/
```

## Non-Negotiable Rules

* Domain and features must not depend on concrete adapters.
* Domain performs no I/O.
* Features access the external world through ports.
* Direct imports between features are prohibited in principle.
* Feature-to-feature chaining belongs in CLI, Web, or platform orchestration.
* Adapters may create and restore domain models, but must not contain business rules.
* Library music file mutations must go through a Plan.
* Apply must use recorded PlanActions and must not recalculate target paths from the latest AppConfig.
* FileEvents record Library music file mutations before those mutations execute.
* Web and CLI use one shared cross-process exclusive-operation lock; only one state-changing operation may hold it, while read-only snapshots remain available.
* A durable Operation records background-request lifecycle, progress, and interruption; it never substitutes for a FileEvent recording an attempted Library music file mutation.
* Apply acceptance holds the exclusive lock, verifies the Library root, and atomically compare-and-sets `ready` to `applying` while inserting a `running` Run and `queued` Operation in one transaction.
* Apply work is not dispatched before that acceptance transaction commits, and the exclusive lock remains held throughout the background worker.
* Config saves from Web and CLI use the same opaque raw-storage revision compare-and-set and atomic-replace protocol under the exclusive lock; last-write-wins is prohibited.
* Library identity is stable by `library_id`, not root path.
* Stored Library-managed paths are Library-root-relative.
* Source file names under `src/` must follow the documented naming rules.

## Dependency Boundaries Summary

Inbound adapters call features, features use domain, and domain may use shared primitives. Outbound adapters implement ports owned by features or common feature ports. `platform/` is the composition root; it wires concrete adapters to feature usecases, and CLI and Web entry points build their dependencies through it instead of constructing adapters themselves.

Detailed dependency direction, forbidden dependency lists, direct feature-to-feature import rules, and adapter boundary examples are authoritative in [docs/codebase/dependency-boundaries.md](docs/codebase/dependency-boundaries.md).

## Layer Responsibilities

`domain/` contains the shared domain kernel and pure domain rules. It performs no I/O and does not import DB, filesystem, HTTP, CLI, Web, TOML, or mutagen.

`features/` contains usecases divided by user goal. Usecases access the external world through ports and do not depend on concrete implementations such as SQLite, shutil, mutagen, FastAPI, or Typer.

`adapters/` implement ports and handle external I/O. Adapters may create and restore domain models, but they must not contain business rules such as conflict judgment, duplicate judgment, canonical path calculation, metadata validation, or PlanAction status decisions.

`platform/` wires concrete adapters to feature usecases and owns application
runtime assembly. CLI and Web entry points build dependencies through it rather
than constructing concrete adapters themselves. The current composition layout
is documented in [docs/codebase/source-layout.md](docs/codebase/source-layout.md)
and [docs/codebase/web-frontend.md](docs/codebase/web-frontend.md).

`shared/` contains only pure auxiliary primitives. It does not depend on domain, features, adapters, or platform.

## Ports And UnitOfWork Summary

External I/O is expressed as ports. Representative ports include UnitOfWork,
FileScanner, FileSnapshotReader, MetadataReader, FileMover, ConfigStore,
ExclusiveOperationLock, OperationProgressReporter, Clock, and IdGenerator.

The baseline policy is `1 usecase = 1 UnitOfWork`. Concrete repositories and transaction mechanics stay behind the UnitOfWork adapter.

`Clock` and `IdGenerator` are ports so tests can fix time and IDs. IdGenerator
creates typed IDs for Library, CheckRun, Track, Plan, PlanAction, Run, and
FileEvent, and Operation.

UnitOfWork exposes Operation persistence and one atomic Apply-claim capability
that commits the Plan transition, Run, and queued Operation together before
dispatch. `apply` and `undo` remain practical exceptions to the simple
`1 usecase = 1 UnitOfWork` shape because Library music file operations and DB
transactions cannot be made fully atomic. They preserve independently
committed pending FileEvents before each Library music file mutation.

## Naming Summary

Python module names use `snake_case.py`. Classes use `PascalCase`. Functions and variables use `snake_case`. Constants use `UPPER_SNAKE_CASE`.

Ambiguous module names such as `utils.py` and `helpers.py` are banned; the authoritative list is in [docs/codebase/naming.md](docs/codebase/naming.md).

Feature-local `domain/` and `adapters/` directories are not created in principle; the authoritative placement rule is in [docs/codebase/source-layout.md](docs/codebase/source-layout.md).

## Tests

Architecture tests enforce the highest-risk dependency and naming rules. The detailed architecture test scope is summarized in [docs/codebase/dependency-boundaries.md](docs/codebase/dependency-boundaries.md) and [docs/codebase/naming.md](docs/codebase/naming.md).
