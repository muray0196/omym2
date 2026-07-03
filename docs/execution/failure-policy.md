---
type: Execution Spec
title: Failure Policy
description: Catalogs cross-cutting execution failure cases, such as target conflicts, missing metadata, duplicate hashes, and stale Library roots, and the policy applied to each.
tags: [failure-policy, blocked-vs-failed, conflicts, error-handling]
timestamp: 2026-06-28T19:25:33+09:00
---

# Failure Policy

This document is authoritative for cross-cutting execution failure rules.

Common execution rules are in [model.md](model.md). Apply-time state transitions are in [apply.md](apply.md). Allowed values are cataloged in [../contracts/status-reason-catalog.md](../contracts/status-reason-catalog.md).

## Scope

The blocked-vs-failed distinction is defined in [model.md](model.md#blocked-vs-failed). Allowed action types, statuses, and reasons are defined in [../contracts/status-reason-catalog.md](../contracts/status-reason-catalog.md).

## Failure Cases

| Case | Policy |
| --- | --- |
| target path exists | conflict. Do not overwrite automatically |
| metadata is insufficient during plan creation | block the PlanAction |
| duplicate hash exists | skip candidate with `duplicate_hash` as the reason |
| source file missing during plan creation | block the PlanAction |
| source file missing at apply | fail the PlanAction and mark Run as failed or partial_failed |
| source hash changed during plan creation | block the PlanAction |
| source hash changed after plan creation at apply | fail the PlanAction and mark Run as failed or partial_failed |
| current Library root differs from `library_root_at_plan` | handle according to [apply-time precondition failures](apply.md#apply-time-precondition-failures) |
| failure during move | mark file_event as failed and Run as partial_failed if prior Library music file mutations succeeded |
| tag mistake after apply | relocate with refresh |
| another file exists at undo destination | mark undo plan as conflict and do not overwrite automatically |
| DB and filesystem are out of sync | detect with check |
| pending file_event exists | report through check and require manual review |
| add requested when no sole registered Library can be selected | reject add plan creation; no Plan, Run, or FileEvent |
| PathPolicy changed after a Library was registered | mark or report that Library as stale; require organize before add |
