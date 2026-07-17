---
type: Codebase Reference
title: Web Frontend
description: Bundled React/Vite frontend contract — stack, design tokens, routes, keyboard, API boundary, serving, packaging, performance gates.
tags: [web-frontend, react, vite, static-spa, artist-names, desktop, windows, performance]
timestamp: 2026-07-18T12:00:00+09:00
---

# Web Frontend

Authoritative for the bundled desktop Web frontend: route and layout contract, generated API boundary, static production runtime, Python-package distribution, and performance measurement conditions. JSON protocol: [Web API Contract](../contracts/web-api.md); related decisions: [ADR 0001](../decisions/0001-breaking-bundled-web-api.md), [ADR 0002](../decisions/0002-durable-operations-over-polling.md), [ADR 0003](../decisions/0003-cross-process-exclusive-operation-lock.md), [ADR 0004](../decisions/0004-windows-desktop-application.md). Test categories and fixtures: [Testing](../development/testing.md).

## Current Boundary

There is one frontend under `web/`: no feature flag, parallel tree, compatibility implementation, or screen-by-screen migration path. Previous frontend source, tests, assets, and dependencies define no compatibility surface. Work is evaluated against this document, the Web API and product contracts, the canonical fixtures, and accessibility acceptance tests.

## Stack And Source Layout

React + TypeScript strict; Vite client-side SPA build; React Router with route-level lazy loading; TanStack Query for server state, cursor pages, capabilities, and operation polling; React Hook Form for local Settings drafts; CSS custom properties and CSS Modules; headless accessible primitives styled through local design tokens; one bundled local SVG icon set; a TypeScript client generated from FastAPI OpenAPI.

No general-purpose global server-data store: URL state owns selection and browse state, TanStack Query owns server state, the form layer owns unsaved Settings drafts, component state owns only transient interaction state.

The generated API source is committed and reviewable. Generation starts from the Python Pydantic/OpenAPI schemas; the API drift gate regenerates the client and fails on any difference. Handwritten frontend types must not duplicate request, response, envelope, error, capability, status, or operation schemas owned by OpenAPI. A small handwritten wrapper may attach CSRF and idempotency headers, pass opaque cursors, normalize transport failures, and define query keys without redefining schema fields.

## Dark-Only Design Contract

Dark-only: no light, system, or OLED modes. Core color tokens are fixed:

| Token | Value | Required use |
| --- | --- | --- |
| Canvas | `#07080a` | Full-screen background |
| Surface | `#0d0d0d` | Navigation, list, and card surfaces |
| Surface elevated | `#101111` | Inputs, active controls, and detail sections |
| Surface card | `#121212` | Selected rows, keycaps, and nested panels |
| Hairline | `#242728` | Pane, card, and row dividers |
| Ink | `#f4f4f6` | Primary text |
| Body | `#cdcdcd` | Body text |
| Mute | `#9c9c9d` | Metadata and timestamps |
| Ash | `#6a6b6c` | Disabled and terminal neutral states |
| Primary | `#ffffff` | The sole primary action in one context |
| Blue | `#57c1ff` | Running, pending, and informational state |
| Green | `#59d499` | Succeeded, applied, and registered state |
| Yellow | `#ffc533` | Blocked, stale, and warning state |
| Red | `#ff6161` | Failed and destructive-warning state |

State is never communicated by color alone; status indicators carry visible text or an accessible name. Accent colors are limited to small badges, icons, and status dots. A destructive action stays visually secondary to the single white primary action and uses warning copy, not a solid red CTA.

Corner radii: only `4px`, `6px`, `8px`, `10px`, `16px`. Depth via the surface ladder and one-pixel borders; drop shadows prohibited. Routine cards `16–24px` padding, dense rows `8–12px`, routine section gaps `24–32px`.

Inter is self-hosted with only required weights, no remote font request; the root enables `"calt"`, `"kern"`, `"liga"`, `"ss03"`. Paths, UUIDs, and hashes use a self-hosted monospace font. Font files and licenses ship in `static_dist/licenses/`. Body text starts at `16px`, dense metadata `12–14px`, routine page titles `20–24px`.

Accessibility target: WCAG 2.2 AA — semantic HTML with ARIA only for gaps; visible focus indicator and deterministic focus restoration; keyboard access to every operation and visible control; no single-character shortcut activation from editable elements; `prefers-reduced-motion` handling; complete operation at 200% zoom on a supported desktop viewport; error-summary links that focus the affected field; live-region announcements for operation start/completion/failure; pointer targets ≥ `36px` (touch-first sizing not required).

The red diagonal stripe motif may appear once, only as the top band of the first-run guided state — prohibited from routine Overview, Plan Review, Settings, dialogs, and notifications. Routine screens have one white primary action per context.

Settings uses `Save Settings` as its primary action: one submission performs backend validation and revision-safe atomic replacement; `Review changes` is an optional non-writing secondary action for validation and the before/after diff. A successful save appears as a top floating status notification without moving the form; the returned diff stays in normal page flow. Path preview is recalculated by the backend after a short editing debounce, keeps the last available result while updating, ignores superseded requests, and exposes manual retry only after failure.

