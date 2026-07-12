---
name: web-frontend-change
description: Procedure for the clean-room React and Vite renewal under web-v2/, its generated API boundary, static packaging, validation, and final cutover to web/. Use for renewal work or Web adapter routes.
---

# Web Frontend Change

Authoritative doc: `docs/codebase/web-frontend.md`.

## Clean-Room Phase Facts

- Until M5, the renewed React + TypeScript + Vite SPA lives in `web-v2/`.
- The existing `web/` is an exclusion zone. Do not read it, search it, import
  it, compare against it, or use its source, copy, layout, assets, package
  choices, screenshots, mock data, or tests as implementation input.
- M5 mechanically deletes the excluded directory and renames `web-v2/` to
  `web/`; that cutover commit contains no design, dependency, API, or feature
  change.
- `web-v2/dist/` (then `web/dist/`) and
  `src/omym2/adapters/web/static_dist/` are generated. Never hand-edit or
  commit `static_dist/`.

## Rules

- Evaluate implementation only against `docs/codebase/web-frontend.md`,
  `docs/contracts/web-api.md`, `docs/contracts/status-reason-catalog.md`,
  `docs/TESTING.md`, the clean-room fixtures, and accessibility tests.
- The frontend consumes committed OpenAPI-generated request/response types. It
  must not hand-copy an API schema or infer capabilities from status values.
- Every state-changing request sends `X-OMYM2-CSRF-Token`; every durable
  Operation start also sends a client-generated `Idempotency-Key`.
- Packages explicitly required by the accepted Web frontend and test contracts
  are within the renewal scope and must be pinned in the lockfile. Stop for
  approval before adding any package outside that accepted stack.
- No Library music file mutation is exposed before M4. Apply and Undo must use
  the atomic claim, shared lock, Plan, Run, and FileEvent contracts.

## Procedure

1. Read the authoritative docs above. Do not inspect the excluded frontend to
   find an example or answer a design question.
2. During M1-M4, edit renewed source only under `web-v2/`. After the completed
   M5 rename, use the same relative paths under `web/`.
3. If the change needs new backend data, treat it as a coordinated two-sided
   contract change:
   - update Pydantic models and the route under
     `src/omym2/adapters/web/` so it calls feature usecases through ports;
   - regenerate and commit the OpenAPI TypeScript client;
   - add/update Python contract tests and clean-room MSW fixtures.
   Routes never read TOML, SQLite, or the filesystem directly.
4. Run the current edit-loop modes selected by `validate`. During staged
   renewal, M1 must point the frontend commands, npm cache, and CI working
   directory to `web-v2/`; M5 changes them to `web/` in the rename commit.
5. Build and audit the Vite export, completely replace the ignored local
   `static_dist/`, and run the relevant unit/component, Playwright, packaging,
   and generated-client drift gates.

## Done means

- Generated OpenAPI source has no drift.
- Frontend format, lint, strict typecheck, unit/component, production build, and
  applicable Playwright keyboard/axe gates pass.
- The export/package audit passes and ignored `static_dist/` matches the built
  renewed source.
- No excluded-frontend source, wording, layout, asset, dependency choice, mock,
  or test baseline entered the change.

## Stop and report when

- Progress appears to require reading or comparing the excluded frontend.
- A package outside the accepted stack appears necessary.
- A UI operation would bypass a feature usecase, capability revalidation,
  exclusive lock, Plan, Run, or FileEvent rule.
- CSP requires an inline-script exception or a broad remote/style allowance.
