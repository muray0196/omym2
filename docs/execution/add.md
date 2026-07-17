---
type: Execution Spec
title: Add Execution
description: Defines Add planning for incoming audio, companions, and opt-in unprocessed leftovers, including claim precedence, rooted exclusions, full persistence, preview-only limits, and apply orchestration.
tags: [add, plan-creation, library-registration, artist-names, companions, unprocessed, apply]
timestamp: 2026-07-17T22:43:57+09:00
---

# Add Execution

This document is authoritative for Add Plan creation, Incoming/source scan
behavior, companion claims, the registered Library gate, duplicate-hash skips,
review-time blocks, and `add --apply` orchestration.

Common execution rules are in [model.md](model.md). Apply rules are in [apply.md](apply.md). Command syntax is summarized in [../COMMANDS.md](../COMMANDS.md).

## Add Plan Behavior

`add` is the daily entry point. It scans Incoming or a specified source directory, creates an add plan, and leaves the user to review and apply it.

In the MVP, `add` targets the sole registered Library. If no registered Library exists or Library selection is ambiguous, `add` refuses to create an add plan. The user-facing remedy is `omym2 organize --library PATH`.

`add` must not perform existing-Library organization and must not mix Incoming import actions with existing Library organization actions. It must not register, reconcile, or relink a Library.

`add` should not perform a full Library-wide organizedness check every time. Its gate is Library registration, not repeated canonical path validation across the entire Library.

Add does perform one narrow artist-name reconciliation guard. When an
otherwise executable incoming move uses a changed resolved source key, Add
recalculates the affected active Library Tracks from their already-loaded raw
metadata using the shared original-to-English mapping. Album-year and disc
inference use active Library Tracks plus otherwise
executable incoming moves; duplicate skips and blocked actions do not influence
this reconciliation context. If the resolved name would change an existing
Track's canonical path and that Track has not already been reconciled to the
resolved current and canonical path, Add stops without creating a Plan and
directs the user to run `organize`.

The guard ignores removed Tracks, duplicate skips, blocked incoming actions,
and name changes that the active path template does not consume. It does not
resolve unrelated Library artists, scan Library files, or replace Organize's
full reconciliation responsibility.

```text
Incoming folder
  ↓
scan
  ↓
create plan
  ↓
review
  ↓
apply
  ↓
Library
```

## Plan Creation

The add plan creation behavior includes:

