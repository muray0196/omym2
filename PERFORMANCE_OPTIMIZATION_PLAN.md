---
type: Plan
title: Performance Optimization Plan
description: Tracks the implemented OMYM2 performance roadmap, measured phase impact, safety trade-offs, and the approved opt-in trust-stat policy.
timestamp: 2026-07-11T16:52:31+09:00
status: Phases 0-3 implemented and validated
---

# Performance Optimization Plan (2026-07-10)

Produced by a four-segment parallel analysis of the pipeline (ingest I/O, plan-creation domain, apply/undo + SQLite, read/serve/startup paths). Every code claim below was verified against the current source; timing numbers are microbenchmarks from this machine (WSL2, repo on ext4) — **ratios generalize, absolute ms do not**. Baseline: main @ c50f33c.

## Product framing (governs priorities)

- `docs/PRODUCT.md:25`: the product's value is *safe, reviewed* mutation — not raw speed. No optimization here may weaken the write-ahead crash-safety design.
- `docs/PRODUCT.md:57`: the daily path is `add` on small batches + `apply`. Full-library flows (`organize`, `refresh --all`, `check`) are occasional but set worst-case wall times.
- Environment: WSL2. If a Library lives under a drvfs `/mnt/*` mount, per-call `stat()`/`open()` costs ~260–440× ext4 (measured). Syscall-count reduction and parallelism are the drvfs mitigations; bulk read bandwidth is fine.

## Where the time actually goes (50k-track scale)

