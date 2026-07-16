---
type: Development Guide
title: Testing
description: Defines OMYM2's Python, frontend, browser, architecture, integration, retained-object filesystem, native Windows, provider/companion/unprocessed fixture, rollback, and CI test policy.
tags: [testing, pytest, vitest, playwright, desktop, windows, architecture-tests, fixtures, musicbrainz, companions, unprocessed, rollback]
timestamp: 2026-07-16T06:02:32+09:00
---

# Testing

This document is authoritative for Python, frontend, browser, architecture,
integration, contract, and fixture test policy, and for deciding which contract
changes require which tests.

Domain rules are in [DOMAIN.md](../DOMAIN.md), execution semantics are in [execution/](../execution/), storage rules are in [STORAGE.md](../STORAGE.md), contract docs are in [contracts/](../contracts/), and developer validation commands are in [harness.md](harness.md).

This document is not a test backlog.

Python test authoring uses `pytest` and `pytest-mock`. Frontend unit and
component tests use Vitest, React Testing Library, `user-event`, and MSW.
Browser tests use Playwright with its pinned Chromium build and axe integration.
Web browser tests use desktop viewports only; phone, tablet, touch-first, and
mobile-navigation coverage is not required.

`pytest-cov` may exist in the development environment for optional local coverage inspection, but coverage reporting is not a separate required test category unless this document defines a threshold.

The package lock owns exact frontend test-tool versions. Tests must not load
remote assets, services, analytics, or test data.

## Architecture Tests

Architecture tests should make later implementation hard to place in the wrong layer.

Required architecture test coverage:

* source files follow naming conventions
* usecases do not import concrete SQLite or filesystem adapters
* domain does not import adapters or platform
* shared does not import upper layers
* forbidden dependencies remain forbidden
* adapters do not import platform
* CLI, Web, and desktop adapters do not import concrete outbound adapters
  (`db`, `fs`, `metadata`, `config`, `artist_ids`), except the documented
  CLI-only pair
* the desktop adapter does not import the Web adapter or expose a native bridge

## Unit Tests

Unit tests should cover pure domain behavior and usecases through ports and fakes.

Use unit tests for:

* domain services and invariants
* typed ID behavior through IdGenerator
* path normalization and PathPolicy behavior
* usecase decisions expressed through repositories, ports, and fakes
* state transitions that do not require concrete adapters

## Integration Tests

Integration tests should cover adapters and vertical slices once their dependencies exist.

Use integration tests for:

* TOML config load / save / validation
* SQLite migrations and repositories
* internal storage creation under the application root
* filesystem scanning and snapshot capture
* retained-object observation and mutation on POSIX and native Windows,
  including link/reparse rejection, replacement races, exclusive target claims,
  and exact-object deletion and cleanup
* metadata adapter behavior
* vertical flows that combine usecases with real adapters
* exclusive-operation contention and crash release through independent
  processes on both Unix and Windows once the lock adapter exists
* the desktop server adapter serving root, deep route, hashed asset, and
  Bootstrap through one retained ephemeral loopback listener

## Frontend Unit And Component Tests

Frontend tests cover behavior within the bundled React application without
starting a production server. They must use accessible queries and observable
behavior rather than DOM class names or component internals.

Required coverage includes:

* status, capability, and structured-error presentation, including unknown-value fallbacks
* cursor reset and URL synchronization when query, filters, grouping, sort, or selection changes
* loading, empty, degraded, disconnected, validation, conflict, and unexpected-error states
* CSRF attachment and the one explicitly safe Bootstrap-refresh retry
* Settings diff, unsaved-draft protection, and Config revision conflicts
* keyboard navigation, focus restoration, live-region announcements, and reduced motion
* operation polling, progress changes, terminal results, interruption, expiration, and loss of connectivity

MSW handlers and fixtures must implement the same generated API types consumed
by production code. Handwritten fixture shapes must fail type checking when the
API contract changes.

## Browser End-To-End Tests

Playwright E2E is a required gate for the Web UI. It uses the pinned
Chromium build in CI and must run against a programmatically started FastAPI app
on an ephemeral loopback port. The registered and first-run profiles each use
a temporary application root, Config state, SQLite database, and music-file
tree. Tests must not open a user's browser, read user state, or access the
network; an automatic context guard fails every non-loopback runtime request.

Required browser coverage is:

1. first run through Settings save and both Organize outcomes (`plan_created` and `registered_without_plan`)
2. Add Plan through review, Apply, and successful History
3. a Plan containing blocked actions
4. a partially failed Run and its succeeded/failed evidence
5. eligible Run through Undo Plan review, Apply, filesystem restoration, and History
6. keyboard-only Command Center navigation and focus restoration
7. deep-link reload and the React Router Not Found screen
8. axe scans of every primary route and operation dialog
9. Check start, completion, and persisted result after reload