* scan Incoming or specified source
* capture file snapshots
* generate target canonical paths
* check duplicate hashes against known active Library tracks and skip duplicates with `duplicate_hash`
* block missing required metadata for incoming files
* block target conflicts according to [Target Collision Safety](#target-collision-safety)
* request complete regular-file source inventory only when companion or
  unprocessed processing is enabled; when both are disabled, preserve the
  native audio-only planning path, including its Windows behavior
* classify companion claims whenever either feature requests inventory; when
  companion processing is enabled, create reviewed lyrics/artwork actions
  after their audio actions, otherwise retain classification only
* when unprocessed collection is enabled, classify every remaining eligible
  regular file only after audio and companion classification claims, and
  record one reviewed content-only action per leftover
* refuse mixed artist naming when an executable incoming move proves that an active existing Track requires Organize reconciliation
* persist the Plan, every PlanAction, and companion dependency edges; a result
  preview limit never drops actions

REMOVED Library tracks are excluded from duplicate-hash and target-conflict judgment, matching refresh, check, and album-year resolution.

The Plan records the exact selected source directory as
`source_root_at_plan`. External companion and unprocessed snapshots and later
Apply/Check/Undo observations must remain anchored below that root.

Before target generation, eligible candidate artist and album-artist values are
sent as one ordered batch through the shared `ArtistNameResolutionReader`.
PathPolicy receives the aligned resolved projection; raw snapshot metadata and
artist-ID lookup keys remain unchanged. The Library/Track read transaction is
closed before resolution begins, and the Plan is persisted in a later
transaction, so provider work cannot extend a Plan DB transaction.
A positive automatic mapping write may commit before the reconciliation guard
refuses Add; that reusable provider result is intentional, and the required
Organize run consumes it when calculating the Library-wide reconciliation.

Every Add action whose candidate reached this resolution step records the
aligned artist and album-artist source, resolved value, provenance, and issue as
review diagnostics. Candidates blocked before resolution record no diagnostic
pair. Duplicate skips and later target-conflict blocks retain the resolution
evidence that informed their recorded target calculation.

## Companion Planning

Whenever companion or unprocessed processing requests regular, non-symlink
source inventory, Add applies the shared deterministic
[Companion Association](../DOMAIN.md#companion-association) policy to establish
claims:

* one unambiguous same-stem `.lrc` becomes one `move_lyrics` action after
  its audio owner;
* each associated `.jpg` or `.png` source becomes one
  `move_artwork` action, preserving its basename below the one common target
  directory;
* artwork records one deterministic semantic owner and durable dependencies on
  every associated audio action.

Companions use rooted content-only snapshots. Their actions record
`content_hash_at_plan`, leave `metadata_hash_at_plan` null, and preallocate
`companion_asset_id`; no CompanionAsset row is created during Add planning.
Ambiguous ownership or target parents, a blocked owner, failed observation, or
a target conflict produces a reviewable blocked companion action. A companion
whose owner is blocked uses `companion_owner_blocked`; ambiguous association
uses `companion_association_ambiguous`.

When companion processing is disabled, newly classified claims create no
companion actions, dependencies, asset IDs, or content snapshots. If
unprocessed processing is enabled independently, those classification-only
claims still reserve recognized `.lrc`, `.jpg`, and `.png` entries from
leftovers. This toggle does not delete or alter managed companion state, change
recorded Plan sources or events, or suppress recorded recovery, History, Check,
or Undo diagnostics.

### Failed Companion Recovery

Add may create a new companion-only Plan for an external source left by a
definitively failed companion action. Eligibility requires the same evidence
as `failed_companion_source_exists`: a terminal failed/partially failed source
Plan, definitive failure evidence with no pending companion FileEvent,
succeeded owning audio provenance, and an active same-Library owner Track. The
selected Add root must exactly match the source Plan's retained
`source_root_at_plan`, and the source must still exist safely below it.

The recovery action reuses the recorded companion identity and existing owner
Track. Its audio work already succeeded in the earlier Run, so the new Plan
does not invent an owner audio action or dependency. This is reviewed
replanning, not automatic retry; unknown pending outcomes are never eligible.

## Unprocessed Planning

Unprocessed collection runs only when `unprocessed.enabled` is true for this
new Add Plan. When false, Add creates no `move_unprocessed` actions or
content-only leftover observations. Changing the setting later does not alter
the recorded Plan.

The selected source root must remain outside the Library. Inventory is
regular-file-only and no-follow. The destination subtree, nested Library,
OMYM2-owned Config/data/log paths, and numeric rotated logs are excluded as
defined by
[Add Source Inventory And Collection Protection](../contracts/path-identity-storage.md#add-source-inventory-and-collection-protection).
The application root itself is not a blanket exclusion; ordinary siblings of
the exact protected paths remain candidates.

Claim precedence is deterministic:

1. every music-scanner claim, including blocked and duplicate-skip audio;
2. every lyrics/artwork classification claim, including reservation-only and
   blocked claims or claims merged into failed-companion recovery; and
3. only then the remaining inventory as unprocessed leftovers.

Each leftover receives a rooted content-only snapshot. Its action is
trackless, companion-free, dependency-free, and metadata-free. Source and
target are absolute, with the target shaped exactly as
`<source-root>/<unprocessed.directory>/<source-relative-path>`. Missing,
unstable, unreadable, or invalid observations remain visible as blocked actions
with `source_missing`, `source_changed`, or `invalid_path`. A target entering
the Library or an internal protected path is blocked with `invalid_path`; any
existing target entry, including a dangling symlink, is blocked with
`target_exists`.

Actions are appended after audio and companion actions in deterministic source
order, and every candidate is persisted. The Plan summary records both
`unprocessed_actions` and `unprocessed_preview_limit`. The latter controls only
the deterministic CLI result excerpt described in
[Commands](../COMMANDS.md#add); normal Plan review, Apply, and API pagination
still expose the complete action set.

## Target Collision Safety

This section is authoritative for add-time target-conflict checks. The
[Path Identity And Storage Contract](../contracts/path-identity-storage.md#pathresolver-boundary)
owns stored target-path representation and normalized comparison; [apply.md](apply.md)
owns the final no-overwrite guard and its state transitions.

For an add candidate that is otherwise a planned `move`, the candidate becomes
a `blocked` PlanAction with reason `target_exists` when any of the following is
true:

| Planning observation | Required result |
| --- | --- |
| An active Track in the target Library has the same normalized `current_path` as the generated target. | Block the candidate. REMOVED Tracks do not occupy a target for this DB check. |
| Two or more otherwise eligible audio or companion move candidates in the same add batch resolve to the same normalized target. | Block every candidate that claims that target. |
| A filesystem entry already exists at the generated target after it is resolved against the Library root. | Block the candidate, even when no Track records that path. |

The logical comparisons are exact normalized Library-root-relative string
matches. They intentionally do not fold case or Unicode; the path contract
defines that boundary. Add never renames a candidate or overwrites a target to
resolve a collision. Active managed CompanionAsset paths also occupy targets.

Plan-time checks can become stale. Apply therefore atomically claims the
recorded target through its exclusive-create FileMover before moving a file. A
target that exists or appears after planning fails closed: the move's FileEvent
and PlanAction become failed with `target_exists`; [failure-policy.md](failure-policy.md)
defines the resulting Run and Plan outcome.

## Registered Library Gate

`add` requires exactly one selectable registered Library in the initial version.

No registered Library, stale Library state after a PathPolicy change, or ambiguous Library selection rejects add plan creation. This creates no Plan, Run, or FileEvent.

## Direct Apply Orchestration

When direct execution is desired, `add --apply` creates and applies the plan in the same command. Confirmation skipping is represented by `ApplyOptions.yes` and shared by `apply` and commands that apply a created plan within the same command.

`add --apply` is orchestration. Add plan creation remains separate from apply behavior.
