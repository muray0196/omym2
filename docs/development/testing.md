---
type: Development Guide
title: Testing
description: Test policy per category, contract-change test requirements, fixture policy, Windows semantics, and CI gates.
tags: [testing, pytest, vitest, playwright, desktop, windows, architecture-tests, fixtures, musicbrainz, companions, unprocessed, rollback]
timestamp: 2026-07-18T03:18:00+09:00
---

# Testing

Authoritative for Python, frontend, browser, architecture, integration, contract, and fixture test policy, and for deciding which contract changes require which tests. Domain rules: [DOMAIN.md](../DOMAIN.md); execution: [execution/](../execution/); storage: [STORAGE.md](../STORAGE.md); contracts: [contracts/](../contracts/); validation commands: [harness.md](harness.md). This document is not a test backlog.

Python tests use `pytest` and `pytest-mock`. Frontend unit/component tests use Vitest, React Testing Library, `user-event`, and MSW. Browser tests use Playwright with pinned Chromium and axe integration, desktop viewports only (no phone/tablet/touch coverage required). `pytest-cov` may exist for optional local inspection, but coverage is not a required category unless this document defines a threshold. The package lock owns exact frontend test-tool versions. Tests must not load remote assets, services, analytics, or test data.

## Architecture Tests

Make later implementation hard to place in the wrong layer. Required coverage: source naming conventions; usecases not importing concrete SQLite/filesystem adapters; domain not importing adapters or platform; shared not importing upper layers; forbidden dependencies staying forbidden; adapters not importing platform; CLI/Web/desktop adapters not importing concrete outbound adapters (`db`, `fs`, `metadata`, `config`, `artist_ids`) except the documented CLI-only pair; the desktop adapter not importing the Web adapter or exposing a native bridge.

## Unit Tests

Cover pure domain behavior and usecases through ports and fakes: domain services and invariants; typed ID behavior through IdGenerator; path normalization and PathPolicy; usecase decisions expressed through repositories, ports, and fakes; state transitions that need no concrete adapters.

## Integration Tests

Cover adapters and vertical slices: TOML config load/save/validation; SQLite migrations and repositories; internal storage creation under the application root; filesystem scanning and snapshot capture; retained-object observation and mutation on POSIX and native Windows (link/reparse rejection, replacement races, exclusive target claims, exact-object deletion and cleanup); metadata adapter behavior; vertical flows combining usecases with real adapters; exclusive-operation contention and crash release through independent processes on Unix and Windows; the desktop server adapter serving root, deep route, hashed asset, and Bootstrap through one retained ephemeral loopback listener.

## Frontend Unit And Component Tests

Cover behavior within the bundled React application without a production server, using accessible queries and observable behavior (never DOM class names or component internals). Required coverage: status/capability/structured-error presentation with exhaustive maps for coordinated closed enums and explicit failure for impossible values; cursor reset and URL synchronization on query/filter/grouping/sort/selection changes; loading, empty, degraded, disconnected, validation, conflict, and unexpected-error states; CSRF attachment and the one explicitly safe Bootstrap-refresh retry; Settings diff, unsaved-draft protection, and Config revision conflicts; keyboard navigation, focus restoration, live-region announcements, reduced motion; operation status polling, terminal results, interruption, expiration, connectivity loss.

MSW handlers and fixtures must implement the same generated API types consumed by production code; handwritten fixture shapes must fail type checking when the API contract changes.

## Browser End-To-End Tests

Playwright E2E is a required Web UI gate: pinned Chromium in CI, against a programmatically started FastAPI app on an ephemeral loopback port. The registered and first-run profiles each use a temporary application root, Config state, SQLite database, and music-file tree. Tests must not open a user's browser, read user state, or access the network; an automatic context guard fails every non-loopback runtime request.

Required coverage: (1) first run through Settings save and both Organize outcomes (`plan_created`, `registered_without_plan`); (2) Add Plan through review, Apply, and successful History; (3) a Plan containing blocked actions; (4) a partially failed Run and its succeeded/failed evidence; (5) eligible Run through Undo Plan review, Apply, filesystem restoration, and History; (6) keyboard-only Command Center navigation and focus restoration; (7) deep-link reload and the React Router Not Found screen; (8) axe scans of every primary route and operation dialog; (9) Check start, completion, and persisted result after reload.

The non-mutating route sentinel proves inspection, Settings, planning, and Check routes preserve an unrelated Library file. File-moving fixtures are allowed only for Apply and Undo flows, inside the temporary Library tree or their explicit temporary external restore path. Playwright tests use role locators, accessible names, and ARIA snapshots — never CSS class names. Keyboard and axe checks run in the required pull-request Chromium job; browser behavior is not duplicated across engines without measured need.

## Native Windows Package Smoke