The non-mutating route sentinel proves that inspection, Settings, planning, and
Check routes preserve an unrelated Library file. File-moving fixtures are
allowed only for Apply and Undo flows and remain inside the temporary Library
tree or their explicit temporary external restore path.

Playwright tests use role locators, accessible names, and ARIA snapshots. They
must not depend on CSS class names. Keyboard and axe checks run in the required
pull-request Chromium job. Native desktop package smoke runs on Windows;
browser behavior is not duplicated across browser engines without measured need.

## Native Windows Package Smoke

Native package acceptance runs against the frozen ZIP on Windows x64; it is not
simulated on Linux and does not duplicate the Playwright product-flow suite. It
must verify the shared Evergreen WebView2 prerequisite, one visible OMYM2
window, no external browser, an exact HTTP-200 root document with successful
pywebview injection, the primary SPA routes, deep route, hashed asset, Bootstrap
and Settings endpoints, and production HTTP security. It creates one
non-applied reviewable Plan through the packaged API as persisted-state setup.
After relaunch, Microsoft UI Automation must remain scoped to WebView2's
document while it exercises the interactive Overview, all six shell routes,
Settings, and Add form submission through a ready Plan detail. API readback may
verify the result but must not substitute for that second Plan's native UI
creation. The smoke must then prove graceful close, process and listener
termination, deletion of extracted copy A, and Config/SQLite/Plan persistence
when extracted copy B runs from a different directory against the same isolated
`%LOCALAPPDATA%` root.

The smoke run records machine-readable JSON evidence for startup timing,
graceful shutdown, relaunch, archive and unpacked package size, selected
loopback behavior, and exact audited wheel/archive identities. Its paired
package-audit evidence also rejects bundled Node.js, Chromium, alternate
renderers, source trees, and resources that differ from that wheel. Exact
commands and artifact ownership are in
[Windows Desktop Packaging](desktop-packaging.md). The native UI flow proves the
core packaged interactions but does not replace the browser-hosted Playwright
suite, which remains authoritative for broader behavior, accessibility, and
edge cases. Windows 11 release validation must repeat the complete smoke on the
supported workstation target and retain its evidence; hosted Windows Server
results cannot be relabeled as that target run.

## Visual Regression

Visual baselines may contain only the current UI rendered from the fixture
catalog below. Screenshots, snapshots, layouts, or assets from previous
frontends are prohibited as inputs or comparison targets.

The baseline matrix covers supported desktop layouts plus loading, empty,
error, long-path, large-count, 200% browser zoom, and reduced-motion states.
Phone and tablet baselines are prohibited from becoming release requirements.
Visual checks run in the pinned Linux Chromium environment so rendering
differences are not hidden by cross-platform snapshot churn.

## Contract Change Test Requirements

Contract changes require tests for the changed behavior.

| Contract change | Required test focus |
| --- | --- |
| Config contract | config load, save, validation, defaults, and migration behavior; include Web settings JSON serialization and parsing when that boundary changes |
| DB schema contract | migrations, repositories, constraints, stored JSON, timestamps, and path representation |
| Path identity contract | path normalization, relink, Library, Track, and CompanionAsset identity, unprocessed retained-root/protected-path rules, Library-root-relative persistence, and the POSIX descriptor/native Windows retained-HANDLE observation and mutation boundary |
| Status catalog | state transitions, failure behavior, persistence of allowed values, catalog-version bump, and old-client refusal |
| Execution contract | Plan, PlanAction dependencies, Run, typed FileEvents, apply order, companion failure/recovery, unprocessed collection/reversal, and undo/refresh/check behavior |
| Architecture contract | dependency-boundary tests and source naming tests |
| Web API contract | route-level request and response JSON shapes, success and error status/envelopes, CSRF on state-changing routes, and affected filters, pagination, facets, or groups |
| Durable operation contract | persistence, idempotency replay/conflict, progress, polling metadata, retention, restart interruption, and reconciliation |
| Exclusive operation contract | Web/CLI exclusion, crash release, 409 conflicts, atomic claims, and Apply/Cancel/Check/Settings race behavior |
| Generated API contract | schema-only OpenAPI export, Pydantic/serializer agreement, committed TypeScript generation, and zero generation drift |

## Fixture Policy

Use in-memory repositories for usecase tests.

Use fixed Clock and IdGenerator ports in tests so time and IDs are deterministic.

Filesystem fixtures should be minimal and task-focused. Read-only filesystem
fixtures are appropriate for scanners, metadata, hashing, and snapshot-reader
tests. File-moving fixtures should wait until Apply behavior is under test
because Apply is the workflow that mutates audio, companion, or unprocessed
files.

### Provider And Companion Fixtures

Automatic naming tests must not load a real model or contact MusicBrainz. Use
fixed predictor output, recorded provider payloads/errors, a fixed or advancing
clock, and temporary SQLite cache/cadence state. Cover persisted opt-out,
missing model/runtime, confidence boundaries, accepted and ambiguous results,
retry limits, and one cadence reservation per attempt without wall-clock
sleeps.