| Cost | Command(s) | Magnitude | Nature |
|---|---|---|---|
| Full-file sha256 + mutagen read per file | plan creation (add/organize/refresh), **apply preconditions**, check (×2 with READY plan) | 1–2 TB read per full pass ≈ hours | Physical floor unless skipped; apply/check re-reads are intentional safety gates |
| SQLite connection churn: fresh connect + close per UoW scope ⇒ **WAL checkpoint on every close** | apply dominates (3 scopes/action → 150k scopes per 50k-move run) | ~9 min vs ~80–95 s floor (measured 3.68 → 0.76 ms/txn, 3.6–4.8×) | Pure overhead; commit boundaries/durability unaffected |
| Plan-creation domain CPU + persistence | add/organize/refresh | ~4–5 s per 50k tracks | ~1 s provably wasted (PathPolicy, re-normalization) |
| CLI cold start | every invocation | ~240–290 ms, ~half is FastAPI/uvicorn imports 11/12 commands never use | Fixed tax on the daily path |
| Web plan-creation response | POST /api/plans/* | 15–25 MB JSON at 50k actions, discarded by client | Dead payload |

Key finding the segment analyses converge on: **hashing I/O is the dominant axis everywhere**, and `apply` re-hashes every source file before each move ([apply_plan.py:238-255](src/omym2/features/apply/usecases/apply_plan.py#L238-L255)) — that is the SOURCE_CHANGED gate, deliberately kept and excluded from the implemented opt-in lane.

## Settled constraints (honored throughout; do not re-litigate)

- Per-action write-ahead commit boundary (PENDING FileEvent committed before each move): permanent. `synchronous=FULL`: permanent. WAL: already enabled 2026-07-10.
- plan→apply content-hash cache keyed by size+mtime: not implemented. Apply always performs full source verification; stat trust is limited to explicit organize/refresh/check CLI flags.
- executemany for plan-creation inserts: rejected 2026-07-05; re-measured — real insert cost is Python-side value marshaling in `save()`, not SQL dispatch, so the rejection stands.

---

## Phase 0 — Measurement baseline (prerequisite)

**B0. Benchmark harness.** At analysis time no perf infrastructure existed (`scripts/checks.sh` was lint/type/test only). Add a small script that generates a synthetic library (config: N tracks, file size, album shape) and times add / organize / apply / check end-to-end, printing a per-stage breakdown. Run once before Phase 1 to establish real-machine baselines and after each phase to verify.
Effort M. No behavior risk. Owner doc: `docs/DEVELOPMENT.md`.

Baseline recorded before Phase 1 with `uv run python scripts/benchmark_pipeline.py --tracks 100 --file-size-bytes 1048576 --tracks-per-album 10` on `/tmp`:

| Stage | Baseline |
| --- | ---: |
| add | 0.377248 s |
| apply | 0.522452 s |
| organize | 0.369792 s |
| check | 0.371466 s |
| measured total | 1.640958 s |

Matched post-Phase-2 run on the same `/tmp` filesystem and dataset:

| Stage | Baseline | After Phases 0-2 | Change |
| --- | ---: | ---: | ---: |
| add | 0.377248 s | 0.286670 s | -24.0% |
| apply | 0.522452 s | 0.248130 s | -52.5% |
| organize | 0.369792 s | 0.260894 s | -29.4% |
| check | 0.371466 s | 0.259428 s | -30.2% |
| measured total | 1.640958 s | 1.055122 s | -35.7% |

The completed harness also adds a READY-refresh-Plan overlap stage so P1-3 is exercised directly. Its post-implementation `check_ready_plan` result was 0.264255 s versus 0.259428 s for the clean check; no pre-P1-3 value exists for that added stage.

## Phase 1 (P0) — Small, zero-behavior-change wins

All S effort, independently committable, no crash-safety interaction. Expected combined effect: daily `add`+`apply` fixed costs roughly halved; plan-creation CPU −~1s/50k; two full-table scans eliminated.

| # | Change | Where | Impact | Trade-offs |
|---|---|---|---|---|
| P0-1 | Lazy-import web stack: move `build_web_app` import into the lambda; move `import uvicorn` into the settings command function. Optionally lazy per-command dispatch in CLI main. | [cli_composition.py:33](src/omym2/platform/cli_composition.py#L33), [settings.py:14](src/omym2/adapters/cli/commands/settings.py#L14), [main.py:13-24](src/omym2/adapters/cli/main.py#L13-L24) | ~½ of the 240–290 ms cold start, for 11 of 12 commands, every invocation | None functionally; full lazy dispatch (M) touches typing imports |
| P0-2 | Plan-creation POSTs return header-only response (client provably discards the action array; GET was already migrated in c3fc447 — the POSTs were missed) | [api.py:1595-1616](src/omym2/adapters/web/routes/api.py#L1595-L1616), TS `PlanCreatedDetail` | Removes 15–25 MB serialize+transfer per large plan created from Web | Contract change in `docs/contracts/web-api.md` (owner) + TS type update |
| P0-3 | Undo: keep the `list_by_plan` result currently discarded after an `any()` check; build `{action_id: action}`; replace per-event `plan_actions.get()` | [create_undo_plan.py:66-69](src/omym2/features/undo/usecases/create_undo_plan.py#L66-L69), :193 | ~0.5–0.6 s per 50k-event undo (measured); found independently by two analyses | None; per-event `tracks.get()` measured a non-issue on embedded SQLite — bundle only for consistency |
| P0-4 | Index migration: **add** `idx_check_issues_check_run_id` (EXPLAIN-verified scan→covering-index) and `idx_file_events_library_status (library_id, status, sequence_no)` (check's `list_pending_by_library` currently full-scans an append-only log); **drop** `idx_tracks_library_id` and `idx_plans_library_id` (both EXPLAIN-verified subsumed by composite indexes) | migrations/ | Kills 2 recurring scans; ~20% less index maintenance on every per-move `tracks` write | Re-verify EXPLAIN on the live migrated DB before merging (agent tested a reconstructed schema) |
| P0-5 | PathPolicy: skip computing template fields the configured template doesn't use (reuse `_template_uses_placeholder` from config_fingerprint.py); add per-instance memo dict for `sanitize_*`/`generate_artist_id` (500 artists / 2k albums, not 50k) | [path_policy.py:83-93](src/omym2/domain/services/path_policy.py#L83-L93) | ~0.3 s/50k unconditionally under the default template (artist_id is computed and unused); memo: 28.6× on generate_artist_id | Cache must be instance-scoped, not a global lru_cache — the web process is long-lived |
| P0-6 | file_mover: memoize parent dirs already ensured this run; skip repeat `mkdir` | [file_mover.py:34](src/omym2/adapters/fs/file_mover.py#L34) | Replaces the repeated existing-directory `mkdir` path with one cached-directory validation, saving roughly one metadata syscall per repeated parent | The validation preserves behavior if a cached directory is removed and does not retry a missing source; keep the known TARGET_EXISTS mislabel note in mind if touching adjacent lines |
| P0-7 | Organize initially passed the scanner's stat result into snapshot capture instead of re-stat'ing. Phase 3 supersedes this for full captures because their fresh stat now becomes a persisted trust baseline; only an eligible trusted snapshot reuses scan stat. Add's second stat remains untouched. | [file_snapshot_reader.py:29](src/omym2/adapters/fs/file_snapshot_reader.py#L29) + organize call site | Negligible on ext4; ~90 s per 50k on drvfs mounts before baseline persistence changed the safety requirement | The full-capture port remains path-only; trusted-snapshot reconstruction occurs in domain/usecase code above the adapter |
| P0-8 | check: for unmanaged-file duplicate candidates, hash directly instead of full `capture()` (metadata_hash is unused there) | [check_library.py:179-184](src/omym2/features/check/usecases/check_library.py#L179-L184) | Saves one mutagen open+read per unmanaged file | None |

## Phase 2 (P1) — Structural wins, still zero behavior change

**P1-1. Reuse the SQLite connection across UnitOfWork scopes (M/L) — the largest safe DB win.**
Every `with uow:` opens a fresh connection and closes it ([unit_of_work.py:110-152](src/omym2/adapters/db/sqlite/unit_of_work.py#L110-L152)). Because the app is single-connection, every close is a "last connection close", which makes SQLite run a **full WAL checkpoint on every transaction** (verified empirically: WAL truncates to 0 after each close; with a keepalive connection it grows to ~4 MB and checkpoints on the normal threshold). Measured 3.68 → 0.76 ms/txn (3.6–4.8×). A 50k-move apply spends ~9 min here vs ~80–95 s at the true 2-commits-per-action floor.
Change: keep one connection for the UoW object's lifetime; each `with` scope still does its own BEGIN/COMMIT exactly as today; dispose at usecase end; consider `PRAGMA wal_checkpoint(TRUNCATE)` at run end.
Crash-safety: **no interaction** — commit count, ordering, and `synchronous=FULL` unchanged; the only delta is a larger (bounded, well-formed, replayable) WAL between checkpoints.
Preconditions: confirm UoW instances are never shared across threads (construction is per-request in `feature_composition.py`; full web call-stack trace still to do). Update `docs/STORAGE.md` "DB Consistency" (owner) with connection-lifetime + checkpoint rationale.
Side benefit: also removes the per-scope `ensure_database_migrated()` re-check and PRAGMA replay for every command, not just apply.

**P1-2. Parallelize snapshot capture with a bounded, order-preserving thread pool (M) — the largest safe I/O win.**
Capture loops in add/organize/refresh plan creation and check's `_track_issues` are strictly sequential; `hashlib` releases the GIL (measured ~5× at 8 threads on hash CPU), and stat/open latency overlaps near-linearly on drvfs. Adapters involved are frozen/stateless; DB work already sits entirely outside these loops.
Requirements: results collected by input index (Plan review order / `sort_order` determinism), identical per-file exception→blocked-candidate mapping, bounded worker count (config constant; default ~4–8).
Expected: multi-× on the dominant cost of every full-library read pass; disk-bound media may cap gains on HDD, NVMe and drvfs benefit most.
Exclusion: **not** for apply's precondition loop — the hash→move window per action must stay tight.

**P1-3. check: intra-run snapshot memo (S/M).**
`_track_issues` captures every managed file; `_plan_source_issues` re-captures the same files when a READY organize/refresh plan exists (sources are library paths — full overlap; add-plan sources are Incoming paths — disjoint). A per-invocation `{path: snapshot}` memo halves check I/O in that case.
Behavior note: check would observe each file once per run instead of twice at slightly different instants; the persisted report is already a point-in-time observation, so this is a benign tightening — state it in `docs/execution/check.md` when implementing.

## Phase 3 (P2) — The big lever, implemented as an explicit conservative opt-in

**P2-1. Persisted size+mtime baseline + opt-in `--trust-stat` fast path.**

The approved policy is deliberately narrower than the original design space:

- nullable `tracks.size` / `tracks.mtime`; migration leaves existing rows null and therefore ineligible
- explicit per-invocation CLI flag on organize, refresh, and check; no TOML setting and no Web API field
- only one active Track at a unique current path with a complete exact size+mtime match is eligible
- every null, ambiguous, path-mismatching, or changed baseline falls back to a complete fresh snapshot
- organize full captures and successful apply writes populate baselines; refresh planning and check never update Tracks
- apply has no stat-trust path and always performs its recorded hash precondition

The opt-in remains in the risk family recorded on 2026-07-05: a same-size, same-mtime edit can be missed. Default behavior is unchanged, and the CLI/docs state that users should omit the flag for full integrity verification.

Matched Phase 3 runs used the same 100 × 1 MiB dataset and `/tmp` filesystem. The tiny synthetic files make fresh-process CLI startup a large part of each result, so large real files should show a larger hashing delta:

| Stage | Full hash | `--trust-stat` | Change |
| --- | ---: | ---: | ---: |
| add | 0.335500 s | 0.329626 s | -1.8% (unaffected/noise) |
| apply | 0.265054 s | 0.262773 s | -0.9% (mandatory hash/noise) |
| organize | 0.264203 s | 0.118767 s | -55.0% |
| check | 0.258852 s | 0.122758 s | -52.6% |
| measured total | 1.123609 s | 0.833924 s | -25.8% |
| check after tag mutation + READY refresh Plan | 0.258639 s | 0.259550 s | +0.4% (expected full-capture fallback) |

Final validation passed `scripts/checks.sh all`: frontend format/lint/build, Ruff lint/format, basedpyright with zero warnings, and the complete pytest suite.

## Not recommended (analyzed, with reasons — do not re-open without new evidence)

- **Fold the per-action library-root check into the pending-write transaction**: a narrower variant than the 2026-07-05 rejected "root-check folding", but after P1-1 the check costs microseconds on an open connection — not worth touching a recorded rejection. Superseded by P1-1.
- **`SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE` alone**: only ~1.1× measured; needs added checkpoint hygiene; superseded by P1-1.
- **Scope album-year/disc-total resolution to touched albums** (add/refresh currently pay a full-library pass, ~125 ms/50k, ~100× reducible): real but blocked on a pre-existing semantics question — `album_year_group()` and `_album_identity()` use slightly different missing-value fallbacks for the same conceptual key. Resolve that as a design/docs question first; only then is the filter safely expressible. Park as a follow-up ticket.
- **Remove double/triple target-path normalization** (~150 ms/50k): removes a defensive normalization that keeps CollisionPolicy/PlanAction correct regardless of caller discipline; needs an invariant type to do safely. Only bundle with adjacent work.
- **Push plans/history group-by into SQL**: bounded sub-100 ms cost, docstring-justified Python placement (dirname is a business rule); revisit only if Run-detail latency is actually observed at 50k events.
- **Undo per-event `tracks.get()` "N+1"**: measured a wash on embedded SQLite (row materialization dominates, not query dispatch, 0.96–1.16×). Fix only as consistency cleanup within P0-3.
- **Single-open mutagen+hash read**: fragile against mutagen's seek patterns, up to ~100 MB/in-flight-file buffering; payoff only meaningful on drvfs (~100 s/50k). Not worth it.
- **MusicBrainz batching/parallelism**: 1 req/s is the API policy floor; already-resolved names are already skipped via config entries.
- **Anything on the permanent NG list**: commit-boundary merging, `synchronous=NORMAL`, default-on hash caching.

## Modeled end-state (validate against Phase 0 baselines)

| Scenario (ext4, ~30 MB files) | Today (modeled) | After P0+P1 | After P2-1 (opt-in, clean library) |
|---|---|---|---|
| Daily: add 100 files + apply | ~30–35 s (capture 2×15 s, DB ~1.1 s, startup 0.27 s, domain ~1 s) | ~15–18 s (parallel capture, DB ~0.25 s, startup ~0.13 s) | Same as P0+P1; apply hashing stays mandatory |
| organize, 50k tracks (~1.5 TB) | hours (sequential read+hash) | ÷ pool factor (≈¼ on NVMe/drvfs) | minutes (stat-only when clean) |
| apply, 50k moves | ~re-read hours + ~9 min DB | same hashing + ~1.5–2 min DB | Same as P0+P1; no stat bypass |
| check, 50k clean Tracks | one full read | one full read ÷ pool factor | minutes (stat-only) |
| check after external edit + READY refresh Plan | ~2× full read | ~1× (memo) ÷ pool factor | Same as P0+P1 because stat mismatch fails closed to full capture |

## Roadmap

1. **Phase 0** (1 session): benchmark harness + real-machine baseline. Gate: numbers recorded in the harness doc.
2. **Phase 1** (1–2 sessions): P0-1 … P0-8 as independent commits, each with tests + owning-doc updates per repo convention. Gate: `scripts/checks.sh py` + benchmark delta.
3. **Phase 2** (2–3 sessions): P1-1 first (smaller blast radius, re-baseline DB layer), then P1-2, then P1-3. Each needs a short design note + `docs/STORAGE.md` / `docs/execution/check.md` updates. Gate: full checks + benchmark delta + crash-safety tests unchanged.
4. **Phase 3**: approved conservative semantics implemented with migration, CLI-only flags, fallback tests, contract docs, and matched benchmark.

Open questions parked for design tickets: album-grouping-key semantics drift (blocker for the album-pass scoping); stale-READY-plan supersede (pre-existing deferred item, unrelated to perf but adjacent to plan lifecycle work).
