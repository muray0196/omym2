---
name: web-frontend-change
description: Procedure for changing the Next.js Web UI under web/, including the static export sync into the Python package and the JSON API boundary. Use for any change under web/ or to the web adapter routes.
---

# Web Frontend Change

Authoritative doc: `docs/codebase/web-frontend.md`.

## Layout facts

- `web/` is a Next.js App Router static export (`output: "export"`); no Node server in production.
- Single-page console: `web/app/page.tsx` renders `Console`; screens live in `web/components/omym2/screens/`.
- The frontend talks to the backend **only** through the JSON API in `web/components/omym2/api-client.ts`. Off-localhost (or `NEXT_PUBLIC_OMYM2_API_MODE=mock`) it serves mock data from `mock-data.ts`.
- `web/out/` and `src/omym2/adapters/web/static_dist/` are generated and ignored. Never hand-edit or commit either.

## Rules

- Match existing component style: TypeScript, Tailwind, existing `components/ui/` primitives before new dependencies.
- Settings save requests must keep sending the CSRF token header (`X-OMYM2-CSRF-Token`).

## Procedure

1. Edit source under `web/app/`, `web/components/`, or `web/lib/` only.
2. If the change needs new backend data, it is a two-sided change:
   - backend: route in `src/omym2/adapters/web/routes/api.py` that calls a feature usecase through ports (routes never read TOML or the filesystem directly), plus known-route registration in `src/omym2/adapters/web/app.py` if a new page path is added;
   - frontend: `api-client.ts` method + matching entry in `mock-data.ts` so static preview keeps working.
   Backend edits also follow `implement-change`.
3. Validate: `scripts/checks.sh web` (runs `npm ci`, `format:check`, `lint`, `build`).
4. `npm run build` also regenerates `src/omym2/adapters/web/static_dist/` via `web/scripts/sync-static-export.mjs`. Keep the generated copy local; do not stage or commit `static_dist/`.
5. Manual check when UI behavior changed: `cd web && npm run dev`, or serve the packaged UI with `uv run omym2 settings`.

## Done means

- `scripts/checks.sh web` passes and the ignored local `static_dist/` is in sync.
- Mock mode still renders every screen you touched (no crash on mock data shape).

## Stop and report when

- The change would require a new npm dependency — stop and ask for explicit approval before adding one.
- The change seems to require browser E2E testing (Playwright is explicitly deferred by `docs/TESTING.md`).
