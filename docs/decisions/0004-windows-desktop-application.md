---
type: Architecture Decision Record
title: "ADR 0004: Package a Thin Windows Desktop Application"
description: The Windows-only pywebview desktop shell, loopback server, stable data root, shutdown semantics, and audited onedir packaging.
tags: [adr, desktop, windows, pywebview, pyinstaller]
timestamp: 2026-07-18T12:00:00+09:00
---

# ADR 0004: Package a Thin Windows Desktop Application

## Status

Accepted.

## Context

OMYM2 ships one React/Vite SPA with a local FastAPI API. The desktop application removes manual browser/server startup without creating a second frontend, a native reimplementation, or a privileged path around the API and operation-safety contracts. Desktop WebView and package behavior is platform-specific, so support is claimed only for a produced and exercised native artifact.

## Decision

* Desktop v1 supports Windows 11 x64 only. One process composes the existing FastAPI app, starts Uvicorn with an exclusively retained socket bound to dynamic port `0` on `127.0.0.1` (retaining the listener removes the release-and-rebind port race), waits for a valid Bootstrap response, then opens the SPA in one pywebview window.
* pywebview is pinned to 6.2.1 with explicit `edgechromium`, using the shared Evergreen Microsoft Edge WebView2 Runtime (checked as a prerequisite) rather than a bundled engine. No `js_api`, native file picker, or JS-to-Python bridge — relative same-origin HTTP is the only UI boundary.
* Desktop application root: `%LOCALAPPDATA%\OMYM2`, independent of the executable and CWD; the CLI stays CWD-rooted. Mutable paths and archive replacement/removal behavior: [Storage](../STORAGE.md#application-root-selection).
* Closing the window requests graceful Uvicorn shutdown and waits for the server thread and lifespan to close. It does not cancel a queued or running durable Operation; accepted work finishes and releases the shared exclusive lock before exit ([Operations contract](../contracts/operations.md#cancellation)).
* Windows artifacts use PyInstaller 6.21.0 `onedir` packaging from an audited wheel, then a deterministic ZIP containing the frozen Python runtime, audited static SPA, SQLite migrations, pywebview support, icon, and version metadata — no separate Python/Node installs, no bundled Chromium, native build only (no cross-builds, no macOS/Linux claims).
* Locally generated ZIPs are unsigned development builds. CI builds and smoke-tests its ZIP ephemerally, retains only native evidence and checksums, and does not publish while redistribution is unresolved. A signed public release requires the gates in [Windows Desktop Packaging](../development/desktop-packaging.md#release-gates); CI success alone does not make a local ZIP redistributable.

## Consequences

* Desktop UI, API schemas, security middleware, usecases, and operation semantics stay shared with the browser-hosted application.
* Windows supplies and services the shared WebView2 Runtime; a missing prerequisite is a startup failure, never a fallback to a bundled engine.
* The server remains loopback-only and dynamic; closing the window may wait while accepted mutation work finishes.
* Updating or removing extracted application files leaves desktop Config, SQLite state, and logs under `%LOCALAPPDATA%\OMYM2` intact.
* macOS or Linux support requires a separate native target, dependency policy, package format, smoke evidence, and architecture decision.