## Command And Keyboard Contract

The Command Center opens with `Cmd+K`/`Ctrl+K` and searches recommended actions, commands, recent Plans/Runs, Tracks, and navigation in that order. Every command also has a visible control; shortcut discovery is never required.

| Key | Behavior |
| --- | --- |
| `ArrowUp` / `ArrowDown` | move list selection |
| `Enter` | open the selected detail |
| `Cmd+Enter` / `Ctrl+Enter` | invoke the current primary action |
| `Escape` | close the top dialog/palette or return from detail to list |
| `/` | focus list search |
| `?` | open shortcut help |

Single-character shortcuts are disabled while focus is in an editable element or when they would interfere with assistive-technology navigation. Closing a dialog, completing a mutation, and changing route restore focus to a declared target, never the document body.

All user-facing copy starts in English and is centralized by feature rather than embedded across render branches — a maintainability boundary, not a localization framework; translated catalogs and locale selection stay out of scope until a later evidence-driven decision.

## Route Map

Health is the UI surface name; Check is the backend operation and persisted result.

| Route | Purpose | Primary action |
| --- | --- | --- |
| `/` | Readiness, ready Plans, latest Check, and most recent Run | Add music |
| `/plans` | Plan list with status and type filters | Create Plan |
| `/plans/new/add` | Add Plan creation | Scan and create Plan |
| `/plans/new/organize` | Library registration or reconciliation Plan creation | Scan Library |
| `/plans/new/refresh` | File, directory, or all-target Refresh Plan creation | Create Refresh Plan |
| `/plans/:planId` | Plan header, summary, actions with recorded artist-name diagnostics, groups, Apply, and Cancel | Apply Plan |
| `/library` | Track search, status filtering, and artist/album grouping | Refresh path |
| `/library/:trackId` | Track metadata, paths, hashes, and history links | Refresh Track |
| `/health` | Latest persisted Check issues, facets, groups, and timestamp | Run Check |
| `/history` | Run list with status filtering | None |
| `/history/:runId` | Run, FileEvents, failures, and Undo eligibility | Create Undo Plan |
| `/settings` | Paths, PathPolicy, editable romanized artist mappings, automatic artist-ID tunables, metadata, and collision policy | Save directly; review Config changes optionally |

Every unmatched browser route renders the React Not Found screen (no server-side route allowlist or API response). Path fields use text input plus backend validation and preview; no browser/native directory picker — a native picker requires a separate architecture and security decision.

## URL And Desktop Layout Behavior

The URL is authoritative for selected entity, search query, filters, grouping, sorting, and detail state; reloading or sharing a URL restores it. Changing a browse filter updates the URL and query key together and resets the cursor.

The supported surface is a desktop browser viewport ≥ `1024px`. Phones, tablets, touch-first interaction, and sub-`1024px` layouts are not product requirements or test targets; responsive rules preserving window resizing, zoom, or AT access do not establish mobile support.

At ≥ `1280px` the shell may show a navigation rail, a `320–420px` list pane, and one detail pane (max three regions side by side). From `1024–1279px`, navigation may be compact and the route shows list or detail. List screens use one compact page-header block plus a filter toolbar (one row when space permits, max two rows at `1024px`). Dense rows use stable columns, right-align comparable numeric/date values with tabular numerals, and fall back to labeled stacked content only under zoom/resize. Counts use locale-aware formatting; pagination shows "Page N of M" when the endpoint supplies a total. The connected-service strip stays a slim single line; degraded/disconnected guidance keeps its expanded alert treatment.

Library browsing uses one full-width result surface: Tracks default, group browsing as an alternate URL-owned view returning to the Track list with the group applied. Default rows prioritize title, artist, album, year, location, status; internal Track IDs live in Track detail, not a primary list column. The list-detail surface stays keyboard-operable; detail selection is route state, not a modal-only state. Primary operations stay reachable without horizontal page scrolling; a dense data region may scroll internally.

## Backend-Authoritative Behavior

The frontend communicates only through the JSON API — never reading TOML, SQLite, the application root, or Library files, and never reimplementing PathPolicy, identity selection, duplicate detection, conflict judgment, precondition checks, or Undo eligibility.

