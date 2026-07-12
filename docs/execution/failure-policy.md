---
type: Execution Spec
title: Failure Policy
description: Catalogs cross-cutting execution failure cases, such as target conflicts, missing metadata, duplicate hashes, and stale Library roots, and the policy applied to each.
tags: [failure-policy, blocked-vs-failed, conflicts, error-handling]
timestamp: 2026-07-13T00:31:39+09:00
---

# Failure Policy

This document is authoritative for cross-cutting execution failure rules.

Common execution rules are in [model.md](model.md). Apply-time state transitions are in [apply.md](apply.md). Allowed values are cataloged in [../contracts/status-reason-catalog.md](../contracts/status-reason-catalog.md).

## Scope

The blocked-vs-failed distinction is defined in [model.md](model.md#blocked-vs-failed). Allowed action types, statuses, and reasons are defined in [../contracts/status-reason-catalog.md](../contracts/status-reason-catalog.md).

After a Run starts, [Apply Execution](apply.md#run-status) defines its
`partial_failed` and `failed` aggregation rules. Blocked and `skip` actions do
not count toward either result.

## Failure Cases

| Case | Policy |
| --- | --- |
| target conflict during plan creation | block the PlanAction with `target_exists`; do not overwrite automatically. [add.md](add.md#target-collision-safety) owns add's planning matrix. |
| target is occupied when a move is attempted at apply | do not overwrite. The failed move records a failed FileEvent and PlanAction with `target_exists`; terminal Run and Plan status follows the rule above. |
| metadata is insufficient during plan creation | block the PlanAction |
| duplicate hash exists | skip candidate with `duplicate_hash` as the reason |
| source file missing during plan creation | block the PlanAction |
| source file missing at apply | fail the PlanAction; terminal Run and Plan status follows the rule above |
| source hash changed during plan creation | block the PlanAction |
| source hash changed after plan creation at apply | fail the PlanAction; terminal Run and Plan status follows the rule above |
| current Library root differs from `library_root_at_plan` | handle according to [apply-time precondition failures](apply.md#apply-time-precondition-failures) |
| failure during move after its pending FileEvent is recorded | mark the FileEvent and PlanAction as failed; terminal Run and Plan status follows the rule above |
| tag mistake after apply | relocate with refresh |
| undo destination is occupied during plan creation | block the undo PlanAction with `target_exists`; do not overwrite automatically |
| DB and filesystem are out of sync | detect with check |
| pending FileEvent exists | report through check and require manual review |
| worker dispatch fails or restart finds an unfinished Operation | mark the Operation `interrupted`; reconcile the Plan/Run from durable evidence; leave pending FileEvents pending; mark planned `skip` actions `applied`, planned `move` and `refresh_metadata` actions `failed` with `operation_interrupted`, and blocked actions unchanged; never resume automatically |
| add requested when no sole registered Library can be selected | reject add plan creation; no Plan, Run, or FileEvent |
| PathPolicy changed after a Library was registered | mark or report that Library as stale; require organize before add |
