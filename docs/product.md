# Product

This document explains what OMYM2 is and is not. Detailed architecture rules live in [../ARCHITECTURE.md](../ARCHITECTURE.md), and execution semantics live in [execution.md](execution.md).

## Overview

OMYM2 is a local tool for safely importing music files into an organized library.

The primary usage model is execution through the CLI. The GUI is a local settings and status console.

OMYM2 is not a full GUI music management application. Its shape is:

```text
Headless domain/usecase core + CLI runner + Web settings console
```

The main value is not moving files quickly. The value is moving files through a reviewed Plan while keeping enough state and history to diagnose failures and recover safely.

## Basic Policy

This is a product-level summary. Architecture rules are authoritative in [../ARCHITECTURE.md](../ARCHITECTURE.md), execution rules are authoritative in [execution.md](execution.md), and storage rules are authoritative in [storage.md](storage.md).

* Configuration files and DB are contained under the root directory, making the application portable, excluding the music library and incoming folder.
* Execution is primarily performed from the CLI.
* Settings can be changed and checked from the local Web UI.
* Domain and usecases are independent from CLI, Web UI, DB, and filesystem.
* Library music file mutations always go through a Plan.
* Read-only scans, metadata reads, hash calculations, and inspections do not require a Plan.
* Feature-oriented Hexagonal Architecture is adopted.
* The `src` layout and source file naming rules are fixed as part of the architecture.
* Core concepts such as Track, Plan, Run, FileEvent, and PathPolicy are shared as a domain kernel.
* External I/O is confined to adapters.
* Execution history is recorded in the DB.
* Settings are managed as human-readable TOML files.
* Library-managed paths stored in the DB are normalized paths relative to the Library root.
* Tag editing is not supported.
* Relocation after tag correction is handled by refresh.

## Primary Use Case

The primary use case is safely adding new music files from an Incoming folder into the Library.

```text
Incoming folder
  ↓
scan
  ↓
create plan
  ↓
review
  ↓
apply
  ↓
Library
```

The daily entry point is `omym2 add`.

OMYM2 is not a tool that reorganizes the entire existing library every time. Daily use treats it as a tool for safely importing newly added tracks.

On first use, the existing Library must be registered into OMYM2's managed state. During setup, config and DB are created, and the existing Library is scanned.

```text
setup
  ↓
create config / DB
  ↓
scan existing Library
  ↓
record tracks
```

`setup` does not move or mutate Library music files. It may register existing files in the DB without creating a Plan because it does not perform Library music file mutations.

Relocation of the existing Library is separate from the daily `add` flow. When needed, `omym2 organize` creates an organization plan.

## Non-Goals

The initial version does not cover:

* Tag editing
* Automatic monitoring
* Electron / Tauri packaging
* Complex duplicate resolution
* Advanced library management
* Large-scale file operations through a full GUI
* Associated file handling such as cover images, cue files, lyrics, or booklets
* Audio-part hashing
* GUI-based plan application
* Automatic filesystem repair
* Retrying partially failed Plans

Tag correction is delegated to external tools. OMYM2 is responsible for re-evaluation and relocation after correction.

## Usage Image

First use:

```bash
omym2 setup
```

Daily add flow:

```bash
omym2 add
```

Plan review and apply:

```bash
omym2 plans
omym2 apply <plan-id>
omym2 apply latest
```

Maintenance:

```bash
omym2 refresh <library-file>
omym2 organize
omym2 history
omym2 undo <run-id>
omym2 check
omym2 inspect <file>
omym2 settings
```

## Role of the UI

The GUI is a settings console, not an execution screen.

The main roles of the GUI are:

* Setting the Library path
* Setting the Incoming path
* Editing the path policy
* Setting required metadata fields
* Setting behavior for duplicates
* Setting behavior for conflicts
* Validating settings
* Displaying diffs before and after settings changes
* Reviewing execution history
* Checking the state of the DB and filesystem

In the initial stage, the GUI focuses on read/write settings and read-only history / check views. Large-scale file movement is left to the CLI.

## Web UI Screen Ideas

Initial screens:

* Settings
* Path Policy Preview
* Runs
* Run Detail
* Check
* Tracks

Applying Plans from the GUI is deferred.

## Product-Facing Technical Policy

This section is a product-facing summary of technology choices. Layering and adapter responsibilities are authoritative in [../ARCHITECTURE.md](../ARCHITECTURE.md).

Initial assumptions:

```text
Language: Python
DB: SQLite
Config: TOML
Web: FastAPI + Jinja2 + htmx
CLI: Typer or argparse
Test: pytest
E2E: Playwright
Metadata extractor: mutagen
```

The Web UI runs on localhost as a local settings console. Settings UI is represented by `omym2 settings`.
