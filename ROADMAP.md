# Web UI Roadmap

## Decision

The GUI apply decision is resolved by full renewal rather than by extending
the current UI: replace the Web UI with a clean-room React + TypeScript +
Vite implementation that ends as a complete operation surface, including
Apply, ready-Plan Cancel, and Undo through a reviewed Plan.

Authoritative repository documentation now owns the frozen contract: [Product](docs/PRODUCT.md),
[Web API](docs/contracts/web-api.md),
[Durable Operations](docs/contracts/operations.md),
[Web Frontend](docs/codebase/web-frontend.md), and the accepted
[architecture decisions](docs/decisions/). The superseded detailed proposal is
planning input only and cannot override those sources. This roadmap records
only the outcome, material decisions, ordering, and gates.

## Outcome and Boundary

A keyboard-first local operations console built around the safe operating
loop: choose an objective, generate a Plan, review actions, apply, verify in
History and Check, and undo through a new Plan. It stays localhost-only,
offline-first, and telemetry-free; the SPA is bundled in the wheel with no
Node at runtime; presentation is dark-only and desktop-browser-only under the
tracked Web frontend contract. Phone, tablet, touch-first, and mobile-specific
layout support are outside the product and test boundary. It is still not a
music player: no playback, tag editing, cover art, or cloud features.

The last review-only `main` release remains the pinned rollback anchor. Its
frontend source was excluded throughout clean-room implementation and deleted
at M5. Only the completed M5 tree is merged/released, so the breaking SPA/API
pair lands atomically.

## Material Decisions

- Clean-room rebuild completed with an atomic cutover to `web/` after deleting
  the old frontend. No feature flag, screen-by-screen migration, or comparison
  against the old UI entered implementation.
- Backend-authoritative behavior: typed API envelope with structured errors,
  capabilities with disabled reasons, opaque cursors. React never infers
  permitted operations from status values.
- Mutation ships last. Through M3 the UI changes persistent state (Settings,
  Plans, Checks, Library registration) but never library music files.
- Durable operations: 202 + polling, client idempotency keys, `interrupted`
  on restart with no automatic resume; pending FileEvents go to manual
  review, never automatic repair. Exact polling and retention tunables are
  owned by the Durable Operation contract.
- Long-running CLI flows persist the same Operation lifecycle while executing
  inline under the shared lock; platform generates their internal idempotency
  key without adding a CLI flag or changing command result semantics.
- One exclusive state-changing operation across Web and CLI via a shared
  application-root OS file lock; conflicts return 409 instead of queueing.
- Settings saves use an opaque `config_revision` with compare-and-set; no
  last-write-wins against CLI edits.
- Apply is accepted only through an atomic claim: lock, root verification,
  and a single-transaction CAS over the Plan transition, Run creation, and
  operation reservation. Terminal Plans are never applied again.
- Undo always generates an Undo Plan reviewed and applied like any other;
  Runs containing `refresh_metadata` are not undoable; restore conflicts
  become blocked actions, never overwrites.
- Deliberate breaking API replacement without `/api/v1`; external Web API
  clients are unsupported under accepted ADR 0001.
- Unknown HTML routes use the SPA fallback and React Router Not Found screen;
  `/api` and missing assets never fall back to HTML.
- Playwright Chromium keyboard/axe E2E is required. Final and pre-cutover
  rollback packages are retained in the official release; intermediate
  milestone evidence may use CI artifacts.

## Ordered Milestones

1. **M0 Contract freeze** — The product/test/distribution contracts, API
   envelope and error catalog, capabilities, `config_revision`, Operation and
   lock decisions, route/status UX, performance conditions, and fixture
   catalog are frozen in authoritative repository documentation.
2. **M1 Foundation** — `web-v2/` from scratch: tokens, primitives, app
   shell, router, TanStack Query, OpenAPI-generated client, Command Center,
   temporary CI gate, CSP spike, dev proxy and SPA fallback.
3. **M2 Inspection console** — Read-only vertical slices with cursor
   pagination, filtering, grouping, and deep links: Plans, History, Library,
   Health (persisted Check), Overview.
4. **M3 Settings and planning** — Operation substrate and shared lock;
   Settings preview/diff/atomic save; Check execution; Add, Organize, and
   Refresh Plan generation into Plan Review. Yields a release candidate that
   does not modify library music files.
5. **M4 Execution console** — The GUI apply slice: atomic Apply claim,
   Apply, Cancel of ready Plans, Undo Plan generation and apply,
   crash/pending reconciliation, race and partial-failure E2E.
6. **M5 Hardening and cutover** — Delete the old frontend, rename `web-v2/`
   to `web/`, accessibility/performance/security passes, wheel/sdist audits
   and smoke tests, docs and index regeneration, release and rollback
   artifacts.

Rough estimate: 41–62 person-days total. P2 items (unified search, SSE
progress, Check history, multi-library, localization) stay out of scope
until measurement justifies them.

M1 starts only from a clean worktree after the M0 contract change is committed
as its own review boundary. The superseded proposal stays outside the
implementation context/denylisted, and M1 review does not inspect deleted
legacy documentation or excluded frontend diffs.

## Key Risks

- Synchronous scans blocking the event loop → build the operation substrate
  before any scan/Check/Apply endpoint.
- Apply/Cancel/CLI races violating the single-use contract → CAS claim,
  shared lock, dedicated race tests.
- Worker crashes leaving running Runs or pending FileEvents → Operation becomes
  `interrupted`, Plan/Run reconcile from durable evidence, no auto-resume, and
  manual review via Check.
- Old-UI contamination breaking the clean-room requirement → path denylist
  during implementation plus a review checklist.
- Static assets missing from the wheel → export/package audits and
  clean-install smoke tests.

## Validation and Rollback

Keep every milestone independently reviewable. Gates: frontend typecheck,
lint, unit/component tests, and Playwright E2E (keyboard and axe included);
backend pytest and the architecture gate; generated API types free of
drift; wheel/sdist content audit and clean-install smoke test. Mutation E2E
proves Plan-centered Apply and Undo outcomes while non-mutating routes preserve
unrelated Library files. Keep the final wheel/sdist and a checksummed rollback
ZIP containing the standardized wheel/sdist of the pinned last pre-cutover
commit. Rollback code does not provide backward persisted-state compatibility,
so recovery also requires a pre-cutover state backup.
