---
type: Codebase Reference
title: Source Layout
description: Defines OMYM2's feature-oriented source layout, including artist naming, Bootstrap, durable Operation, desktop-shell placement, dependency layers, composition, and directory rules.
tags: [source-layout, architecture, artist-names, operations, desktop, hexagonal-architecture, python]
timestamp: 2026-07-17T22:43:57+09:00
---

# Source Layout

This document is authoritative for the OMYM2 source layout, package placement, feature-oriented structure, and rules for adding directories.

Dependency rules are in [dependency-boundaries.md](dependency-boundaries.md).

## Layout Rule

OMYM2 uses the Python `src/` layout.

The package is organized around Feature-oriented Hexagonal Architecture:

```text
src/
  omym2/
    domain/
    features/
    adapters/
    platform/
    shared/
```

Core concepts such as Library, Track, Plan, Run, FileEvent, Operation, and
PathPolicy are not split by feature. They are placed in `domain/` as the shared
domain kernel for all of OMYM2.

Features are divided by user goal, such as `bootstrap`, `settings`,
`artist_names`, `artist_ids`, `organize`, `add`, `refresh`, `apply`, `undo`,
`check`, `operations`, `plans`, `history`, `tracks`, and `inspect`.

CLI and Web call feature usecases as inbound adapters. The desktop shell is a
presentation adapter around the platform-composed Web application; it does not
call features directly. DB, filesystem, metadata reader, config loader, and
artist-name integrations implement ports as outbound adapters.

## Representative Package Structure

This tree is representative. The live source tree remains the implementation evidence.

```text
src/
  omym2/
    domain/
      models/
      services/

    features/
      common_ports.py
      bootstrap/
      add/
      artist_names/
      artist_ids/
      organize/
      refresh/
      apply/
      undo/
      check/
      operations/
      plans/
      history/
      inspect/
      tracks/
      settings/

    adapters/
      cli/
      desktop/
      web/
      db/
      fs/
      metadata/
      config/
      artist_ids/

    platform/

    shared/
```

## domain/

`domain/` contains the core concepts of OMYM2 and pure domain rules.

Main targets:

* AppConfig
* AcceptedArtistName
* Library
* Track
* TrackMetadata
* FileScanEntry
* FileSnapshot
* Plan
* PlanAction
* Run
* FileEvent
* Operation
* PathPolicy
* ArtistNameProjection
* ArtistNameResolution
* CollisionPolicy
* CheckRun
* CheckIssue

`domain/` performs no I/O. It does not import DB, filesystem, HTTP, CLI, Web, TOML, or mutagen.

PathPolicy is a pure domain service.

## features/

`features/` contains usecases divided by user goal.

* `settings`: read and write config, validate it, and preview path policy
* `bootstrap`: project Config validity, unambiguous Library readiness, runtime
  capabilities, and polling policy without making the Web route read storage
  directly
* `artist_names`: resolve whole artist and album-artist source values through
  one editable original-to-Latin mapping, deterministic Unicode-script
  eligibility, and provider acceptance; it also owns revision-checked mapping edits
* `organize`: scan the selected Library, create a relocation plan when needed, and register the Library when clean
* `add`: create an add plan from Incoming / specified source
* `refresh`: reload metadata and create a relocation plan
* `apply`: apply a Plan and update run / file_events / tracks
* `undo`: create an undo plan from a run and apply it if needed
* `check`: detect inconsistencies between the DB and the filesystem
* `operations`: retrieve durable Operation state and reconcile interrupted
  lifecycle records without dispatching another feature
* `plans`: get plan lists and details
* `history`: get runs / file_events
* `tracks`: list managed Tracks for read-only inspection
* `inspect`: check metadata / hash / canonical path for a single file

Usecases access the external world through ports. They do not depend on concrete implementations such as SQLite, shutil, mutagen, FastAPI, or Typer.

When a usecase needs files from a directory, it uses FileScanner only to discover FileScanEntry values. When it needs metadata or hashes, it captures FileSnapshot values through a separate port.

## adapters/

`adapters/` implement ports and handle external I/O.

* `adapters/db/sqlite`: SQLite repositories / UnitOfWork, including editable artist-name mappings and provenance
* `adapters/fs`: file discovery / snapshot capture / move / path operations /
  hash calculation / native application-root exclusive lock
* `adapters/metadata`: metadata reading with mutagen
* `adapters/artist_ids`: raw MusicBrainz artist search used by the shared
  artist-name resolver
* `adapters/config`: TOML config store / validator / defaults
* `adapters/cli`: CLI commands
* `adapters/desktop`: the retained loopback Uvicorn server and one pywebview
  window; it owns native-window and server-lifecycle mechanics only
* `adapters/web`: typed local JSON routes, the schema-only FastAPI factory, and
  packaged SPA serving. `schema_app.py` registers the production route/model
  set without constructing Config, SQLite, filesystem, metadata, network, or
  static-build collaborators.

Adapters may create and restore domain models. They must not contain business rules.

## platform/

`platform/` is the composition root. It wires concrete adapters to feature usecases and owns application runtime assembly.

* `runtime_context.py`: `RuntimeContext` (resolved config file, database file, a shared `TomlConfigStore`, and a shared `MutagenMetadataReader`) and `runtime_context_for(...)`, which resolves `default_application_paths()` once per invocation.
* `feature_composition.py`: `build_*` functions that construct feature `*Ports` dataclasses from concrete adapters (add, apply, check, history, inspect, organize, plans, refresh, settings, tracks, undo), plus `build_uow`; normal Plan ports receive the shared local artist-name resolver.
* `artist_name_composition.py`: language-predictor and MusicBrainz-provider selection plus shared cache-aware artist-name resolver composition for Plan and naming consumers.
* `cli_composition.py`: `build_command_dependencies(...)`, which builds the full `CommandDependencies` bundle for one CLI invocation.
* `cli_path_normalization.py`: `normalize_cli_path(...)`, injected into add, organize, and refresh command dependencies so their handlers do not resolve filesystem paths directly.
* `cli_entry_point.py`: `main()` / `run_cli(...)`, the process entry point that both the `omym2` console script and `python -m omym2` route through.
* `desktop_entry_point.py`: the Windows GUI-script entry point; it selects the
  stable desktop application root, configures desktop logging, and composes the
  existing Web app with the desktop runtime.
* `desktop_runtime.py`: coordinates server readiness, the blocking native
  window, and graceful shutdown without implementing feature behavior.
* `web_composition.py`: `build_api_route_context(...)` composes the Bootstrap
  usecase from Config and Library snapshot ports, and `build_web_app(...)`
  supplies that typed context to the FastAPI app. Schema generation instead
  uses the adapter's no-I/O `create_api_schema_app()` factory.
* `operation_composition.py`: wires durable Operation persistence, the
  application-root lock, status polling, reconciliation, and the one-slot
  worker that invokes already-wired feature usecases without making features
  import each other.

Feature-to-feature chaining belongs in CLI, Web, or platform orchestration, not inside a feature importing another feature's internals.

## shared/

`shared/` contains only pure auxiliary primitives.

* ID value object helpers
* Keyset pagination and cursor helpers
* Pure functions for path string processing
* Time type helpers

`shared/` does not depend on domain, features, adapters, or platform.

## Adding Directories

Add a new top-level package directory only when the existing layers cannot express the responsibility.

Do not add feature-local layer directories. This is the authoritative statement of that rule:

```text
features/{feature}/domain/
features/{feature}/adapters/
```
