---
name: plan-apply-safety
description: Safety checklist for any change that can affect Plan, PlanAction, Run, FileEvent, apply, undo, refresh, or any Library music file mutation. Use before designing or reviewing such a change.
---

# Plan / Apply Safety

Highest-risk area of OMYM2: mistakes here move or lose user music files.
Authoritative docs: `docs/execution/model.md`, `docs/execution/apply.md`,
`docs/execution/failure-policy.md`, `docs/contracts/operations.md`,
`docs/contracts/status-reason-catalog.md`.

## Focused reading

This skill carries the cross-cutting invariants. Locate headings first and read
only sections that govern the changed behavior:

| Change | Read |
| --- | --- |
| Plan, Run, FileEvent, blocked/failed, or single-use semantics | Matching section of `docs/execution/model.md` |
| Command behavior | Matching section of `docs/execution/{apply,undo,refresh,organize,add,check}.md` |
| Failure timing, rollback, restart, or recovery | Matching case in `docs/execution/failure-policy.md` |
| Background lifecycle, idempotency, progress, cancellation, or reconciliation | Matching section of `docs/contracts/operations.md` |
| Persisted status or reason | Exact entity section plus Cross-Cutting Rules in `docs/contracts/status-reason-catalog.md` |

Do not preload all five documents. Only statuses/reasons listed in the catalog
may be persisted.

## Non-negotiable invariants

1. Apply resolves paths against `library_root_at_plan`.
2. FileEvent ordering per mutation attempt:
   1. check preconditions
   2. persist FileEvent as pending — **before** the mutation
   3. perform the mutation
   4. update the FileEvent with the outcome
   5. update Track / PlanAction only after the confirmed result
3. Failure classes are distinct and must stay distinct in code, statuses, and tests:
   - blocked at plan time
   - failed before the mutation attempt
   - failed after the mutation attempt
4. A crash or unobserved mutation outcome leaves its FileEvent `pending`.
   Reconciliation must not infer success/failure from filesystem state or
   rewrite the Plan to `ready`.

## Procedure

1. Route focused reading through the table above.
2. Check the design against every non-negotiable invariant above.
3. Every PlanAction carries stored `source_path`/`target_path`, so this skill and `path-identity-safety` always co-trigger together: follow this skill's execution-semantics checks first, then apply `path-identity-safety`'s stored-path invariants throughout the work.
4. Work through the Done means checklist below before declaring the change safe.

## Done means

- [ ] Are all Plan / PlanAction / Run / FileEvent state transitions among those allowed in the status catalog?
- [ ] Every changed contract edge has a test per `docs/development/testing.md`'s Contract Change Test Requirements table, Execution contract row.

## Stop and report when

- Any invariant above must be bent to satisfy the request.
- A new status or reason value is needed (it requires a `status-reason-catalog.md` contract change first).
- Atomicity between DB and filesystem is assumed anywhere — it does not exist; FileEvents are the durable log that bridges the gap.
