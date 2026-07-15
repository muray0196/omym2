---
type: Product Overview
title: Product
description: Defines OMYM2 as a Plan-centered local music application with configurable artist display names across CLI, browser-hosted Web, and supported Windows desktop surfaces, including their execution boundary and non-goals.
tags: [product, overview, cli, web-ui, artist-names, desktop, windows, operations-console]
timestamp: 2026-07-15T20:47:24+09:00
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
Headless domain/usecase core + CLI runner + local Web operations console + thin native window
```

The main value is not moving files quickly. The value is moving files through a reviewed Plan while keeping enough state and history to diagnose failures and recover safely.

## Basic Policy

This is a product-level summary. Execution rules are authoritative in [execution/](execution/), and storage rules are authoritative in [STORAGE.md](STORAGE.md) plus [contracts/](contracts/).

* CLI and Web operations use the same feature usecases, persisted state, and
  cross-process exclusion protocol.
* The packaged desktop application is a thin host for the existing local Web
  application. It adds no second frontend, native business logic, or direct
  data-access boundary.
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
* Editing exact full artist display-name preferences used for planned paths
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

Apply, Cancel, and Undo controls use the durable Operation, shared lock, atomic
Apply claim, crash reconciliation, and mutation contracts together.

## Windows Desktop Application

The packaged desktop v1 supports Windows 11 x64 only. It opens the unchanged
React application in one pywebview window using the `edgechromium` backend and
the shared Evergreen Microsoft Edge WebView2 Runtime. OMYM2 does not claim a
packaged macOS or Linux application until each target has its own native build
and smoke evidence.

The shell starts the existing FastAPI application on an exclusively retained,
dynamically assigned `127.0.0.1` listener and waits for Bootstrap readiness
before opening the window. The React application continues to use relative,
same-origin JSON API requests with the existing host, CSRF, CSP, framing, and
error-redaction protections. The shell does not register `js_api` or any other
JavaScript-to-Python bridge.

Closing the window requests graceful server shutdown. Work already accepted as
a durable Operation is not cancelled; the process allows it to finish and
release the shared operation lock before shutdown completes. The architecture
decision is recorded in
[ADR 0004](decisions/0004-windows-desktop-application.md).

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

The browser-hosted Web UI supports desktop browsers only. Accessibility
requirements such as keyboard operation, browser zoom, and reflow on a
supported desktop viewport do not establish phone or tablet support. The
supported viewport and test conditions are defined in
[codebase/web-frontend.md](codebase/web-frontend.md) and
[development/testing.md](development/testing.md).

The initial packaged application does not support macOS, Linux, mobile or
tablet operating systems, bundled Chromium, native file pickers, multiple
windows, background startup, automatic updates, or a native API bridge.

## Product-Facing Technical Policy

This section is a product-facing summary of technology choices.

Accepted stack for the bundled Web surface:

```text
Language: Python
DB: SQLite
Config: TOML
Web: FastAPI serving a React + TypeScript + Vite static SPA
Desktop: pywebview 6.2.1 using EdgeChromium on Windows 11 x64
CLI: hand-written command dispatch on the standard library (no CLI framework)
Python test: pytest + pytest-mock
Frontend test: Vitest + React Testing Library + MSW
Browser test: Playwright Chromium + axe
Coverage: pytest-cov for optional local reporting
Metadata extractor: mutagen
```

The SPA is bundled in the Python wheel and sdist and runs without Node.js in
production. It is served on loopback by `omym2 settings`. Presentation is
dark-only.

The Windows desktop ZIP is a PyInstaller 6.21.0 `onedir` application built from
the audited wheel. It carries its frozen Python runtime and the same audited SPA
but no Node.js or Chromium runtime; Windows supplies the shared Evergreen
WebView2 runtime. Packaging and native-smoke commands are authoritative in
[Windows Desktop Packaging](development/desktop-packaging.md).

The implementation, route map, presentation tokens, and distribution contract
are authoritative in
[codebase/web-frontend.md](codebase/web-frontend.md). Test policy is
authoritative in [development/testing.md](development/testing.md).
