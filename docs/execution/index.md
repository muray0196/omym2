# Execution

Use this file as the execution router. Read the focused file for the task.

* [Execution Model](model.md) - Common Plan/Run/FileEvent model: shared exclusive lock, single-use Plans, blocked-vs-failed, durable mutation log.
* [Failure Policy](failure-policy.md) - Cross-cutting failure case catalog mapping each planning, apply, undo, and interruption failure to its policy.
* [Add Execution](add.md) - Add planning rules: incoming scan, companion claims, unprocessed leftovers, collision blocks, registered-Library gate.
* [Organize Execution](organize.md) - Organize registration and reconciliation for audio and companions, clean DB-only registration, and trust-stat rules.
* [Refresh Execution](refresh.md) - Refresh re-evaluation after tag correction, relocation and metadata-only actions, companion movement, and trust-stat rules.
* [Apply Execution](apply.md) - Apply acceptance and execution flow, status transitions, precondition failures, and interruption reconciliation.
* [Undo Execution](undo.md) - Undo eligibility, deduplication, reverse provenance, external restore targets, and companion/unprocessed reversal rules.
* [Check Execution](check.md) - Diagnostic Check execution, CheckIssue scope, findings persistence, and trust-stat scope.
