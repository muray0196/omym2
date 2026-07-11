# Execution

Use this file as the execution router. Read the focused file for the task.

* [Execution Model](model.md) - Defines the common Plan-centered execution model shared by all commands, covering Plan/PlanAction/Run/FileEvent behavior, single-use Plan policy, the blocked-vs-failed distinction, and the durable operation log principle.
* [Failure Policy](failure-policy.md) - Catalogs cross-cutting execution failure cases, such as target conflicts, missing metadata, duplicate hashes, and stale Library roots, and the policy applied to each.
* [Add Execution](add.md) - Defines add plan creation from an Incoming/source scan against the sole registered Library, including duplicate-hash skips, missing-metadata and target-conflict blocks, and add --apply orchestration.
* [Organize Execution](organize.md) - Defines organize registration and reconciliation, Plan creation, and the explicit unique-Track size+mtime trust-stat optimization and fallback rules.
* [Refresh Execution](refresh.md) - Defines refresh target re-evaluation, move versus metadata actions, stable Track identity, and the explicit size+mtime trust-stat optimization and fallback rules.
* [Apply Execution](apply.md) - Defines apply state transitions, mandatory full source verification, verified Track baseline writes, FileEvent ordering, and Library-root preconditions.
* [Undo Execution](undo.md) - Defines per-Run undo, terminal Run requirements, refresh_metadata rejection, reverse FileEvent tracing, restore-destination conflict handling, and external restore Track removal.
* [Check Execution](check.md) - Defines persisted check diagnostics, point-in-time snapshot reuse, the explicit trust-stat optimization, unmanaged hashing, and the Track no-mutation boundary.
