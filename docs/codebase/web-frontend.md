---
type: Codebase Reference
title: Web Frontend
description: Authoritative reference for the Next.js web/ frontend layout, its audited static export build and packaging pipeline into the Python package, and the JSON API boundary between frontend and backend.
tags: [web-frontend, nextjs, static-export, api-boundary]
timestamp: 2026-07-12T22:30:28+09:00
---

# Web Frontend

This document is authoritative for the `web/` frontend layout, the audited static export build and packaging pipeline, and the boundary between the frontend and the Python backend.

Backend adapter rules are in [dependency-boundaries.md](dependency-boundaries.md). Frontend quality commands are in [../DEVELOPMENT.md](../DEVELOPMENT.md).

## Stack

The Web UI is a Next.js App Router project (`web/`) using React, TypeScript, and Tailwind CSS. It is built as a static export (`output: "export"` in `web/next.config.mjs`); no Node server runs in production.

The app is a single-page console: `web/app/page.tsx` renders the `Console` component, and screen switching happens client-side inside `components/omym2/`.

The persistent shell includes a global command palette opened through its
header trigger or `Ctrl`/`Cmd`+`K`. Static commands cover screen navigation and
copyable CLI operations. Non-blank input is debounced and searches the paged
Track, Plan, Run, and persisted Check issue APIs in parallel; result rows link
to the corresponding detail or filtered browse screen. A failed source does
not discard successful results from the other sources.

The Settings editor separates routine controls from safety-sensitive and
advanced controls. Paths, metadata and artist IDs, and appearance remain in the
General settings area. The persisted `ui.show_advanced_settings` value exposes
a distinct Advanced controls area for automation defaults, path construction,
and collision or missing-data policies. Hiding the advanced area changes only
editor visibility; it does not reset those persisted values. Both areas use the
same validation, diff, and save flow, and neither adds a Web apply path.

## Layout

```text
web/
  app/                  # App Router entry: layout.tsx, page.tsx, globals.css
  components/
    omym2/              # console shell, app context, API client, forms, widgets
      screens/          # check, dashboard, path-policy, plan-detail, plans, run-detail, runs, settings, tracks
  lib/                  # utils.ts helpers
  public/               # icons and static assets copied into the export
  scripts/              # audit-static-export.mjs, sync-static-export.mjs
  next.config.mjs       # static export configuration
  package.json
```

`web/out/` is the generated Next export output and is not hand-edited.
`src/omym2/adapters/web/static_dist/` is the generated Python-package copy of
that export and is not hand-edited or committed.

## Build And Packaging Pipeline

`npm run build` in `web/` runs these steps (`web/package.json`):

1. `next build` produces the static export in `web/out/`. `web/next.config.mjs` pins the build id to `omym2-static` so generated exports stay reproducible, and disables image optimization.
2. `node scripts/sync-static-export.mjs` audits `web/out/`, replaces `src/omym2/adapters/web/static_dist/` with a copy of `web/out/`, then audits the packaged copy.

The audit rejects common secret, debug, server-only, and analytics artifacts such as source maps, environment files, key material, database files, logs, Next server manifests, build traces, and Vercel Analytics code. The Web UI is a local console and must not include third-party analytics.

The export is packaged inside the Python package so `omym2 settings` can serve the current Web UI without a Node runtime:

* `omym2 settings` (`src/omym2/adapters/cli/commands/settings.py`) calls an injected `SettingsCommandPorts.web_app_factory` to obtain the FastAPI app and serves it locally with uvicorn; it does not build the app itself.
* `src/omym2/platform/web_composition.py::build_web_app` is that factory: it builds the Web UI's `ApiRouteContext` (config store, feature ports factories, CSRF token, artist-id language detector and name resolver) via `build_api_route_context`, then calls `src/omym2/adapters/web/app.py::create_web_app(context, static_dist_path)`.
* `src/omym2/adapters/web/app.py::create_web_app` takes that pre-built `ApiRouteContext` and only assembles routes and static assets: it mounts `_next/static` assets, returns `index.html` for the known UI routes (`/`, `/settings`, `/path-policy`, `/plans`, `/plans/{plan_id}`, `/history`, `/history/{run_id}`, `/check`, `/tracks`), serves remaining root-level export files, and answers 503 when the export is missing. It does not construct outbound adapters itself.

After changing the frontend, run the build so the ignored local `static_dist/`
copy matches the source before runtime or package verification. Do not commit
`static_dist/`; package builds include it from the generated local copy.

## Frontend / Backend Boundary

The JSON envelope, pagination/cursor, facet, and group-by contract for the browsing endpoints (`/api/tracks`, `/api/plans`, `/api/check`, `/api/history`) is authoritative in [../contracts/web-api.md](../contracts/web-api.md).

The frontend talks to the backend only through the JSON API:

* `web/components/omym2/api-client.ts` calls the Settings endpoints (`/api/settings`, `/api/settings/validate`, `/api/settings/preview`, `/api/settings/save`, `/api/settings/artist-ids/generate`) and the browsing endpoints documented in [../contracts/web-api.md](../contracts/web-api.md), including paged list, search, facet, group, and detail routes under `/api/tracks`, `/api/plans`, `/api/check`, and `/api/history`. Settings saves, artist ID generation, Plan creation POSTs, and Check recomputation (`POST /api/check/run`) send the CSRF token in the `X-OMYM2-CSRF-Token` header.
* `src/omym2/adapters/web/routes/api.py` translates JSON payloads into feature usecases (settings load / validate / preview / save, Plan list / detail / creation, history, check, tracks). Routes never read TOML or the filesystem directly; config access goes through `SettingsPorts` and the `ConfigStore` port, and Plan creation stays review-only without wiring apply or file moving.

When the page is not served from localhost (or `NEXT_PUBLIC_OMYM2_API_MODE=mock` is set), `api-client.ts` returns mock data from `components/omym2/mock-data.ts` instead of calling the API, which keeps static previews working without a backend.
