---
type: Codebase Reference
title: Web Frontend
description: Defines the bundled desktop React and Vite Web frontend contract, including routes, artist-name settings and Plan diagnostics, design rules, API boundaries, browser and native-window serving, packaging, security, and performance gates.
tags: [web-frontend, react, vite, static-spa, artist-names, desktop, windows, performance]
timestamp: 2026-07-17T20:30:51+09:00
---

# Web Frontend

This document is authoritative for the bundled desktop Web frontend, its
route and layout contract, its generated API boundary, its static production
runtime, its Python-package distribution, and its performance measurement
conditions.

The JSON protocol is authoritative in the [Web API Contract](../contracts/web-api.md).
The API compatibility decision is recorded in
[Breaking Web API Without A Version Prefix](../decisions/0001-breaking-bundled-web-api.md),
durable transport in
[Durable Operations Over Polling](../decisions/0002-durable-operations-over-polling.md),
and exclusive coordination in
[Cross-Process Exclusive Operation Lock](../decisions/0003-cross-process-exclusive-operation-lock.md).
The native Windows host is recorded in
[ADR 0004](../decisions/0004-windows-desktop-application.md).
Test categories and fixture policy are authoritative in [Testing](../development/testing.md).

## Current Boundary

There is one frontend under `web/`: no feature flag, parallel tree,
compatibility implementation, or screen-by-screen migration path is allowed.
Previous frontend source, tests, assets, and dependencies do not define a
compatibility surface. Current work is evaluated against this document, the
Web API and product contracts, the canonical fixtures, and accessibility
acceptance tests.

## Stack And Source Layout

The frontend uses:

* React with TypeScript strict mode
* Vite as a client-side SPA build
* React Router with route-level lazy loading
* TanStack Query for server state, cursor pages, capabilities, and operation polling
* React Hook Form for local Settings drafts
* CSS custom properties and CSS Modules
* headless accessible primitives styled through the local design tokens
* one bundled local SVG icon set
* a TypeScript client generated from FastAPI OpenAPI

The frontend does not introduce a general-purpose global server-data store.
URL state owns selection and browse state, TanStack Query owns server state,
the form layer owns unsaved Settings drafts, and component state owns only
transient interaction state.

The generated API source is committed and reviewable. Generation starts from
the Python Pydantic/OpenAPI schemas, and the API drift gate regenerates the
client and fails on any difference. Handwritten frontend types must not
duplicate request, response, envelope, error, capability, status, or operation
schemas owned by OpenAPI. A small handwritten wrapper may attach CSRF and
idempotency headers, pass opaque cursors, normalize transport failures, and
define query keys without redefining schema fields.

## Dark-Only Design Contract

The frontend is dark-only. It must not implement light, system, or OLED
rendering modes.

Core color tokens are fixed as follows:

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

State must never be communicated through color alone. Status indicators carry
visible text or an accessible name. Accent colors are limited to small badges,
icons, and status dots. A destructive action remains visually secondary to the
single white primary action and uses warning copy rather than a solid red CTA.

Only `4px`, `6px`, `8px`, `10px`, and `16px` corner radii are allowed. Depth is
expressed through the surface ladder and one-pixel borders; drop shadows are
prohibited. Routine cards use `16px` to `24px` padding, dense rows use `8px` to
`12px`, and routine section gaps use `24px` to `32px`.

Inter is self-hosted with only the required weights and no remote font request;
the root enables `"calt"`, `"kern"`, `"liga"`, and `"ss03"` font features.
Paths, UUIDs, and hashes use a self-hosted monospace font. Font files and
licenses ship in `static_dist/licenses/`. Body text starts at `16px`, dense
metadata at `12px` to `14px`, and routine page titles at `20px` to `24px`.

The accessibility target is WCAG 2.2 AA. The implementation must provide:

* semantic HTML, with ARIA used only to fill semantic gaps
* a visible focus indicator and deterministic focus restoration
* keyboard access to every operation and visible control
* no single-character shortcut activation from editable elements
* `prefers-reduced-motion` handling for pulses and transitions
* complete operation at 200% zoom on a supported desktop viewport
* error-summary links that focus the affected field
* live-region announcements for operation start, completion, and failure
* pointer targets of at least `36px`; touch-first sizing is not required

The red diagonal stripe motif may appear once, only as the top band of the
first-run guided state. It is prohibited from routine Overview, Plan Review,
Settings, dialogs, and notifications. Routine screens have one white primary
action per context; risk is communicated with text, icons, and small status
accents rather than a second competing primary treatment.

Settings uses `Save Settings` as its primary action. One submission performs
backend validation and revision-safe atomic replacement; `Review changes` is
an optional, non-writing secondary action for inspecting validation and the
before/after diff. A successful save appears as a top floating status
notification without moving the form, while the returned diff remains in the
normal page flow. Path preview is recalculated by the backend after a short
editing debounce, keeps the last available result while updating, ignores
superseded requests, and exposes a manual retry only after failure.

## Command And Keyboard Contract

