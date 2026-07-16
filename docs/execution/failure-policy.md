---
type: Execution Spec
title: Failure Policy
description: Catalogs cross-cutting audio, companion, and unprocessed planning, source, collision, protected-path, Undo-content, interruption, and Library-root failures.
tags: [failure-policy, blocked-vs-failed, conflicts, companions, unprocessed, error-handling]
timestamp: 2026-07-16T04:51:16+09:00
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
| target is occupied when an audio, companion, or unprocessed move is attempted at apply | do not overwrite. The failed move records a failed typed FileEvent and PlanAction with `target_exists`; terminal Run and Plan status follows the rule above. |
| metadata is insufficient during plan creation | block the PlanAction |
| duplicate hash exists | skip candidate with `duplicate_hash` as the reason |
| companion owner is unavailable/blocked or has no target during planning | block the companion action with `companion_owner_blocked`; create no managed asset |
| lyrics has multiple audio owners or artwork audio targets have different parents | block the companion action with `companion_association_ambiguous`; never guess or duplicate artwork |
| a recorded companion dependency or semantic owner is not valid and applied | fail with `companion_dependency_failed` before filesystem observation or FileEvent creation |
| source file missing during plan creation | block the PlanAction |
| source file missing at apply | fail the PlanAction; terminal Run and Plan status follows the rule above |
| source hash changed during plan creation | block the PlanAction |
| source hash changed after plan creation at apply | fail the PlanAction; terminal Run and Plan status follows the rule above |
| unprocessed source/target shape escapes its retained root, is relabelled, enters the recorded Library, or carries managed/dependency identity | block during planning when observable there; otherwise fail with `invalid_path` before observation or FileEvent creation |
| current Library root differs from `library_root_at_plan` | handle according to [apply-time precondition failures](apply.md#apply-time-precondition-failures) |
| failure during audio, companion, or unprocessed move after its pending FileEvent is recorded | mark the FileEvent and PlanAction failed; do not advance Track/CompanionAsset state; terminal status follows the rule above |
| a definitively failed companion source still exists with valid succeeded owner-audio provenance | Check reports `failed_companion_source_exists`; create a new reviewed Add Plan for an exactly rooted external source or Organize Plan for a Library-relative source; never repair automatically |
| original audio Run and later companion recovery Run both need reversal | create and Apply each Run's own Undo Plan; never attach the recovered companion to the original Run or infer a cross-Run result |
| tag mistake after apply | relocate with refresh |
| undo destination is occupied during plan creation | block the undo PlanAction with `target_exists`; do not overwrite automatically |
| companion Undo provenance, source root, owner, asset, or reverse dependency evidence is inconsistent | reject Undo Plan creation, or fail Apply with `invalid_path`/`source_changed` before mutation when current evidence changed |
| collected unprocessed content is missing or changed | Check reports an error and directs the user to History; changed content blocks Undo with `source_changed`; never repair automatically |
| a successful unprocessed move leaves an empty source directory, or its Undo leaves an empty destination directory | retain the directory; no cleanup is inferred from one file action |
| DB and filesystem are out of sync | detect with check |
| pending FileEvent exists | report through check and require manual review |
| worker dispatch fails or restart finds an unfinished Operation | mark the Operation `interrupted`; reconcile from durable evidence; leave pending FileEvents pending; mark planned `skip` actions `applied`, planned `move`, `move_lyrics`, `move_artwork`, `move_unprocessed`, and `refresh_metadata` actions `failed` with `operation_interrupted`, and blocked actions unchanged; never resume automatically |
| add requested when no sole registered Library can be selected | reject add plan creation; no Plan, Run, or FileEvent |
| PathPolicy changed after a Library was registered | mark or report that Library as stale; require organize before add |
