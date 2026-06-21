# Architecture

This document is authoritative for OMYM2 architecture, dependency direction, layer responsibility, ports, UnitOfWork policy, transaction boundaries, durable operation log policy, and source file naming.

Domain semantics are in [docs/domain.md](docs/domain.md), execution semantics are in [docs/execution.md](docs/execution.md), and persistence details are in [docs/storage.md](docs/storage.md).

## Feature-Oriented Hexagonal Architecture

OMYM2 adopts Feature-oriented Hexagonal Architecture.

Core concepts such as Track, Plan, Run, FileEvent, and PathPolicy are not split by feature. They are placed in `domain/` as the shared domain kernel for all of OMYM2.

Features are divided by user goal, such as `settings`, `organize`, `add`, `refresh`, `apply`, `undo`, `check`, `plans`, `history`, and `inspect`.

CLI and Web call feature usecases as inbound adapters. DB, filesystem, metadata reader, and config loader implement ports as outbound adapters.

## Directory Structure

The Python package adopts the `src/` layout.

```text
src/
  omym2/
    domain/
      models/
        app_config.py
        track.py
        track_metadata.py
        file_scan_entry.py
        file_snapshot.py
        plan.py
        plan_action.py
        run.py
        file_event.py
        check_issue.py
      services/
        path_policy.py
        plan_builder.py
        collision_policy.py
        duplicate_policy.py
        metadata_fingerprint.py
        content_fingerprint.py
      errors.py

    features/
      common_ports.py

      add/
        usecases/
          create_add_plan.py
        ports.py
        dto.py

      organize/
        usecases/
          create_organize_plan.py
        ports.py
        dto.py

      refresh/
        usecases/
          create_refresh_plan.py
        ports.py
        dto.py

      apply/
        usecases/
          apply_plan.py
        ports.py
        dto.py

      undo/
        usecases/
          create_undo_plan.py
        ports.py
        dto.py

      check/
        usecases/
          check_library.py
        ports.py
        dto.py

      plans/
        usecases/
          list_plans.py
          get_plan_detail.py
        ports.py
        dto.py

      history/
        usecases/
          list_runs.py
          get_run_detail.py
        ports.py
        dto.py

      inspect/
        usecases/
          inspect_file.py
        ports.py
        dto.py

      settings/
        usecases/
          load_settings.py
          save_settings.py
          validate_settings.py
          preview_path_policy.py
        ports.py
        dto.py

    adapters/
      cli/
        main.py
        app.py
        commands/
          add.py
          organize.py
          refresh.py
          apply.py
          undo.py
          check.py
          plans.py
          history.py
          inspect.py
          config.py
          settings.py
        args/
          paths.py
          apply_options.py
          output_options.py

      web/
        app.py
        routes/
          settings.py
          plans.py
          history.py
          check.py
          tracks.py
        schemas/
          settings_form.py
          path_policy_preview_form.py
        templates/
        static/

      db/
        sqlite/
          unit_of_work.py
          repositories.py
          migrations/
            202606160001_initial_schema.sql

      fs/
        file_scanner.py
        file_snapshot_reader.py
        file_mover.py
        path_resolver.py
        hash_calculator.py

      metadata/
        mutagen_reader.py

      config/
        toml_config_store.py
        config_validator.py
        default_config.py

    platform/
      wiring.py
      runtime.py
      app_context.py

    shared/
      result.py
      ids.py
      paths.py
      time.py
      typing.py
```

`empty_dir_cleaner.py` is deferred until delete-empty-directory behavior is explicitly designed.

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
domain → adapters
domain → platform
domain → db
domain → fs
domain → web
domain → cli

features → concrete db/fs/web/cli implementations
features → internal implementations of other features

adapters/web/routes → direct filesystem operations
adapters/cli/commands → direct filesystem operations
templates → filesystem operations
```

Direct imports between features are prohibited in principle. When multiple usecases are chained, orchestration is done in CLI, Web, or platform.

For example, `omym2 add --apply` does not have `features/add` call `features/apply` directly. Instead, the CLI or platform calls `ApplyPlanUseCase` after executing `AddUseCase`.

## Layer Responsibilities

### domain/

`domain/` contains the core concepts of OMYM2 and pure domain rules.

Main targets:

* AppConfig
* Track
* TrackMetadata
* FileScanEntry
* FileSnapshot
* Plan
* PlanAction
* Run
* FileEvent
* PathPolicy
* CollisionPolicy
* DuplicatePolicy
* CheckIssue

`domain/` performs no I/O. It does not import DB, filesystem, HTTP, CLI, Web, TOML, or mutagen.

PathPolicy is a pure domain service.

```text
metadata + file extension + path policy config
  ↓
