---
type: Development Guide
title: Testing
description: Defines OMYM2's Python, bundled-frontend, desktop-browser, architecture, integration, contract, fixture, and release test policy.
tags: [testing, pytest, vitest, playwright, architecture-tests, fixtures]
timestamp: 2026-07-13T21:02:26+09:00
---

# Testing

This document is authoritative for Python, frontend, browser, architecture,
integration, contract, fixture, and clean-room test policy, and for deciding
which contract changes require which tests.

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
* CLI and Web adapters do not import concrete outbound adapters (`db`, `fs`,
  `metadata`, `config`, `artist_ids`), except the documented CLI-only pair

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
* metadata adapter behavior
* vertical flows that combine usecases with real adapters
* exclusive-operation contention and crash release through independent
  processes on both Unix and Windows once the lock adapter exists

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

Required browser coverage, as the corresponding milestone makes each flow
available, is:

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
pull-request Chromium job. Cross-platform package/static smoke runs on Windows;
browser behavior is not duplicated across browser engines without measured need.

## Visual Regression

Visual baselines may contain only the clean-room UI rendered from the fixture
catalog below. Screenshots, snapshots, layouts, or assets from the excluded
frontend are prohibited as inputs or comparison targets.

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
| Path identity contract | path normalization, relink, Library identity, Track identity, and Library-root-relative persistence |
| Status catalog | state transitions, failure behavior, and persistence of allowed values |
| Execution contract | Plan, PlanAction, Run, FileEvent, apply order, failure cases, and undo/refresh/check behavior |
| Architecture contract | dependency-boundary tests and source naming tests |
| Web API contract | route-level request and response JSON shapes, success and error status/envelopes, CSRF on state-changing routes, and affected filters, pagination, facets, or groups |
| Durable operation contract | persistence, idempotency replay/conflict, progress, polling metadata, retention, restart interruption, and reconciliation |
| Exclusive operation contract | Web/CLI exclusion, crash release, 409 conflicts, atomic claims, and Apply/Cancel/Check/Settings race behavior |
| Generated API contract | schema-only OpenAPI export, Pydantic/serializer agreement, committed TypeScript generation, and zero generation drift |

## Fixture Policy

Use in-memory repositories for usecase tests.

Use fixed Clock and IdGenerator ports in tests so time and IDs are deterministic.

Filesystem fixtures should be minimal and task-focused. Read-only filesystem fixtures are appropriate for FileScanner, metadata, hashing, and FileSnapshotReader tests. File-moving fixtures should wait until apply behavior is under test because apply is the workflow that mutates Library music files.

### Web Fixture Catalog

The clean-room Web test boundary implements these canonical scenarios. Fixture
IDs and entity IDs are fixed, full UUID values; timestamps, operation progress,
paths, hashes, counts, and ordering are deterministic.

| Fixture | Required evidence |
| --- | --- |
| `degraded_bootstrap` | missing Config and invalid raw TOML variants; Bootstrap still supplies CSRF and recovery data |
| `library_readiness` | unregistered, stale, and blocked Library variants with backend-provided disabled reasons |
| `ready_plan_mixed_actions` | ready Plan containing move, `refresh_metadata`, skip, and blocked actions with a typed summary |
| `blocked_only_plan` | ready Plan whose actions are all blocked and whose Apply capability/copy explains the zero-mutation outcome |
| `partial_failed_run` | terminal Run with confirmed successes and failures plus linked PlanAction evidence |
| `pending_file_event` | pending FileEvent presented as manual-review-required, with no automatic repair action |
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
5. installed-package performance measurement (`npm run test:performance`):
   record in M1 and enforce the documented budgets from M2
6. wheel/sdist content audit, clean install, installed-package smoke, and sdist-to-wheel rebuild without Node
7. Windows package/static smoke and, from M3 onward, real multiprocess
   exclusive-lock contention/crash-release tests

Pull requests run gates 1–6 on Linux and every gate-7 check required by the
current milestone on Windows (package/static smoke from M1; multiprocess lock
tests from M3).
Protected-branch and release builds retain the same gates and publish their
audited artifacts according to the distribution contract. A gate may be added
before its product flow exists, but it must not be weakened or silently skipped
after that milestone declares the flow complete.

## Test Commands

Use [harness.md](harness.md#test-commands) for quick global checks, focused failure inspection, and deep debug commands. This document defines what to test; `docs/development/harness.md` defines how to run validation commands.
