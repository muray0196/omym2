# Architecture

This document is the top-level OMYM2 architecture entry point.

It is authoritative for the architecture overview, non-negotiable architecture rules, and routing to detailed architecture documents. Detailed architecture rules live in [docs/architecture/](docs/architecture/).

Domain semantics are in [docs/domain.md](docs/domain.md), execution semantics are in [docs/execution/](docs/execution/), and storage contracts are in [docs/storage.md](docs/storage.md) plus [docs/contracts/](docs/contracts/).

## Architecture Model

OMYM2 adopts Feature-oriented Hexagonal Architecture.

Core concepts such as Library, Track, Plan, Run, FileEvent, and PathPolicy are shared as a domain kernel. Features are divided by user goal. CLI and Web are inbound adapters. DB, filesystem, metadata reader, and config loader are outbound adapters.

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
* Library identity is stable by `library_id`, not root path.
* Stored Library-managed paths are Library-root-relative.
* Source file names under `src/` must follow the documented naming rules.

## Dependency Direction

Inbound adapters call features, features use domain, and domain may use shared primitives.

```text
adapters/cli, adapters/web
  ↓
features/*/usecases/*.py
  ↓
domain/
  ↓
shared/
```

Outbound adapters implement ports owned by features or common feature ports.

```text
adapters/db, adapters/fs, adapters/metadata, adapters/config
  ↓
features/*/ports.py or features/common_ports.py
  ↓
domain/
```

`platform/` is the composition root and wires features and adapters together.

## Forbidden Dependencies

```text
domain -> adapters
domain -> platform
domain -> db
domain -> fs
domain -> web
domain -> cli

features -> concrete db/fs/web/cli implementations
features -> internal implementations of other features

adapters/web/routes -> direct filesystem operations
adapters/cli/commands -> direct filesystem operations
templates -> filesystem operations
```

Direct imports between features are prohibited in principle. When multiple usecases are chained, orchestration is done in CLI, Web, or platform.

## Layer Responsibilities

`domain/` contains the shared domain kernel and pure domain rules. It performs no I/O and does not import DB, filesystem, HTTP, CLI, Web, TOML, or mutagen.

`features/` contains usecases divided by user goal. Usecases access the external world through ports and do not depend on concrete implementations such as SQLite, shutil, mutagen, FastAPI, or Typer.

`adapters/` implement ports and handle external I/O. Adapters may create and restore domain models, but they must not contain business rules such as conflict judgment, duplicate judgment, canonical path calculation, metadata validation, or PlanAction status decisions.

`platform/` wires concrete adapters to feature usecases and owns application runtime assembly.

`shared/` contains only pure auxiliary primitives. It does not depend on domain, features, adapters, or platform.

## Ports And UnitOfWork Summary

External I/O is expressed as ports. Representative ports include UnitOfWork, FileScanner, FileSnapshotReader, MetadataReader, FileMover, ConfigStore, Clock, and IdGenerator.

The baseline policy is `1 usecase = 1 UnitOfWork`. Concrete repositories and transaction mechanics stay behind the UnitOfWork adapter.

`Clock` and `IdGenerator` are ports so tests can fix time and IDs. IdGenerator creates typed IDs for Library, Track, Plan, PlanAction, Run, and FileEvent.

`apply` and `undo` are practical exceptions to the simple `1 usecase = 1 UnitOfWork` shape because Library music file operations and DB transactions cannot be made fully atomic. They use FileEvents as a durable operation log.

## Naming Summary

Python module names use `snake_case.py`. Classes use `PascalCase`. Functions and variables use `snake_case`. Constants use `UPPER_SNAKE_CASE`.

Avoid vague module names:

```text
utils.py
helpers.py
manager.py
service.py
common.py
```

Do not create `features/{feature}/domain/` or `features/{feature}/adapters/` in principle.

## Architecture Document Routing

Detailed architecture routing is in [docs/architecture/index.md](docs/architecture/index.md).

## Tests

Architecture tests enforce the highest-risk rules:

* source files follow naming conventions
* usecases do not import concrete SQLite or filesystem adapters
* domain does not import adapters or platform
* shared stays below upper layers

## Execution And Storage Links

Plan-centered execution rules are authoritative in [docs/execution/model.md](docs/execution/model.md), [docs/execution/apply.md](docs/execution/apply.md), and the task-specific execution docs.

Storage responsibility is authoritative in [docs/storage.md](docs/storage.md). Config, DB schema, path identity, and status values are authoritative in [docs/contracts/](docs/contracts/).