Companion fixtures use minimal temporary roots with explicit regular,
non-symlink audio, `.lrc`, `.jpg`, and `.png` entries plus fixed content
snapshots and IDs. Cover disabled behavior, ambiguous ownership, shared
artwork-once ordering, dependencies, collisions, partial/pending failure,
Check recovery classification, and Undo. Mutation fixtures must assert both
no-overwrite behavior and the exact source/Library root boundary.

### Unprocessed And Downgrade Fixtures

Unprocessed tests use a temporary external source root, separate Library root,
exact internal Config/data/log paths, regular leftovers, claimed audio and
companion files, the destination subtree, a symlink, and fixed content hashes.
They prove that Add does not request complete inventory when both feature
toggles are false and that unprocessed-only mode still applies
classification-only companion claims which reserve recognized paths without
actions, content snapshots, IDs, or dependencies. They also prove that Check
unmanaged-companion discovery follows `companions.enabled` while managed and
recorded diagnostics do not. Further cases cover music/companion claim
precedence, precise exclusions, protected target overlap, broken-symlink
target presence, snapshot failures, deterministic ordering, and persistence of
every action beyond the result preview limit.

The concrete filesystem/SQLite vertical fixture covers Plan creation, current
toggle disablement before Apply, pending-first no-overwrite mutation, History,
clean Check, missing/changed Check errors, exact Undo, and absence of Track or
CompanionAsset state. Separate cases retain pending evidence after simulated
process loss, block Undo after content changes, preserve late-collision source
and target bytes, and prove that neither direction removes empty directories.

Downgrade/rollback validation starts from a matched Config/SQLite backup. It
exercises Apply and Cancel for ready Plans containing each newer action family,
keeps pending companion/unprocessed events manual-review-only, restores both
stores together, and proves an older binary is never used to read or apply a
Plan containing an unknown closed value.

### Web Fixture Catalog

The bundled Web test boundary implements these canonical scenarios. Fixture
IDs and entity IDs are fixed, full UUID values; timestamps, operation progress,
paths, hashes, counts, and ordering are deterministic.

| Fixture | Required evidence |
| --- | --- |
| `degraded_bootstrap` | missing Config and invalid raw TOML variants; Bootstrap still supplies CSRF and recovery data |
| `library_readiness` | unregistered, stale, and blocked Library variants with backend-provided disabled reasons |
| `ready_plan_mixed_actions` | ready Plan containing move, `move_unprocessed`, `refresh_metadata`, skip, and blocked actions with a typed summary |
| `blocked_only_plan` | ready Plan whose actions are all blocked and whose Apply capability/copy explains the zero-mutation outcome |
| `partial_failed_run` | terminal Run with confirmed successes and failures plus linked PlanAction evidence |
| `pending_file_event` | pending FileEvent presented as manual-review-required, with no automatic repair action |
| `unprocessed_history` | succeeded `move_unprocessed_file` evidence with its explicit History label and null managed identity |
| `unprocessed_health` | missing/changed unprocessed findings presented as danger/error evidence with an `omym2 history` remediation |
| `precondition_failure_without_event` | failed apply-time PlanAction for which no Library mutation or FileEvent occurred |
| `undo_ineligible_refresh_run` | terminal Run containing `refresh_metadata`, with a backend-provided Undo refusal reason |

Fixtures must be authored from the domain, API, execution, design-token, and
accessibility contracts.

## CI Execution Policy

The bundled frontend requires these independently diagnosable CI gates:

1. Python schema and contract tests
2. OpenAPI export and generated-client drift check
3. frontend format, lint, strict typecheck, unit/component tests, and production build
4. pinned-Chromium Playwright E2E with keyboard and axe checks
5. installed-package performance budget measurement (`npm run test:performance`)
6. wheel/sdist content audit, clean install, installed-package smoke, and sdist-to-wheel rebuild without Node
7. native Windows retained-HANDLE observation and mutation, scanner
   containment, companion/unprocessed concrete adapter E2E, real multiprocess
   exclusive-lock contention/crash release, and desktop build, audit, and
   native-window smoke with JSON evidence

Pull requests and protected branches run gates 1–6 on Linux. Windows CI runs
the rooted observation contract, scanner containment, concrete companion and
unprocessed adapter E2E, real multiprocess lock tests, and native desktop
package smoke from gate 7. These native repository tests do not replace the
packaged smoke or turn hosted-server evidence into release evidence. Completed
product-flow gates must not be weakened or silently skipped.

The hosted `windows-2025` job is a native Windows Server 2025 x64 development
proxy. It does not establish support for that server edition or replace release
validation on the supported Windows 11 x64 target. A release candidate must run
the same packaged smoke on Windows 11 x64 and retain its JSON evidence.

## Test Commands

Use [harness.md](harness.md#test-commands) for quick global checks, focused failure inspection, and deep debug commands. This document defines what to test; `docs/development/harness.md` defines how to run validation commands.