The Command Center opens with `Cmd+K` or `Ctrl+K` and searches recommended
actions, commands, recent Plans/Runs, Tracks, and navigation in that order.
Every command also has a visible control; shortcut discovery is never required
to operate the application.

Context-independent shortcuts are:

| Key | Behavior |
| --- | --- |
| `ArrowUp` / `ArrowDown` | move list selection |
| `Enter` | open the selected detail |
| `Cmd+Enter` / `Ctrl+Enter` | invoke the current primary action |
| `Escape` | close the top dialog/palette or return from detail to list |
| `/` | focus list search |
| `?` | open shortcut help |

Single-character shortcuts are disabled while focus is in an editable element
or when they would interfere with assistive-technology navigation. Closing a
dialog, completing a mutation, and changing route restore focus to a declared
target rather than to the document body.

All user-facing copy starts in English, the product's default language, and is
centralized by feature rather than embedded across render branches. This is a
maintainability boundary, not a localization framework; translated catalogs and
locale selection remain out of scope until a later evidence-driven decision.

## Route Map

Health is the UI surface name; Check is the backend operation and persisted
result.

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

Every unmatched browser route renders the React Not Found screen. It
does not trigger a server-side route allowlist or return an API response.

Path fields use text input plus backend validation and preview. The initial Web
surface does not add a browser/native directory picker or infer a path from
browser file handles. A native picker requires a separate architecture and
security decision.

## URL And Desktop Layout Behavior

The URL is authoritative for the selected entity, search query, filters,
grouping, sorting, and detail state. Reloading or sharing a URL must restore
that state. Changing a browse filter updates the URL and query key together and
resets the cursor.

The supported Web surface is a desktop browser viewport at least `1024px`
wide. Phone and tablet browsers, touch-first interaction, mobile-specific
navigation, and layouts below `1024px` are not product requirements or test
targets. Responsive rules used to preserve desktop window resizing, browser
zoom, or assistive-technology access do not establish mobile support.

At widths of at least `1280px`, the shell may show a navigation rail, a
`320px` to `420px` list pane, and one detail pane. No more than three regions
may appear side by side. From `1024px` through `1279px`, navigation may be
compact and the route may show either the list or detail view.

List screens use one compact page-header block followed by a filter toolbar
that stays on one row when space permits and no more than two rows at `1024px`.
Dense result rows use stable columns, right-align comparable numeric and date
values with tabular numerals, and fall back to labeled stacked content only
when zoom or window resizing requires it. Counts use locale-aware formatting,
and pagination shows “Page N of M” whenever the endpoint supplies a total.
The normal connected-service strip remains a slim single line; degraded and
disconnected guidance keeps its expanded alert treatment.

Library browsing uses one full-width result surface. Tracks are the default
view; group browsing is an alternate URL-owned view, and selecting a group
returns to the Track list with that group applied. The default Track rows
prioritize title, artist, album, year, location, and status. Internal Track IDs
remain available in Track detail instead of occupying a primary list column.

The list-detail surface remains keyboard-operable throughout the supported
desktop range. Detail
selection is a route state, not an unaddressable modal-only state. Primary
operations remain reachable without horizontal page scrolling at supported
desktop widths; a dense data region may use explicit internal scrolling.

## Backend-Authoritative Behavior

The frontend communicates only through the JSON API. It never reads TOML,
SQLite, the application root, or Library files directly, and it never
reimplements PathPolicy, identity selection, duplicate detection, conflict
judgment, precondition checks, or Undo eligibility.

The backend returns operation `capabilities` and structured
`disabled_reasons`. The frontend must not infer permitted state transitions or
mutations from entity status. Displayed capabilities are revalidated by the
backend when a mutation is accepted.