Runs against the frozen ZIP on Windows x64; not simulated on Linux and not a duplicate of the Playwright suite. It must verify: the shared Evergreen WebView2 prerequisite; one visible OMYM2 window and no external browser; an exact HTTP-200 root document with successful pywebview injection; primary SPA routes, deep route, hashed asset, Bootstrap and Settings endpoints, and production HTTP security. It creates one non-applied reviewable Plan through the packaged API as persisted-state setup; after relaunch, Microsoft UI Automation stays scoped to WebView2's document while exercising the interactive Overview, all six shell routes, Settings, and Add form submission through a ready Plan detail (API readback may verify but not substitute for the second Plan's native UI creation). It must then prove graceful close, process and listener termination, deletion of extracted copy A, and Config/SQLite/Plan persistence when copy B runs from a different directory against the same isolated `%LOCALAPPDATA%` root.

The smoke records machine-readable JSON evidence: startup timing, graceful shutdown, relaunch, archive/unpacked size, selected loopback behavior, exact audited wheel/archive identities. Its paired package audit rejects bundled Node.js, Chromium, alternate renderers, source trees, and resources differing from the wheel. Exact commands: [Windows Desktop Packaging](desktop-packaging.md). The native flow proves core packaged interactions but does not replace the Playwright suite. Windows 11 release validation must repeat the complete smoke on the supported workstation target and retain evidence; hosted Windows Server results cannot be relabeled as that run.

## Windows Filesystem Semantics

The retained-object suites run unchanged on POSIX and native Windows, but the platforms enforce the same invariants differently. Tests and `adapters/fs` changes must respect these verified Windows behaviors:

* Filesystem identity comparisons go through `stat_change_marker_ns` (`src/omym2/adapters/fs/win32_file_handles.py`), never raw `st_ctime_ns`: Python 3.14 maps Windows `st_ctime` to NTFS ChangeTime, and by-name stats report it with transient staleness for freshly written files, so raw comparisons across the path-stat/handle-stat boundary fail intermittently on real NTFS.
* By-name Windows stats may fall back to stale directory-entry timestamps; build expected identities through an opened handle (`os.fstat`), not `Path.stat()`.
* NT share-mode arbitration binds only handles holding data or delete access. An attributes-only handle neither blocks nor is blocked by renames — retained directory handles request `FILE_LIST_DIRECTORY` because withholding `FILE_SHARE_DELETE` prevents parent replacement only from a data-access handle.
* TOCTOU simulations renaming an open file or its parent are impossible on Windows (sharing violation). Such tests platform-split: assert OS-level enforcement on `os.name == "nt"` and detection-based invalidation on POSIX — enforcement is the stronger form of the same guarantee, not a skipped check.
* The native Win32 backend preempts the descriptor and path fallbacks; a test targeting a fallback must construct the reader with `windows_backend=None` — monkeypatching `_OPEN_SUPPORTS_DIR_FD` alone is a no-op on Windows.
* SQLite opens its database without `FILE_SHARE_DELETE`, and `sqlite3`'s connection context manager only ends the transaction, not the connection. Close connections deterministically (`contextlib.closing`, read-only URI mode for observation) or later Windows directory cleanup fails with a sharing violation.
* `cmd.exe` builtins such as `mklink` need one subprocess argv element per token; a single pre-quoted command string is corrupted by `list2cmdline` escaping.

Windows-only behavior is reproducible without CI round-trips: under WSL2 the Windows host can run the same pytest selection on real NTFS through `uv` on the host side. Prefer that reproduction before pushing Windows-affecting changes.

## Visual Regression

Visual baselines may contain only the current UI rendered from the fixture catalog below; screenshots, snapshots, layouts, or assets from previous frontends are prohibited as inputs or comparison targets. The baseline matrix covers supported desktop layouts plus loading, empty, error, long-path, large-count, 200% zoom, and reduced-motion states. Phone/tablet baselines must not become release requirements. Visual checks run in the pinned Linux Chromium environment.

## Contract Change Test Requirements

Contract changes require tests for the changed behavior.

| Contract change | Required test focus |
| --- | --- |
| Config contract | current-version load, save, validation, defaults, reset rejection, and Web settings JSON serialization/parsing |
| DB schema contract | clean baseline and future migrations, old-state rejection, repositories, constraints, stored JSON, timestamps, and path representation |
| Path identity contract | path normalization, relink, Library, Track, and CompanionAsset identity, unprocessed retained-root/protected-path rules, Library-root-relative persistence, and the POSIX descriptor/native Windows retained-HANDLE observation and mutation boundary |
| Status catalog | state transitions, failure behavior, persistence of allowed values, and exhaustive bundled-client presentation |
| Execution contract | Plan, PlanAction dependencies, Run, typed FileEvents, apply order, companion failure/recovery, unprocessed collection/reversal, and undo/refresh/check behavior |
| Architecture contract | dependency-boundary tests and source naming tests |
| Web API contract | route-level request and response JSON shapes, success and error status/envelopes, CSRF on state-changing routes, and affected filters, pagination, facets, or groups |
| Durable operation contract | persistence, idempotency replay/conflict, status polling metadata, retention, restart interruption, and reconciliation |
| Exclusive operation contract | Web/CLI exclusion, crash release, 409 conflicts, atomic claims, and Apply/Cancel/Check/Settings race behavior |
| Generated API contract | schema-only OpenAPI export, Pydantic/serializer agreement, committed TypeScript generation, and zero generation drift |

