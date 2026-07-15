---
type: Execution Spec
title: Organize Execution
description: Defines organize registration and artist-name reconciliation diagnostics, Plan creation, and the explicit unique-Track size+mtime trust-stat optimization and fallback rules.
tags: [organize, library-registration, plan-creation, artist-names, path-policy]
timestamp: 2026-07-16T00:44:26+09:00
---

# Organize Execution

This document is authoritative for `organize --library PATH`, first Library registration, existing Library rescan, unregistered path refusal, clean Library registration without mutation plan, organize Plan creation, and registration after successful apply.

Common execution rules are in [model.md](model.md). Path identity rules are in [../contracts/path-identity-storage.md](../contracts/path-identity-storage.md).

## Library Registration Behavior

Library identity is defined in [../DOMAIN.md](../DOMAIN.md#library).

Registration is per Library and is tied to:

* `library_id`
* `path_policy_hash` or an equivalent identity for the current PathPolicy

Registration is not defined by whether the `tracks` table has rows.

Minimum representative registration fields:

* `library_id`
* `root_path`
* `path_policy_hash`
* `registered_at`
* `status`

Allowed status values are in [../contracts/status-reason-catalog.md](../contracts/status-reason-catalog.md#library-status).

Changing PathPolicy invalidates prior registration for that Library. After a PathPolicy change, `add` refuses to create a plan until the Library is registered again under the new PathPolicy. The expected remedy is `omym2 organize --library PATH`.

`organize` is the only supported path for an unregistered or unorganized Library to become usable by `add`.

`organize --library PATH` is the primary user-facing operation for registering and reconciling a Library.

Relink rules are defined in [../contracts/path-identity-storage.md](../contracts/path-identity-storage.md#identity-rules).

## Organize Behavior

`organize --library PATH` scans the specified Library read-only and computes canonical paths under the current PathPolicy.

For every otherwise valid snapshot, organize batches raw artist and
album-artist values through the shared `ArtistNameResolutionReader` before
canonical path generation. This lets organize reconcile paths after either an
exact preference or accepted provider name changes without rewriting stored
Track metadata. Library selection and Track reads finish before resolver work;
result persistence begins only after resolver work has completed.

When a resolved candidate becomes a PlanAction, Organize records its aligned
artist and album-artist resolution diagnostics on that action. Already-correct
files create no action or standalone diagnostic row, and candidates blocked
before resolution record no pair.

The scan always covers the whole Library and only ever plans misplaced (current path differs from the canonical target path) or blocked files; already-correctly-placed files never become Plan actions.

In the MVP, `organize --library PATH` supports these identity cases:

| Case | Policy |
| --- | --- |
| `PATH` matches an existing `libraries.root_path` | Rescan and organize the existing Library. |
| No Library exists yet | Create the first Library row and organize it. |
| `PATH` is unregistered while another Library already exists | Stop with a clear message. The path may be a moved Library or a second Library, and both are out of MVP scope. |

The MVP must not silently duplicate a Library when an unregistered path may represent an existing Library.

Plain `omym2 organize` is allowed only when exactly one known Library can be selected unambiguously. Otherwise it fails with a clear message and asks for `omym2 organize --library PATH`.

If files need to move or blocking actions must be reviewed, `organize` creates an organize Plan. `organize` does not move files directly except through `--apply` orchestration.

If no moves are needed and no blocking issues exist, `organize` can register the Library without creating a mutation Plan because DB-only Library state updates are not Library music file mutations.

If the organize Plan is applied successfully and no blocking Library-state issues remain, the Library becomes registered. Updating Library state after apply is a DB-only state change and does not create a FileEvent.

If blocked actions remain, the Library must not become registered.

Blocking issues include:

* missing required metadata
* canonical path conflicts
* invalid paths
* missing source files
* other problems preventing safe acceptance

## Trust-Stat Optimization

`omym2 organize --trust-stat` is an explicit CLI-only performance opt-in. The Web organize route always uses full snapshot capture.

One scanned source is eligible only when all of these conditions hold:

* exactly one active Track in the Library has that `current_path`
* the Track logical path and the scanner observation path match the source being evaluated
* both persisted Track `size` and `mtime` values are non-null
* current size and modification time exactly equal that persisted baseline

For an eligible source, organize may reconstruct the FileSnapshot from the scanner stat plus the Track's last verified hashes and metadata. Every null, ambiguous, path-mismatching, or changed baseline falls back to a complete snapshot that performs a fresh stat, metadata read, and content hash. Full captures do not reuse the earlier scan observation when establishing the persisted baseline.

When an eligible source is accepted, organize updates that same unique active Track identity. Removed Track records that share the source path remain removed.

Accepted organize candidates persist their snapshot size and modification time. This backfills existing null baselines only after full verification; an eligible trusted candidate preserves its already verified baseline.

The opt-in can miss a content or metadata edit that preserves both size and modification time. Users who need full integrity verification omit the flag. If `--apply` is also selected, apply still performs its mandatory full source-hash precondition before any Track update or Library music file mutation.
