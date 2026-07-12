---
type: Product Overview
title: Product
description: Describes OMYM2's product shape as a headless domain core with a CLI runner and a local Web UI for settings, Plan creation and review, and status; defines its primary safe-import use case and technology stack.
tags: [product, overview, cli, web-ui]
timestamp: 2026-07-12T21:25:28+09:00
---

# Product

This document explains what OMYM2 is and is not. Execution semantics live in [execution/](execution/).

## Overview

OMYM2 safely imports local music files into an organized library.

The primary usage model is execution through the CLI. The local Web UI supports
settings, Plan creation and review, and status.

OMYM2 is not a full music-management application. Its shape is:

```text
Headless domain/usecase core + CLI runner + local Web UI for settings, Plan creation and review, and status
```

The main value is not moving files quickly. The value is moving files through a reviewed Plan while keeping enough state and history to diagnose failures and recover safely.

## Basic Policy

This is a product-level summary. Execution rules are authoritative in [execution/](execution/), and storage rules are authoritative in [STORAGE.md](STORAGE.md) plus [contracts/](contracts/).

* Execution is primarily performed from the CLI.
* The Web UI is a local console for settings, Plan creation and review, and status. It does not apply Plans or move files.
* Daily use imports new files with `add` after one Library has been registered.
* Unregistered or unorganized Libraries are accepted through `organize --library PATH` before `add`.
* Tag editing is outside OMYM2; relocation after external tag correction is handled by `refresh`.

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

The daily entry point is `omym2 add`, but only after exactly one Library is registered and selectable.

OMYM2 is not a tool that reorganizes the entire existing library every time. Daily use treats it as a tool for safely importing newly added tracks.

OMYM2 is also not a daily operation tool for arbitrary unorganized music libraries. If the Library is unregistered or unorganized, the supported path is `omym2 organize --library PATH`.

`organize` owns Library registration and reconciliation. `add` owns importing new files after the Library is registered. Detailed registration and add-plan behavior is defined in [execution/organize.md](execution/organize.md) and [execution/add.md](execution/add.md).

Relinking a moved Library is not yet a user-facing operation. Its future identity
rules are defined in [contracts/path-identity-storage.md](contracts/path-identity-storage.md).

## Usage Image

See [COMMANDS.md](COMMANDS.md) for the command sequence behind the primary
Incoming-to-Library flow and periodic maintenance operations.

## Role of the Web UI

The Web UI is a local console for settings, Plan creation and review, and status.
It is not an execution screen: it does not apply Plans or move files.

The roles of the Web UI are:

* Setting optional Library path shortcuts
* Setting the Incoming path
* Editing the path policy
* Generating and editing artist ID path values
* Setting required metadata fields
* Setting behavior for duplicates
* Setting behavior for conflicts
* Validating settings
* Displaying diffs before and after settings changes
* Creating add, organize, and refresh Plans for review
* Browsing and reviewing Plans and their PlanActions
* Reviewing execution history
* Checking the state of the DB and filesystem
* Searching Tracks, Plans, Runs, and persisted Check issues from a global command palette

The Web UI supports settings, Plan creation and review, and read-only Track,
history, and check browsing. Applying Plans and all direct file movement remain
CLI-only.

## Product-Facing Technical Policy

This section is a product-facing summary of technology choices.

Current stack:

```text
Language: Python
DB: SQLite
Config: TOML
Web: FastAPI serving a Next.js (React) static export
CLI: hand-written command dispatch on the standard library (no CLI framework)
Test: pytest + pytest-mock
Coverage: pytest-cov for optional local reporting
E2E: deferred in the initial test policy
Metadata extractor: mutagen
```

The Web UI runs on localhost as a local console for settings, Plan creation and
review, and status. It is served by `omym2 settings`.
