---
type: Codebase Reference
title: Source Layout
description: Feature-oriented source layout, package placement, per-layer contents, and directory-addition rules.
tags: [source-layout, architecture, artist-names, operations, desktop, hexagonal-architecture, python]
timestamp: 2026-07-18T12:00:00+09:00
---

# Source Layout

Authoritative for the source layout, package placement, feature-oriented structure, and rules for adding directories. Dependency rules: [dependency-boundaries.md](dependency-boundaries.md).

## Layout Rule

Python `src/` layout, organized around Feature-oriented Hexagonal Architecture:

```text
src/
  omym2/
    domain/      # models/, services/ — shared domain kernel
    features/    # common_ports.py + one package per user goal
    adapters/    # cli/, desktop/, web/, db/, fs/, metadata/, config/, artist_ids/
    platform/    # composition root
    shared/      # pure auxiliary primitives
```

Core concepts (Library, Track, Plan, Run, FileEvent, Operation, PathPolicy, …) are not split by feature; they live in `domain/` as the shared kernel. Features are divided by user goal: `bootstrap`, `settings`, `artist_names`, `artist_ids`, `organize`, `add`, `refresh`, `apply`, `undo`, `check`, `operations`, `plans`, `history`, `tracks`, `inspect`. CLI and Web call feature usecases as inbound adapters. The desktop shell is a presentation adapter around the platform-composed Web application and does not call features directly. DB, filesystem, metadata reader, config loader, and artist-name integrations implement ports as outbound adapters. The live source tree remains the implementation evidence for exact contents.

## domain/

Core concepts and pure domain rules: AppConfig, AcceptedArtistName, Library, Track, TrackMetadata, FileScanEntry, FileSnapshot, Plan, PlanAction, Run, FileEvent, Operation, PathPolicy, ArtistNameProjection, ArtistNameResolution, CollisionPolicy, CheckRun, CheckIssue. `domain/` performs no I/O and does not import DB, filesystem, HTTP, CLI, Web, TOML, or mutagen. PathPolicy is a pure domain service.

## features/

Usecases divided by user goal:

* `settings`: read/write/validate config; preview path policy
* `bootstrap`: project Config validity, unambiguous Library readiness, runtime capabilities, and polling policy without the Web route reading storage directly
* `artist_names`: resolve whole artist/album-artist source values through one editable original-to-Latin mapping, deterministic Unicode-script eligibility, and provider acceptance; owns revision-checked mapping edits
* `organize`: scan the selected Library, create a relocation plan when needed, register when clean
* `add`: create an add plan from Incoming / specified source
* `refresh`: reload metadata and create a relocation plan
* `apply`: apply a Plan and update run / file_events / tracks
* `undo`: create an undo plan from a run and apply it if needed
* `check`: detect DB/filesystem inconsistencies
* `operations`: retrieve durable Operation state and reconcile interrupted lifecycle records without dispatching another feature
* `plans` / `history` / `tracks`: read-only lists and details
* `inspect`: metadata / hash / canonical path for a single file

Usecases access the external world through ports — no SQLite, shutil, mutagen, FastAPI, or Typer. Directory discovery uses FileScanner for FileScanEntry values only; metadata/hashes come through a separate snapshot port.

## adapters/

* `adapters/db/sqlite`: SQLite repositories / UnitOfWork, including editable artist-name mappings and provenance
* `adapters/fs`: file discovery, snapshot capture, move, path operations, hash calculation, native application-root exclusive lock
* `adapters/metadata`: metadata reading with mutagen
* `adapters/artist_ids`: raw MusicBrainz artist search used by the shared artist-name resolver
* `adapters/config`: TOML config store / validator / defaults
* `adapters/cli`: CLI commands
* `adapters/desktop`: retained loopback Uvicorn server plus one pywebview window; native-window and server-lifecycle mechanics only
* `adapters/web`: typed local JSON routes, the schema-only FastAPI factory, and packaged SPA serving. `schema_app.py` registers the production route/model set without constructing Config, SQLite, filesystem, metadata, network, or static-build collaborators.

Adapters may create and restore domain models but contain no business rules.

## platform/

The composition root; wires concrete adapters to feature usecases and owns runtime assembly.

* `runtime_context.py`: `RuntimeContext` (resolved config file, database file, shared `TomlConfigStore`, shared `MutagenMetadataReader`) and `runtime_context_for(...)` resolving `default_application_paths()` once per invocation
* `feature_composition.py`: `build_*` functions constructing feature `*Ports` dataclasses from concrete adapters, plus `build_uow`; normal Plan ports receive the shared local artist-name resolver
* `artist_name_composition.py`: language-predictor and MusicBrainz-provider selection plus shared cache-aware resolver composition
* `cli_composition.py`: `build_command_dependencies(...)` for one CLI invocation
* `cli_path_normalization.py`: `normalize_cli_path(...)`, injected into add/organize/refresh command dependencies so handlers do not resolve filesystem paths directly
* `cli_entry_point.py`: `main()` / `run_cli(...)` — entry for both the `omym2` console script and `python -m omym2`
* `desktop_entry_point.py`: Windows GUI-script entry; selects the stable desktop application root, configures desktop logging, composes the Web app with the desktop runtime
* `desktop_runtime.py`: coordinates server readiness, the blocking native window, and graceful shutdown without feature behavior
* `web_composition.py`: `build_api_route_context(...)` composes the Bootstrap usecase from Config and Library snapshot ports; `build_web_app(...)` supplies that context to the FastAPI app. Schema generation uses the adapter's no-I/O `create_api_schema_app()` factory.
* `operation_composition.py`: wires durable Operation persistence, the application-root lock, status polling, reconciliation, and the one-slot worker invoking already-wired feature usecases without features importing each other

Feature-to-feature chaining belongs in CLI, Web, or platform orchestration, never inside a feature importing another feature's internals.

## shared/

Pure auxiliary primitives only: ID value object helpers, keyset pagination/cursor helpers, pure path string processing, time type helpers. `shared/` does not depend on domain, features, adapters, or platform.

## Adding Directories

Add a new top-level package directory only when existing layers cannot express the responsibility. Do not add feature-local layer directories — this is the authoritative statement of that rule:

```text
features/{feature}/domain/
features/{feature}/adapters/
```
