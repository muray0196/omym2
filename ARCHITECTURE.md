# Architecture

This document is the top-level OMYM2 architecture contract.

It is authoritative for the architecture overview and non-negotiable architecture rules.

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

## Dependency Boundaries Summary

Inbound adapters call features, features use domain, and domain may use shared primitives. Outbound adapters implement ports owned by features or common feature ports. `platform/` is the composition root; it wires concrete adapters to feature usecases, and CLI and Web entry points build their dependencies through it instead of constructing adapters themselves.

Detailed dependency direction, forbidden dependency lists, direct feature-to-feature import rules, and adapter boundary examples are authoritative in [docs/codebase/dependency-boundaries.md](docs/codebase/dependency-boundaries.md).

## Layer Responsibilities

`domain/` contains the shared domain kernel and pure domain rules. It performs no I/O and does not import DB, filesystem, HTTP, CLI, Web, TOML, or mutagen.

`features/` contains usecases divided by user goal. Usecases access the external world through ports and do not depend on concrete implementations such as SQLite, shutil, mutagen, FastAPI, or Typer.

`adapters/` implement ports and handle external I/O. Adapters may create and restore domain models, but they must not contain business rules such as conflict judgment, duplicate judgment, canonical path calculation, metadata validation, or PlanAction status decisions.

`platform/` wires concrete adapters to feature usecases and owns application runtime assembly. The `omym2` console script and `python -m omym2` both start through `platform/cli_entry_point.py`, which builds a `CommandDependencies` bundle via `platform/cli_composition.py` and dispatches into `adapters/cli/main.py`. `adapters/web/app.py` only assembles FastAPI routes and static assets from an injected `ApiRouteContext`; `platform/web_composition.py` builds that context and the concrete adapters behind it.

`shared/` contains only pure auxiliary primitives. It does not depend on domain, features, adapters, or platform.

## Ports And UnitOfWork Summary

External I/O is expressed as ports. Representative ports include UnitOfWork, FileScanner, FileSnapshotReader, MetadataReader, FileMover, ConfigStore, Clock, and IdGenerator.

The baseline policy is `1 usecase = 1 UnitOfWork`. Concrete repositories and transaction mechanics stay behind the UnitOfWork adapter.

`Clock` and `IdGenerator` are ports so tests can fix time and IDs. IdGenerator creates typed IDs for Library, Track, Plan, PlanAction, Run, and FileEvent.

`apply` and `undo` are practical exceptions to the simple `1 usecase = 1 UnitOfWork` shape because Library music file operations and DB transactions cannot be made fully atomic. They use FileEvents as a durable operation log.

## Naming Summary

Python module names use `snake_case.py`. Classes use `PascalCase`. Functions and variables use `snake_case`. Constants use `UPPER_SNAKE_CASE`.

Ambiguous module names such as `utils.py` and `helpers.py` are banned; the authoritative list is in [docs/codebase/naming.md](docs/codebase/naming.md).

Feature-local `domain/` and `adapters/` directories are not created in principle; the authoritative placement rule is in [docs/codebase/source-layout.md](docs/codebase/source-layout.md).

## Tests

Architecture tests enforce the highest-risk dependency and naming rules. The detailed architecture test scope is summarized in [docs/codebase/dependency-boundaries.md](docs/codebase/dependency-boundaries.md) and [docs/codebase/naming.md](docs/codebase/naming.md).
