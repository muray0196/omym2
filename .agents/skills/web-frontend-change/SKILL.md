---
name: web-frontend-change
description: Change the OMYM2 React and Vite frontend, generated API boundary, static packaging, or Web adapter routes. Use for implementation work under web/ or src/omym2/adapters/web/.
---

# Web Frontend Change

Authoritative docs remain under `docs/`; this skill is the operational safety
cache and routes only the sections needed for the current change.

## Current Facts

- The React + TypeScript + Vite SPA lives in `web/`.
- `web/dist/` and `src/omym2/adapters/web/static_dist/` are generated. Never
  hand-edit or commit `static_dist/`.

## Rules

- The frontend consumes committed OpenAPI-generated request/response types. It
  must not hand-copy an API schema or infer capabilities from status values.
- Every state-changing request sends `X-OMYM2-CSRF-Token`; every durable
  Operation start also sends a client-generated `Idempotency-Key`.
- Packages explicitly required by the accepted Web frontend and test contracts
  must be pinned in the lockfile. Stop for approval before adding any package
  outside that accepted stack.
- Apply and Undo must use the atomic claim, shared lock, Plan, Run, and
  FileEvent contracts.

## Focused reading

Locate headings first and read only the matching section:

| Change | Read |
| --- | --- |
| Source layout, routes, interaction, keyboard, build, serving, packaging, or performance | Matching section of `docs/codebase/web-frontend.md` |
| Request/response shape, envelope, CSRF, browsing, idempotency, or one endpoint | Cross-cutting rule plus the affected endpoint section in `docs/contracts/web-api.md` |
| Persisted or presented status/reason | The affected entity section plus Cross-Cutting Rules in `docs/contracts/status-reason-catalog.md` |
| Unit, browser, accessibility, or fixture behavior | Matching test/fixture section in `docs/development/testing.md` |

For an explicit external design/accessibility audit request, fetch and apply
`https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md`.

Do not preload all four documents. Do not read generated clients, OpenAPI JSON,
lockfiles, `dist/`, or `static_dist/` in full; use targeted symbols, generation
drift, or focused diffs.

## Procedure

1. Route focused reading through the table above.
2. Edit frontend source only under `web/`; do not create a parallel Web tree.
3. If the change needs new backend data, treat it as a coordinated two-sided
   contract change:
   - update Pydantic models and the route under
     `src/omym2/adapters/web/` so it calls feature usecases through ports;
   - regenerate and commit the OpenAPI TypeScript client;
   - add/update Python contract tests and clean-room MSW fixtures.
   Routes never read TOML, SQLite, or the filesystem directly.
4. Run the current edit-loop modes selected by `validate`; frontend commands,
   npm cache, and CI working directories all use `web/`.
5. Build and audit the Vite export, completely replace the ignored local
   `static_dist/`, and run the relevant unit/component, Playwright, packaging,
   and generated-client drift gates.

## Done means

- Generated OpenAPI source has no drift.
- Frontend format, lint, strict typecheck, unit/component, production build, and
  applicable Playwright keyboard/axe gates pass.
- The export/package audit passes and ignored `static_dist/` matches the built
  source.

## Stop and report when

- A package outside the accepted stack appears necessary.
- A UI operation would bypass a feature usecase, capability revalidation,
  exclusive lock, Plan, Run, or FileEvent rule.
- CSP requires an inline-script exception or a broad remote/style allowance.