The backend returns operation `capabilities` and structured `disabled_reasons`; the frontend must not infer permitted transitions from entity status. Displayed capabilities are revalidated by the backend on mutation acceptance. Closed catalog labels are exhaustive and fail explicitly when a mapping is missing; raw-value fallback only for explicitly open fields such as `FileEvent.error_code` ([status presentation contract](../contracts/status-reason-catalog.md#status-presentation-contract)).

Cursors are opaque: pass `next_cursor` unchanged, never parse or derive meaning. Full UUIDs are authoritative; display may abbreviate but copy and API operations use the full value.

Every state-changing request carries the Bootstrap CSRF token; requests starting durable operations also carry a client-generated `Idempotency-Key` and follow the durable polling decision. The frontend does not automatically retry mutations after network/5xx failures and does not retry 4xx validation or conflict responses; any explicitly safe CSRF refresh-and-resend behavior is defined by the Web API contract.

## Development Runtime

The Python server binds `127.0.0.1:8765`; Vite uses a development-only port and proxies `/api` to that loopback server, preserving the production same-origin boundary. CORS must not be enabled. Development/test profiles may admit the Vite proxy host and TestClient's `testserver`; production host validation admits only `127.0.0.1` and `localhost`.

## Production Serving

The production process is Python-only and binds loopback. Node.js, a CDN, remote fonts, analytics, telemetry, and a service worker are prohibited at runtime.

Requests are classified before SPA fallback:

1. Every `/api` request is handled as JSON; unknown API routes return the typed JSON 404 envelope, never HTML.
2. `/assets/*` serves only packaged content-hashed assets; a missing asset returns 404, never `index.html`.
3. Any other `GET` whose `Accept` contains `text/html` returns `index.html` with 200; React Router owns the matched screen or Not Found.
4. A missing or non-HTML `Accept` (including `*/*`) returns 404.
5. Non-`GET` UI requests return 405. Dotfiles and path traversal are rejected with 404 before filesystem lookup or SPA fallback.

If the packaged build is missing, UI routes return 503 while the JSON API stays operational.

### Native Windows Host

The Windows 11 x64 desktop application displays this same production surface in one pywebview EdgeChromium window: no forked React tree, no changed router or generated client, no native navigation chrome, no pywebview `js_api`. Path entry stays an ordinary Web form. The desktop process passes the FastAPI app to Uvicorn through an exclusively retained socket bound to dynamic port `0` on `127.0.0.1`; the same socket stays owned through startup (no release-and-rebind race). The window is created only after `/api/bootstrap` proves readiness and navigates to the same-origin loopback URL. Production HTTP protections are unchanged.

`index.html` and HTML fallback use `Cache-Control: no-cache`; content-hashed assets use `Cache-Control: public, max-age=31536000, immutable`; no unhashed file gets immutable caching.

Every response applies the security baseline: allowed-host enforcement; CSP with `default-src 'self'`, `script-src 'self'`, no inline script or `unsafe-eval`, no remote source, `object-src 'none'`, `base-uri 'none'`, `frame-ancestors 'none'`; `X-Content-Type-Options: nosniff`; `Referrer-Policy: no-referrer`; framing prohibition; redacted unexpected errors with correlation IDs (no raw exception or stack trace in the browser). Inline style permission stays absent unless a required accessible or virtualized primitive proves it cannot operate without a narrowly scoped `style-src-attr` allowance; such an allowance must not permit remote styles or inline scripts.

## Build And Distribution

Vite writes the staged build to `web/dist/`. The packaging sync performs a complete replacement of `src/omym2/adapters/web/static_dist/`; it never overlays stale output, and the generated directory is never hand-edited.

The export audit requires: `index.html` and all referenced hashed assets; package-relative asset references; no source maps, analytics, remote runtime URLs, unexpected inline scripts, secrets, logs, databases, or server-only artifacts; self-hosted fonts and licenses under `static_dist/licenses/`.

Wheel and sdist include the complete audited `static_dist/`. A clean environment must build the wheel from the sdist without Node.js (the sdist carries the built frontend). Clean-install smoke tests retrieve `/`, a deep route, one hashed asset, and `/api/bootstrap` from the installed package. Build inclusion is configured through `pyproject.toml` package data; add a `MANIFEST.in` only if an audited sdist build proves the build backend cannot satisfy this contract. The Windows native ZIP freezes this same audited wheel rather than rebuilding the frontend; its build and smoke contract: [Windows Desktop Packaging](../development/desktop-packaging.md).

## Performance Contract

All feature routes are lazy-loaded; the initial app shell must not eagerly load feature code unnecessary for `/`. Cursor endpoints request batches of 100 by default and never retrieve an unbounded result set. Each collection renders one cursor page at a time with Previous/Next; cached pages remain available without accumulating rows in the DOM.

`npm run test:performance` is the authoritative frontend performance command. It measures an installed production package (not a Vite dev server) through `/` on loopback under fixed conditions: Playwright and its Chromium revision pinned by the frontend lockfile; CI on an `ubuntu-24.04` hosted runner recording runner image, CPU model, logical CPU count, and memory; the app shell sets `data-omym2-shell-interactive="true"` only after navigation and Command Center handlers are operable (ends interactive-shell timing); the cold series uses a fresh browser context per run with cache disabled; the warm series reuses one context with HTTP cache enabled; each series performs one unreported warm-up and reports the median of five measured runs.

The initial-route JavaScript budget is the sum of JavaScript resources loaded by `/` before the interactive marker, each compressed with `gzip -9 -n -c` for deterministic byte counts; lazy chunks not requested by `/` are excluded. Budgets: median interactive-shell ≤ `1000ms`; initial-route JavaScript ≤ `250000` gzipped bytes. Any budget change must update this contract with measurement evidence and rationale.
