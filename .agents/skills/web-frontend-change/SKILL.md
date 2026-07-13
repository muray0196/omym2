---
name: web-frontend-change
description: Procedure for the bundled React and Vite frontend under web/, its generated API boundary, static packaging, validation, and Web adapter routes.
---

# Web Frontend Change

Authoritative doc: `docs/codebase/web-frontend.md`.

## Current Facts

- The React + TypeScript + Vite SPA lives in `web/`.
- M5 deleted the legacy frontend before moving the clean-room implementation
  into this path. There is no parallel frontend or compatibility surface.
- `web/dist/` and `src/omym2/adapters/web/static_dist/` are generated. Never
  hand-edit or commit `static_dist/`.

## Rules

- Evaluate implementation only against `docs/codebase/web-frontend.md`,
  `docs/contracts/web-api.md`, `docs/contracts/status-reason-catalog.md`,
  `docs/TESTING.md`, the clean-room fixtures, and accessibility tests.
- The frontend consumes committed OpenAPI-generated request/response types. It
  must not hand-copy an API schema or infer capabilities from status values.
- Every state-changing request sends `X-OMYM2-CSRF-Token`; every durable
  Operation start also sends a client-generated `Idempotency-Key`.
- Packages explicitly required by the accepted Web frontend and test contracts
  must be pinned in the lockfile. Stop for approval before adding any package
  outside that accepted stack.
- Apply and Undo must use the atomic claim, shared lock, Plan, Run, and
  FileEvent contracts.

## Procedure

1. Read the authoritative docs above.
2. Edit frontend source only under `web/`; do not create a parallel Web tree
   or compatibility implementation.
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