Library-root-relative canonical_path
```

This process does not call `path.exists()` and does not join with the Library root. The usecase checks the existence of actual files through ports after PathResolver has resolved the Library-root-relative path to an absolute filesystem path.

### features/

`features/` contains usecases divided by user goal.

* `settings`: read and write config, validate it, and preview path policy
* `organize`: scan the configured Library, create a relocation plan when needed, and register the Library when clean
* `add`: create an add plan from Incoming / specified source
* `refresh`: reload metadata and create a relocation plan
* `apply`: apply a Plan and update run / file_events / tracks
* `undo`: create an undo plan from a run and apply it if needed
* `check`: detect inconsistencies between the DB and the filesystem
* `plans`: get plan lists and details
* `history`: get runs / file_events
* `inspect`: check metadata / hash / canonical path for a single file

Usecases access the external world through ports. They do not depend on concrete implementations such as SQLite, shutil, mutagen, FastAPI, or Typer.

When a usecase needs files from a directory, it uses FileScanner only to discover FileScanEntry values. When it needs metadata or hashes, it captures FileSnapshot values through a separate port.

### adapters/

`adapters/` implement ports and handle external I/O.

* `adapters/db/sqlite`: SQLite repositories / UnitOfWork
* `adapters/fs`: file discovery / snapshot capture / move / path operations / hash calculation
* `adapters/metadata`: metadata reading with mutagen
* `adapters/config`: TOML config store / validator / defaults
* `adapters/cli`: CLI commands
* `adapters/web`: local Web UI

Adapters may create and restore domain models. They must not contain business rules.

Bad example:

```python
# adapters/db/sqlite/repositories.py

if target_path_exists:
    action = PlanAction.conflict(...)
```

Conflict judgment is the responsibility of a domain service or usecase.

Good example:

```python
# adapters/db/sqlite/repositories.py

return Track(
    id=row["id"],
    current_path=row["current_path"],
    metadata_hash=row["metadata_hash"],
)
```

This only restores a domain model from persisted data, so it is allowed.

### platform/

`platform/` is the composition root. It wires concrete adapters to feature usecases and owns application runtime assembly.

Feature-to-feature chaining belongs in CLI, Web, or platform orchestration, not inside a feature importing another feature's internals.

### shared/

`shared/` contains only pure auxiliary primitives.

* Result type
* ID value object helpers
* Pure functions for path string processing
* Time type helpers
* Typing helpers

`shared/` does not depend on domain, features, adapters, or platform.

## Ports and UnitOfWork Policy

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

FileScanner must not read tags or calculate hashes. FileSnapshotReader may compose filesystem stat, MetadataReader, hash calculation, and Clock, but it must not decide conflicts, duplicates, canonical paths, or PlanAction status.

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
    def new_track_id(self) -> TrackId: ...
    def new_plan_id(self) -> PlanId: ...
    def new_run_id(self) -> RunId: ...
```

`Clock` and `IdGenerator` are also ports. This makes it possible to fix time and IDs during tests.

In the initial implementation, IdGenerator returns UUIDv7-backed IDs. Domain and usecases depend on typed IDs such as TrackId, PlanId, and RunId, not on a concrete UUID library.

The basic policy is `1 usecase = 1 UnitOfWork`.

## Transaction and Durable Operation Log Policy

`apply` and `undo` are practical exceptions to the simple `1 usecase = 1 UnitOfWork` shape because Library music file operations and DB transactions cannot be made fully atomic.

They must use FileEvents as a durable operation log rather than relying on one huge transaction.

Architecture preserves these boundaries:

* Usecases coordinate the operation.
* Adapters perform I/O through ports.
* FileEvents record Library music file mutations before they are executed.

Detailed apply order is authoritative in [docs/execution.md](docs/execution.md). DB consistency details are authoritative in [docs/storage.md](docs/storage.md).

## Source File Naming Rules

File naming under `src` is part of Feature-oriented Hexagonal Architecture. Naming rules preserve responsibility boundaries.

### Common Rules

```text
Python module name   snake_case.py
Class name           PascalCase
Function / variable  snake_case
Constant             UPPER_SNAKE_CASE
```

Avoid ambiguous names.

```text
Names to avoid:
  utils.py
  helpers.py
  manager.py
  service.py
```

Even when placing shared processing as an exception, use a concrete concern name.

### Naming in domain

`domain/` is noun-based. Do not place names that imply I/O or execution procedures.

Examples:

```text
domain/models/
  track.py
  track_metadata.py
  file_scan_entry.py
  file_snapshot.py
  plan.py
  plan_action.py
  run.py
  file_event.py
  check_issue.py

domain/services/
  path_policy.py
  plan_builder.py
  collision_policy.py
  duplicate_policy.py
  metadata_fingerprint.py
  content_fingerprint.py
```

Even under `domain/services/`, do not append `_service.py` to file names. The directory already indicates that they are services.

### Naming in features

`features/{feature}/` is divided by user goal.

```text
features/{feature}/
  usecases/
    {verb}_{object}.py
  ports.py
  dto.py
```

Examples:

```text
features/add/usecases/create_add_plan.py
features/apply/usecases/apply_plan.py
features/check/usecases/check_library.py
```

Do not create `features/{feature}/domain/` or `features/{feature}/adapters/` in principle.

### Naming in adapters

Adapter names may include technical names or role names.

Examples:

```text
adapters/cli/commands/add.py
adapters/web/routes/settings.py
adapters/db/sqlite/unit_of_work.py
adapters/fs/file_scanner.py
adapters/fs/file_snapshot_reader.py
adapters/metadata/mutagen_reader.py
```

Do not use the name DAO in the DB adapter.

### Naming Not Adopted

The following are not adopted.

```text
features/{feature}/domain/
features/{feature}/adapters/
platform/*_dao.py
*_service.py
utils.py
helpers.py
manager.py
common.py
```
