# Execution

Use this file as the execution router. Read the focused file for the task.

* [Execution Model](model.md) - Defines Plan-centered execution, durable Operation versus FileEvent responsibilities, shared exclusion, single-use Plans, and blocked-versus-failed behavior.
* [Failure Policy](failure-policy.md) - Catalogs cross-cutting execution failure cases, such as target conflicts, missing metadata, duplicate hashes, and stale Library roots, and the policy applied to each.
* [Add Execution](add.md) - Defines add plan creation from an Incoming/source scan against the sole registered Library, including artist-name resolution diagnostics, duplicate-hash skips, missing-metadata and target-conflict blocks, and add --apply orchestration.
* [Organize Execution](organize.md) - Defines organize registration and artist-name reconciliation diagnostics, Plan creation, and the explicit unique-Track size+mtime trust-stat optimization and fallback rules.
* [Refresh Execution](refresh.md) - Defines refresh target re-evaluation with artist-name resolution diagnostics and reconciliation safety, move versus metadata actions, stable Track identity, and the explicit size+mtime trust-stat optimization and fallback rules.
* [Apply Execution](apply.md) - Defines atomic Apply acceptance, descriptor-anchored source and target verification, state transitions, Track baseline writes, FileEvent ordering, interruption, and Library-root preconditions.
* [Undo Execution](undo.md) - Defines Undo eligibility and deduplication, reverse FileEvent tracing, Undo Plan provenance, source-observation blocks, restore conflicts, and external restore Track removal.
* [Check Execution](check.md) - Defines exclusive Check execution as a durable Operation, persisted diagnostics, snapshot reuse, trust-stat optimization, and the Track no-mutation boundary.
