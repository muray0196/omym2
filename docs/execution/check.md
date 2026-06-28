# Check Execution

This document is authoritative for read-only check behavior, DB / filesystem inconsistency reporting, Library state reporting, CheckIssue scope, and pending FileEvent reporting.

Common execution rules are in [model.md](model.md). CheckIssue values are cataloged in [../contracts/status-reason-catalog.md](../contracts/status-reason-catalog.md#checkissue-issue-type).

## Check Behavior

`check` is read-only in the initial version. It reports inconsistencies between the DB and the filesystem and reports Library state.

`check` may report whether the Library is `registered`, `unregistered`, `stale`, or `blocked`.

`check` is diagnostic. It does not replace `organize`, and `add` should not absorb full `check` responsibilities.

Reported issues include:

* missing DB files
* unmanaged files
* changed hashes
* path differences
* duplicate candidates
* pending file_events
* Library state issues

The CheckIssue model is defined in [../domain.md](../domain.md#checkissue).
