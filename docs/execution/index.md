# Execution

Use this file as the execution router. Read the focused file for the task.

* [Execution Model](model.md) - Defines the common Plan-centered execution model shared by all commands, covering Plan/PlanAction/Run/FileEvent behavior, single-use Plan policy, the blocked-vs-failed distinction, and the durable operation log principle.
* [Failure Policy](failure-policy.md) - Catalogs cross-cutting execution failure cases, such as target conflicts, missing metadata, duplicate hashes, and stale Library roots, and the policy applied to each.
* [Add Execution](add.md) - Defines add plan creation from an Incoming/source scan against the sole registered Library, including duplicate-hash skips, missing-metadata and target-conflict blocks, and add --apply orchestration.
* [Organize Execution](organize.md) - Defines organize --library PATH behavior for first Library registration, existing Library rescan, unregistered-path refusal, and registration timing relative to plan creation and apply.
* [Refresh Execution](refresh.md) - Defines the refresh command for re-evaluating file/directory/all targets after external tag correction, including metadata reload, canonical path recalculation, move vs refresh_metadata plan action selection, and stable track_id preservation.
* [Apply Execution](apply.md) - Defines the apply flow and the Plan, PlanAction, Run, and FileEvent state transitions, including library_root_at_plan checks and apply-time precondition failures.
* [Undo Execution](undo.md) - Defines per-Run undo, terminal Run requirements, refresh_metadata rejection, reverse FileEvent tracing, restore-destination conflict handling, and external restore Track removal.
* [Check Execution](check.md) - Defines the read-only check command that reports DB/filesystem inconsistencies, Library state, and CheckIssue scope without mutating anything.
