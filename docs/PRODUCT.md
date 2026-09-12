---
type: Product Overview
title: Product
description: Product scope, non-goals, Web UI role, and Windows desktop positioning; read before scope or surface decisions.
tags: [product, overview, cli, web-ui, artist-names, musicbrainz, companions, unprocessed, desktop, windows, operations-console]
timestamp: 2026-07-18T12:00:00+09:00
---

# Product

OMYM2 safely imports local music files into an organized Library through a reviewed Plan, keeping enough state and history to diagnose failures and recover safely. Shape:

```text
Headless domain/usecase core + CLI runner + local Web operations console + thin native window
```

Execution semantics are authoritative in [execution/](execution/); storage rules in [STORAGE.md](STORAGE.md) and [contracts/](contracts/).

## Scope Policy

* CLI and Web are peer inbound surfaces over the same feature usecases, persisted state, and cross-process exclusion protocol. The Web UI is a keyboard-first operations console, not a second implementation of path, conflict, or mutation rules.
* The packaged desktop application is a thin host for the local Web application: no second frontend, native business logic, or direct data-access boundary.
* Primary flow: Incoming → scan → create Plan → review → apply → Library. Daily entry point is `add`, only after exactly one Library is registered. Unregistered or unorganized Libraries go through `organize --library PATH` first. `organize` owns registration and reconciliation ([execution/organize.md](execution/organize.md)); `add` owns importing new files ([execution/add.md](execution/add.md)). OMYM2 is not a whole-library reorganizer or a daily tool for arbitrary unorganized libraries.
* Tag editing is outside OMYM2; relocation after external tag correction is `refresh`.
* No Web control moves a Library-managed audio or companion file directly. Apply is the only Web execution path and executes recorded PlanActions through Run and FileEvent contracts.
* Automatic MusicBrainz naming is enabled by default for uncached names containing non-Latin letters; Latin-only names (including diacritics) stay unchanged; Korean names stay unchanged unless a mapping is added manually. Users can disable new provider work while reusing saved romanized-name mappings. Provider unavailability falls back to local naming and never blocks reviewing or applying recorded local work.
* Companion processing (when enabled): Add, Organize, and Refresh create actions for newly discovered unmanaged `.lrc`, `.jpg`, and `.png` files; Check reports unmanaged companion candidates. Companions remain distinct managed assets with their own actions, history, Check findings, and reversible mutations — never moved as a hidden side effect of an audio action. Disabling stops new actions and Check discovery only: it deletes no managed state, changes no recorded Plan sources or events, and suppresses no managed/recorded Check, recovery, History, or Undo diagnostics.
* Unprocessed-file collection is a separate disabled-by-default Add-planning opt-in. Add settles every audio and companion classification claim (reservation-only claims when companion actions are disabled), then records remaining eligible regular files as reviewed `move_unprocessed` actions into a configured directory below the source root; Apply records each attempt as `move_unprocessed_file` history. No Track or CompanionAsset is created; an occupied destination is never overwritten; disabling later does not alter a recorded Plan, Apply, History, Check, or Undo. Unprocessed-only Add inventory still classifies companion claims so recognized companions are not collected as leftovers (no companion action or snapshot).
* The initial Web release presents one unambiguous Library. All APIs and internal references retain `library_id`; switching and relinking are separate future features (relink identity rules: [contracts/path-identity-storage.md](contracts/path-identity-storage.md)).

## Role of the Web UI

Operating loop: choose objective → create Plan → review actions → Apply → verify → create Undo Plan when eligible.

Surface: Settings (Library path shortcuts, Incoming path, path policy, romanized artist-name mappings, MusicBrainz naming/request bounds/accepted-cache policy, hashing throughput, bounded logging — logging changes require restart, companion toggle, unprocessed toggle plus destination directory and preview cap, artist-ID generation, required metadata, duplicate and conflict behavior, validation, before/after diffs); creating and reviewing add/organize/refresh Plans and PlanActions; applying one ready Plan after a backend-authoritative confirmation; cancelling one ready Plan before Apply claims it; History; Check; creating and reviewing an Undo Plan from an eligible terminal Run; searching Tracks, Plans, Runs, and persisted Check issues.

Backend capabilities and disabled reasons own operation availability. The Web UI never derives permission from a status string, recalculates a target path, repairs a pending FileEvent, overwrites a restore conflict, or automatically retries a mutation. Apply, Cancel, and Undo use the durable Operation, shared lock, atomic Apply claim, crash reconciliation, and mutation contracts together.

## Windows Desktop Application

* v1 supports Windows 11 x64 only; no packaged macOS or Linux claim until each target has its own native build and smoke evidence.
* One pywebview window (`edgechromium` backend, shared Evergreen WebView2 Runtime) hosting the unchanged React application.
* The shell starts the FastAPI application on an exclusively retained, dynamically assigned `127.0.0.1` listener and waits for Bootstrap readiness before opening the window. The React application keeps relative same-origin JSON requests with the existing host, CSRF, CSP, framing, and error-redaction protections. No `js_api` or any JavaScript-to-Python bridge.
* Closing the window requests graceful shutdown; work already accepted as a durable Operation finishes and releases the shared operation lock first. See [ADR 0004](decisions/0004-windows-desktop-application.md).

## Non-Goals

* No music playback, tag editing, lyrics/artwork editing or downloading, or streaming integrations.
* No arbitrary browser-directed file moves or overwrites.
* No cloud sync, accounts, remote binding, analytics, telemetry, or service worker. Localhost-only, offline-first.
* No phone/tablet or touch-first support; desktop browsers only. Accessibility requirements (keyboard operation, zoom, reflow) do not establish mobile support; supported viewport and test conditions: [codebase/web-frontend.md](codebase/web-frontend.md), [development/testing.md](development/testing.md).
* No initial multi-Library switcher, automatic moved-Library relink, Check history, in-flight operation cancellation, or localization.
* Unknown or interrupted mutation state is surfaced for Check and manual review, never hidden behind automatic repair.
* Desktop v1: no macOS, Linux, mobile or tablet OS, bundled Chromium, native file pickers, multiple windows, background startup, automatic updates, or native API bridge.

## Technical Policy

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

* The SPA is bundled in the wheel/sdist, runs without Node.js in production, and is served on loopback by `omym2 settings`. Presentation is dark-only.
* The Windows desktop ZIP is a PyInstaller 6.21.0 `onedir` build from the audited wheel: frozen Python runtime plus the audited SPA, no Node.js or Chromium; Windows supplies the shared Evergreen WebView2 runtime. Packaging and native-smoke commands: [Windows Desktop Packaging](development/desktop-packaging.md).
* Implementation, route map, presentation tokens, distribution contract: [codebase/web-frontend.md](codebase/web-frontend.md). Test policy: [development/testing.md](development/testing.md).