Closed catalog labels are exhaustive and fail explicitly when a mapping is
missing. Raw-value fallback is permitted only for fields whose contract is
explicitly open, such as `FileEvent.error_code`; the details are authoritative
in the [status presentation contract](../contracts/status-reason-catalog.md#status-presentation-contract).

Cursors are opaque. The frontend passes `next_cursor` unchanged and never
parses, constructs, or derives meaning from it. Full UUIDs are authoritative;
the display may abbreviate an ID, but copy and API operations use the full
value.

Every state-changing request carries the Bootstrap CSRF token. Requests that
start durable operations also carry a client-generated `Idempotency-Key` and
follow the durable polling decision. The frontend does not automatically retry
mutations after a network or 5xx failure, and it does not retry 4xx validation
or conflict responses. Any explicitly safe CSRF refresh-and-resend behavior is
defined by the Web API contract.

## Development Runtime

The Python server binds to `127.0.0.1:8765`. Vite uses a development-only port
and proxies `/api` to that loopback server. Browser requests therefore preserve
the production same-origin boundary. CORS must not be enabled.

Development and test profiles may admit the Vite proxy host and TestClient's
`testserver`; production host validation admits only `127.0.0.1` and
`localhost`.

## Production Serving

The production process is Python-only and binds to loopback. Node.js, a CDN,
remote fonts, analytics, telemetry, and a service worker are prohibited at
runtime.

Requests are classified before SPA fallback:

1. Every `/api` request is handled as JSON. Unknown API routes return the typed
   JSON 404 envelope and never return HTML.
2. `/assets/*` serves only packaged, content-hashed assets. A missing asset
   returns 404 and never falls back to `index.html`.
3. Any other `GET` whose `Accept` header contains `text/html` returns
   `index.html` with status 200; React Router owns the matched screen or Not
   Found result.
4. A missing or non-HTML `Accept` value, including `*/*`, does not qualify for
   fallback and returns 404.
5. Non-`GET` UI requests return 405. Dotfile requests and path traversal are
   rejected with 404 before filesystem lookup or SPA fallback.

If the packaged build is missing, UI routes return 503 while the JSON API
remains operational.

### Native Windows Host

The Windows 11 x64 desktop application displays this same production surface
inside one pywebview EdgeChromium window. It does not fork the React tree,
change React Router or the generated client, add native navigation chrome, or
register a pywebview `js_api` object. Path entry remains an ordinary Web form;
a native picker is outside this boundary.

The desktop process passes the existing FastAPI application to Uvicorn through
an exclusively retained socket bound to dynamic port `0` on `127.0.0.1`. The
same socket remains owned through server startup, so no release-and-rebind port
race exists. The native window is created only after `/api/bootstrap` proves
the server ready, and it navigates to the resulting same-origin loopback URL.
The production HTTP protections in this section remain unchanged.

`index.html` and HTML fallback responses use `Cache-Control: no-cache`.
Content-hashed assets use
`Cache-Control: public, max-age=31536000, immutable`. No unhashed file receives
immutable caching.

Every response applies the security baseline:

* allowed-host enforcement
* `Content-Security-Policy` with `default-src 'self'`, `script-src 'self'`, no
  inline script or `unsafe-eval`, no remote source, `object-src 'none'`,
  `base-uri 'none'`, and `frame-ancestors 'none'`
* `X-Content-Type-Options: nosniff`
* `Referrer-Policy: no-referrer`
* framing prohibition
* redacted unexpected errors with correlation IDs; no raw exception or stack
  trace in the browser response

Inline style permission must remain absent unless a required accessible or
virtualized primitive proves it cannot operate without a narrowly scoped
`style-src-attr` allowance. Such an allowance must not permit remote styles or
inline scripts.

## Build And Distribution

Vite writes the staged build to `web/dist/`. The packaging sync performs a
complete replacement of
`src/omym2/adapters/web/static_dist/`; it never overlays stale output and the
generated directory is never hand-edited.

The export audit requires:

* `index.html` and all referenced hashed assets
* package-relative asset references
* no source maps, analytics, remote runtime URLs, unexpected inline scripts,
  secrets, logs, databases, or server-only artifacts
* self-hosted font files and licenses under `static_dist/licenses/`

Both the wheel and sdist include the complete audited `static_dist/`. A clean
environment must be able to build the wheel from the sdist without Node.js;
the sdist therefore carries the already-built frontend rather than requiring a
frontend build. Clean-install smoke tests retrieve `/`, a deep route, one
hashed asset, and `/api/bootstrap` from the installed package.

Python build inclusion is configured through `pyproject.toml` package data.
The build does not assume or require a separate `MANIFEST.in`; add one only
if an audited sdist build proves the existing build backend cannot satisfy this
contract.

The Windows native ZIP freezes this same audited wheel rather than rebuilding
the frontend or reading a source checkout. Its build and smoke contract is in
[Windows Desktop Packaging](../development/desktop-packaging.md).

## Performance Contract

All feature routes are lazy-loaded. The initial app shell must not eagerly load
feature code that is unnecessary for `/`. Cursor endpoints request batches of
100 items by default and must never retrieve an unbounded result set. Each
collection renders one cursor page at a time with Previous/Next controls;
cached pages remain available without accumulating their rows in the DOM.

`npm run test:performance` is the authoritative frontend performance command.
It measures an installed production package, not a Vite development server,
through `/` on a loopback address under these fixed conditions:

* the Playwright version and its Chromium revision are pinned by the frontend lockfile
* CI uses an `ubuntu-24.04` hosted runner and records the runner image, CPU model,
  logical CPU count, and available memory with the result
* the app shell sets `data-omym2-shell-interactive="true"` only after its
  navigation and Command Center handlers are operable; this marker ends the
  interactive-shell timing
* the cold series creates a fresh browser context for each run and disables the
  browser cache
* the warm series reuses one context with the HTTP cache enabled and repeats
  navigation after the initial load
* each series performs one unreported warm-up and reports the median of five
  measured runs

The initial-route JavaScript budget is the sum of JavaScript resources loaded
by `/` before the interactive marker. Each unique resource is compressed with
`gzip -9 -n -c` so maximum compression and suppressed gzip metadata make the
byte count deterministic; lazy feature chunks not requested by `/` are not
included.

The median interactive-shell time must not exceed `1000ms`, and initial-route
JavaScript must not exceed `250000` gzipped bytes. Any budget change must update
this contract with the measurement evidence and rationale.
