---
type: Codebase Reference
title: Source Layout
description: Authoritative description of OMYM2's src/ layout and Feature-oriented Hexagonal Architecture, covering the domain, features, adapters, platform, and shared packages and rules for adding new directories.
tags: [source-layout, architecture, hexagonal-architecture, python]
timestamp: 2026-07-07T00:39:14+09:00
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

Core concepts such as Library, Track, Plan, Run, FileEvent, and PathPolicy are not split by feature. They are placed in `domain/` as the shared domain kernel for all of OMYM2.

Features are divided by user goal, such as `settings`, `artist_ids`, `organize`, `add`, `refresh`, `apply`, `undo`, `check`, `plans`, `history`, `tracks`, and `inspect`.

CLI and Web call feature usecases as inbound adapters. DB, filesystem, metadata reader, and config loader implement ports as outbound adapters.

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
      add/
      organize/
      refresh/
      apply/
      undo/
      check/
      plans/
      history/
      inspect/
      tracks/
      settings/

    adapters/
      cli/
      web/
      db/
      fs/
      metadata/
      config/

    platform/

    shared/
```

## domain/

`domain/` contains the core concepts of OMYM2 and pure domain rules.

Main targets:

* AppConfig
* Library
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

## features/

`features/` contains usecases divided by user goal.

* `settings`: read and write config, validate it, and preview path policy
* `artist_ids`: generate and save artist ID path values in config, preserving existing entries unless overwrite is requested
* `organize`: scan the selected Library, create a relocation plan when needed, and register the Library when clean
* `add`: create an add plan from Incoming / specified source
* `refresh`: reload metadata and create a relocation plan
* `apply`: apply a Plan and update run / file_events / tracks
* `undo`: create an undo plan from a run and apply it if needed
* `check`: detect inconsistencies between the DB and the filesystem
* `plans`: get plan lists and details
* `history`: get runs / file_events
* `tracks`: list managed Tracks for read-only inspection
* `inspect`: check metadata / hash / canonical path for a single file

Usecases access the external world through ports. They do not depend on concrete implementations such as SQLite, shutil, mutagen, FastAPI, or Typer.

When a usecase needs files from a directory, it uses FileScanner only to discover FileScanEntry values. When it needs metadata or hashes, it captures FileSnapshot values through a separate port.

## adapters/

`adapters/` implement ports and handle external I/O.

* `adapters/db/sqlite`: SQLite repositories / UnitOfWork
* `adapters/fs`: file discovery / snapshot capture / move / path operations / hash calculation
* `adapters/metadata`: metadata reading with mutagen
* `adapters/artist_ids`: fastText Japanese-name detection and MusicBrainz artist name lookup
* `adapters/config`: TOML config store / validator / defaults
* `adapters/cli`: CLI commands
* `adapters/web`: local Web UI

Adapters may create and restore domain models. They must not contain business rules.

## platform/

`platform/` is the intended composition root. It wires concrete adapters to feature usecases and owns application runtime assembly.

Today `platform/` is an empty placeholder package; the actual wiring is currently done by `adapters/cli/commands/*.py` and `adapters/web/app.py`.

Feature-to-feature chaining belongs in CLI, Web, or platform orchestration, not inside a feature importing another feature's internals.

## shared/

`shared/` contains only pure auxiliary primitives.

* Result type
* ID value object helpers
* Pure functions for path string processing
* Time type helpers
* Typing helpers

`shared/` does not depend on domain, features, adapters, or platform.

## Adding Directories

Add a new top-level package directory only when the existing layers cannot express the responsibility.

Do not add feature-local layer directories. This is the authoritative statement of that rule:

```text
features/{feature}/domain/
features/{feature}/adapters/
```

`empty_dir_cleaner.py` is deferred until delete-empty-directory behavior is explicitly designed.
