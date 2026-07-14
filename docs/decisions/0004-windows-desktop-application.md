---
type: Architecture Decision Record
title: "ADR 0004: Package a Thin Windows Desktop Application"
description: Records the Windows-only native desktop shell, retained loopback server, EdgeChromium boundary, stable data root, shutdown semantics, and audited onedir packaging decision.
tags: [adr, desktop, windows, pywebview, pyinstaller]
timestamp: 2026-07-15T00:13:25+09:00
---

# ADR 0004: Package a Thin Windows Desktop Application

## Status

Accepted.

## Context

OMYM2 already ships one React/Vite SPA with a local FastAPI API. A desktop
application should remove manual browser and server startup without creating a
second frontend, a native reimplementation, or a privileged path around the
existing API and operation-safety contracts.

Desktop WebView and package behavior is platform-specific. Claiming generic
desktop support before producing and exercising a native artifact would hide
renderer, filesystem, process-lifecycle, and signing differences.

## Decision

Desktop v1 supports Windows 11 x64 only. One process composes the existing
FastAPI application, starts Uvicorn with an exclusively retained socket bound
to dynamic port `0` on `127.0.0.1`, waits for a valid Bootstrap response, and
then opens the existing SPA in one pywebview window. Retaining the listener
through server startup removes the release-and-rebind port race.

pywebview is pinned to 6.2.1 and explicitly selects `edgechromium`. It uses the
shared Evergreen Microsoft Edge WebView2 Runtime rather than carrying a fixed
WebView2 or Chromium distribution. The package and smoke workflow checks this
prerequisite. The desktop adapter registers no `js_api`, native file picker, or
other JavaScript-to-Python bridge; relative same-origin HTTP remains the only UI
boundary.

The desktop application root is `%LOCALAPPDATA%\OMYM2`, independent of the
executable and current working directory. The CLI remains rooted in its current
working directory. Exact mutable paths and archive replacement/removal
behavior are authoritative in
[Storage](../STORAGE.md#application-root-selection).

Closing the native window requests graceful Uvicorn shutdown and waits for the
server thread and application lifespan to close. It does not cancel a queued or
running durable Operation. Work already accepted is allowed to finish and
release the shared exclusive-operation lock before the process exits, as
defined by the [Operations contract](../contracts/operations.md#cancellation).

Windows artifacts use PyInstaller 6.21.0 `onedir` packaging from an audited
wheel, followed by a deterministic ZIP. The package includes the frozen Python
runtime, audited static SPA, SQLite migrations, pywebview support, icon, and
version metadata. It does not require separate Python or Node.js installations
and does not bundle Chromium. The build is native; OMYM2 does not cross-build
Windows artifacts or claim macOS/Linux packages.

Locally generated ZIPs remain unsigned development builds. CI builds and
smoke-tests its ZIP ephemerally, retains only native evidence and checksums, and
does not publish the package while redistribution is unresolved. A signed
public release requires the licensing and signing gates defined in
[Windows Desktop Packaging](../development/desktop-packaging.md#release-gates);
CI success alone does not make a locally generated ZIP a redistributable
release.

## Consequences

* The desktop UI, API schemas, security middleware, feature usecases, and
  operation semantics stay shared with the browser-hosted application.
* Windows supplies and services the shared Evergreen WebView2 Runtime; a
  missing prerequisite is a startup failure, not a reason to fall back to a
  bundled browser engine.
* The server remains loopback-only and dynamic without exposing a LAN listener
  or a port-selection race.
* Closing the window may wait while accepted mutation work finishes; preserving
  its durable safety boundary takes precedence over forced process exit.
* Updating or removing extracted application files leaves desktop Config,
  SQLite state, and logs under `%LOCALAPPDATA%\OMYM2` intact.
* macOS or Linux support requires a separate native target, dependency policy,
  package format, smoke evidence, and architecture decision.