## Fixture Policy

Use in-memory repositories for usecase tests. Use fixed Clock and IdGenerator ports so time and IDs are deterministic. Filesystem fixtures stay minimal and task-focused: read-only fixtures for scanners, metadata, hashing, and snapshot readers; file-moving fixtures wait until Apply behavior is under test, because Apply is the workflow that mutates audio, companion, or unprocessed files.

### Provider And Companion Fixtures

Automatic naming tests must not load a real model or contact MusicBrainz: use fixed predictor output, recorded provider payloads/errors, a fixed or advancing clock, and temporary SQLite cache/cadence state. Cover persisted opt-out, missing model/runtime, confidence boundaries, accepted and ambiguous results, retry limits, and one cadence reservation per attempt without wall-clock sleeps.

Companion fixtures use minimal temporary roots with explicit regular, non-symlink audio, `.lrc`, `.jpg`, `.png` entries plus fixed content snapshots and IDs. Cover disabled behavior, ambiguous ownership, shared artwork-once ordering, dependencies, collisions, partial/pending failure, Check recovery classification, and Undo. Mutation fixtures assert both no-overwrite behavior and the exact source/Library root boundary.

### Unprocessed Fixtures

Unprocessed tests use a temporary external source root, separate Library root, exact internal Config/data/log paths, regular leftovers, claimed audio and companion files, the destination subtree, a symlink, and fixed content hashes. They prove: Add requests no complete inventory when both feature toggles are false; unprocessed-only mode still applies classification-only companion claims reserving recognized paths without actions, snapshots, IDs, or dependencies; Check unmanaged-companion discovery follows `companions.enabled` while managed and recorded diagnostics do not. Further cases cover music/companion claim precedence, precise exclusions, protected target overlap, broken-symlink target presence, snapshot failures, deterministic ordering, and persistence of every action beyond the result preview limit.

The concrete filesystem/SQLite vertical fixture covers Plan creation, current toggle disablement before Apply, pending-first no-overwrite mutation, History, clean Check, missing/changed Check errors, exact Undo, and absence of Track or CompanionAsset state. Separate cases retain pending evidence after simulated process loss, block Undo after content changes, preserve late-collision source and target bytes, and prove neither direction removes empty directories.

### Web Fixture Catalog

The bundled Web test boundary implements these canonical scenarios. Fixture and entity IDs are fixed full UUIDs; timestamps, operation status, paths, hashes, counts, and ordering are deterministic.

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

Fixtures are authored from the domain, API, execution, design-token, and accessibility contracts.

## CI Execution Policy

Required independently diagnosable CI gates:

1. Python schema and contract tests
2. OpenAPI export and generated-client drift check
3. frontend format, lint, strict typecheck, unit/component tests, and production build
4. pinned-Chromium Playwright E2E with keyboard and axe checks
5. installed-package performance budget measurement (`npm run test:performance`)
6. wheel/sdist content audit, clean install, installed-package smoke, and sdist-to-wheel rebuild without Node
7. native Windows retained-HANDLE observation and mutation, scanner containment, companion/unprocessed concrete adapter E2E, real multiprocess exclusive-lock contention/crash release, and desktop build, audit, and native-window smoke with JSON evidence

Pull requests and protected branches run gates 1–6 on Linux; Windows CI runs gate-7 native repository tests and packaged smoke as independent jobs so the runtime suite can start before Linux package evidence is ready. The fast API/client job remains independently diagnosable, the Frontend job owns complete Web validation, and CI-only Playwright performs only its job-local static build/sync plus browser profiles while performance reuses the audited wheel. Documentation and agent-surface-only changes run documentation conformance; every product, tooling, workflow, or unknown change remains on the full suite. Native repository tests do not replace the packaged smoke or turn hosted-server evidence into release evidence. Completed product-flow gates must not be weakened or silently skipped. Hosted `windows-2025` jobs are development proxies — a release candidate must run the same packaged smoke on Windows 11 x64 and retain its JSON evidence.

## Test Commands

Use [harness.md](harness.md#test-commands) for focused failure inspection and deep debug commands. This document defines what to test; `docs/development/harness.md` defines how to run validation.
