---
name: plan-apply-safety
description: Safety checklist for any change that can affect Plan, PlanAction, Run, FileEvent, apply, undo, refresh, or any Library music file mutation. Use before designing or reviewing such a change.
---

# Plan / Apply Safety

Highest-risk area of OMYM2: mistakes here move or lose user music files.
Authoritative docs: `docs/execution/model.md`, `docs/execution/apply.md`,
`docs/execution/failure-policy.md`, `docs/contracts/operations.md`,
`docs/contracts/status-reason-catalog.md`.

## Read first (in this order)

1. `docs/execution/model.md`
2. The doc for the command you touch: `docs/execution/{apply,undo,refresh,organize,add,check}.md`
3. `docs/execution/failure-policy.md`
4. `docs/contracts/operations.md`
5. `docs/contracts/status-reason-catalog.md` — only the statuses/reasons listed there may be persisted

## Non-negotiable invariants

1. Every Library music file mutation flows through a Plan. There is no direct-mutation path. If the requested design mutates files without a Plan, stop and report.
2. Apply executes the **recorded** PlanActions. It never recalculates target paths from the current AppConfig, and it resolves paths against `library_root_at_plan`.
3. FileEvent ordering per mutation attempt:
   1. check preconditions
   2. persist FileEvent as pending — **before** the mutation
   3. perform the mutation
   4. update the FileEvent with the outcome
   5. update Track / PlanAction only after the confirmed result
4. Failure classes are distinct and must stay distinct in code, statuses, and tests:
   - blocked at plan time
   - failed before the mutation attempt
   - failed after the mutation attempt
5. Blocked actions stay blocked; nothing "retries" a blocked action implicitly.
6. Refresh updates Track / FileEvent / Plan state only through the documented contracts, never by ad-hoc reconciliation.
7. Apply acceptance holds the shared exclusive lock and atomically commits the
   `ready -> applying` compare-and-set, running Run, and queued Operation before
   worker dispatch. No read-then-upsert start path is permitted.
8. A crash or unobserved mutation outcome leaves its FileEvent `pending`.
   Reconciliation must not infer success/failure from filesystem state or
   rewrite the Plan to `ready`.

## Procedure

1. Read the docs above, in the listed order.
2. Check the design against every non-negotiable invariant above.
3. Every PlanAction carries stored `source_path`/`target_path`, so this skill and `path-identity-safety` always co-trigger together: follow this skill's execution-semantics checks first, then apply `path-identity-safety`'s stored-path invariants throughout the work.
4. Work through the Done means checklist below before declaring the change safe.

## Done means

- [ ] Can this change mutate a Library music file? If yes, is every mutation inside a Plan-centered flow?
- [ ] Are all Plan / PlanAction / Run / FileEvent state transitions among those allowed in the status catalog?
- [ ] Is the FileEvent written as pending before any mutation code runs?
- [ ] Are the three failure classes handled and persisted differently?
- [ ] Does apply read only recorded PlanActions (grep for AppConfig / PathPolicy usage inside apply)?
- [ ] Does one transaction claim the Plan, create the Run, and reserve the
  Operation before dispatch, while the shared lock remains held?
- [ ] Can restart/dispatch reconciliation leave pending FileEvents pending and
  derive Plan/Run state only from durable evidence?
- [ ] Every changed contract edge has a test per `docs/TESTING.md`'s Contract Change Test Requirements table, Execution contract row.

## Stop and report when

- Any invariant above must be bent to satisfy the request.
- A new status or reason value is needed (it requires a `status-reason-catalog.md` contract change first).
- Atomicity between DB and filesystem is assumed anywhere — it does not exist; FileEvents are the durable log that bridges the gap.
