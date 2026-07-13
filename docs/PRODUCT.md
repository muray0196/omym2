---
type: Product Overview
title: Product
description: Defines OMYM2 as a Plan-centered local music operations core with peer CLI and desktop Web surfaces, including the Web execution boundary and non-goals.
tags: [product, overview, cli, web-ui, operations-console]
timestamp: 2026-07-13T13:24:49+09:00
---

# Product

This document explains what OMYM2 is and is not. Execution semantics live in [execution/](execution/).

## Overview

OMYM2 safely imports local music files into an organized library.

The CLI and local Web UI are peer inbound surfaces over the same Plan-centered
domain and feature usecases. The Web UI is a keyboard-first operations console,
not a separate implementation of path, conflict, or mutation rules.

OMYM2 is not a full music-management application. Its shape is:

```text
Headless domain/usecase core + CLI runner + local Web operations console
```

The main value is not moving files quickly. The value is moving files through a reviewed Plan while keeping enough state and history to diagnose failures and recover safely.

## Basic Policy

This is a product-level summary. Execution rules are authoritative in [execution/](execution/), and storage rules are authoritative in [STORAGE.md](STORAGE.md) plus [contracts/](contracts/).

* CLI and Web operations use the same feature usecases, persisted state, and
  cross-process exclusion protocol.
* The Web UI covers Settings, Plan creation and review, Check, Apply, ready-Plan
  Cancel, History, and Undo-through-Plan.
* No Web control moves a Library music file directly. Apply is the only Web
  execution path, and it executes recorded PlanActions through Run and
  FileEvent contracts.
* Daily use imports new files with `add` after one Library has been registered.
* Unregistered or unorganized Libraries are accepted through `organize --library PATH` before `add`.
* Tag editing is outside OMYM2; relocation after external tag correction is handled by `refresh`.
* The initial Web release presents one unambiguous Library. All APIs and
  internal references retain `library_id`; switching and relinking are separate
  future features.

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

The Web UI makes the safe operating loop available without requiring CLI
knowledge:

```text
choose objective → create Plan → review actions → Apply → verify → create Undo Plan when eligible
```

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
* Applying one ready Plan after a backend-authoritative confirmation
* Cancelling one ready Plan before Apply claims it
* Reviewing execution history
* Checking the state of the DB and filesystem
* Creating an Undo Plan from an eligible terminal Run and reviewing it before Apply
* Searching and navigating Tracks, Plans, Runs, and persisted Check issues

Backend capabilities and disabled reasons own operation availability. The Web
UI never derives permission from a status string, recalculates a target path,
repairs a pending FileEvent, overwrites a restore conflict, or automatically
retries a mutation.

Apply, Cancel, and Undo controls must not be exposed until the durable Operation,
shared lock, atomic Apply claim, crash reconciliation, and mutation E2E gates
are implemented together. Earlier renewal milestones may change Config,
Library registration, Plans, and persisted Check results but must not mutate a
Library music file.

## Product Non-Goals

The Web UI does not add:

* music playback, tag editing, cover-art management, or streaming integrations
* arbitrary browser-directed file moves or overwrites
* cloud sync, accounts, remote binding, analytics, telemetry, or a service worker
* phone or tablet support, touch-first interaction, or mobile-specific
  navigation and layout behavior
* an initial multi-Library switcher, automatic moved-Library relink, Check
  history, in-flight operation cancellation, or localization

The application remains localhost-only, offline-first, and telemetry-free.
Unknown or interrupted mutation state is surfaced for Check and manual review,
never hidden behind automatic repair.

The Web UI supports desktop browsers only. Accessibility requirements such as
keyboard operation, browser zoom, and reflow on a supported desktop viewport
do not establish phone or tablet support. The supported viewport and test
conditions are defined in [codebase/web-frontend.md](codebase/web-frontend.md)
and [TESTING.md](TESTING.md).

## Product-Facing Technical Policy

This section is a product-facing summary of technology choices.

Accepted stack for the renewed Web surface:

```text
Language: Python
DB: SQLite
Config: TOML
Web: FastAPI serving a React + TypeScript + Vite static SPA
CLI: hand-written command dispatch on the standard library (no CLI framework)
Python test: pytest + pytest-mock
Frontend test: Vitest + React Testing Library + MSW
Browser test: Playwright Chromium + axe
Coverage: pytest-cov for optional local reporting
Metadata extractor: mutagen
```

The SPA is bundled in the Python wheel and sdist and runs without Node.js in
production. It is served on loopback by `omym2 settings`. Presentation is
dark-only. The existing persisted `ui.theme` Config field is outside the
renewal's schema scope and is not interpreted by the renewed UI.

The clean-room implementation, route map, presentation tokens, distribution,
and cutover contract are authoritative in
[codebase/web-frontend.md](codebase/web-frontend.md). Test policy is
authoritative in [TESTING.md](TESTING.md).
