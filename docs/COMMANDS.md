---
type: Command Reference
title: Commands
description: Lists the OMYM2 CLI surface, including persisted controls, companion and unprocessed Add review, deterministic result previews, diagnostics, recovery, and trust-stat flags.
tags: [cli, commands, reference, artist-names, musicbrainz, companions, unprocessed]
timestamp: 2026-07-16T05:23:14+09:00
---

# Commands

This document is authoritative for the CLI command surface. Per-command descriptions are summaries only. Detailed Plan, Run, FileEvent, and failure semantics live in [execution/](execution/), and storage details live in [STORAGE.md](STORAGE.md).

The CLI is a complete execution interface. The local Web UI is a peer inbound
surface over the same usecases and safety contracts; this document specifies
only CLI syntax and behavior.

## Command List

The current CLI surface includes:

```bash
# Settings
omym2 settings
omym2 config show
omym2 config validate
omym2 artist-ids generate [--overwrite] [--fasttext-model <path>] <artist>...

# Register or organize existing Library
omym2 organize --library <path>
omym2 organize --library <path> --apply
omym2 organize --library <path> --trust-stat
omym2 organize
omym2 organize --apply

# Add new tracks to a registered Library
omym2 add
omym2 add <source-dir>
omym2 add --apply
omym2 add --apply --yes

# Plans and apply
omym2 plans
omym2 plans <plan-id>
omym2 apply <plan-id>
omym2 apply <plan-id> --yes
omym2 apply latest

# Re-evaluate after tag correction
omym2 refresh <file>
omym2 refresh <dir>
omym2 refresh --all
omym2 refresh <file> --apply
omym2 refresh --all --trust-stat

# History and recovery
omym2 history [RUN_ID]
omym2 undo <run-id>
omym2 undo <run-id> --apply

# Status check
omym2 check
omym2 check --trust-stat
omym2 inspect <file>
```

Primary commands are purpose-based. Plan orchestration and lazy bootstrap rules are defined in [execution/model.md](execution/model.md).

## Durable Command Coordination

Long-running state-changing CLI flows—Add, Organize, Refresh, Check, Apply, and
Undo Plan generation—run synchronously from the caller's perspective while
recording the same durable Operation lifecycle used by the Web worker. Platform
orchestration generates the internal idempotency key; no CLI flag or new
user-facing key is added.

These commands hold the shared application-root exclusive lock for their full
execution. A conflicting CLI command fails immediately rather than queueing,
and a crashed Operation is marked interrupted and never resumed automatically.
This control-plane record does not change the command's Plan/Run/FileEvent
output semantics or replace FileEvents for audio, companion, or unprocessed
mutation evidence.

## Persisted Runtime, Companion, And Unprocessed Controls

`omym2 settings` edits the persisted MusicBrainz, fastText, hashing, logging,
companion, and unprocessed-file controls. `omym2 config show` displays them and
`omym2 config validate` validates them; the exact keys and defaults are in the
[Config Contract](contracts/config.md).

Normal Add, Organize, and Refresh Plan creation may perform automatic artist
naming only when MusicBrainz is enabled and a usable fastText model is
configured. Preferences and accepted cached names remain available without
new provider work. Apply, Undo, Check, History, and Plan inspection never load
the model or contact MusicBrainz.

The hashing chunk size changes read throughput, not content-hash identity.
Logging destination, level, rotation, and retention changes take effect after
the process restarts. `companions.enabled` controls creation of newly
discovered unmanaged lyrics/artwork actions and Check discovery of unmanaged
companion candidates. Disabling it does not discard managed assets, alter
recorded Plan sources or events, suppress Check itself or its managed/recorded
diagnostics, suppress recovery, History, or Undo, or change an existing Plan.
When unprocessed collection alone requests Add inventory, companion
classification still reserves recognized lyrics/artwork from leftovers but
creates no companion action, snapshot, asset ID, or dependency.

`unprocessed.enabled` affects only newly created Add Plans. Its directory and
preview limit do not recalculate, truncate, or disable actions already stored
in a Plan; Apply, History, Check, and Undo use recorded action/event evidence
even when the current setting is disabled or changed.

## add

`add` creates an add plan from Incoming or a specified source directory.

When companion processing is enabled, the same review may contain associated
same-stem lyrics and directory artwork actions after their owning audio
actions. A definitive failed companion source can be replanned through a new
Add invocation at the exact recorded external source root; a pending outcome
requires manual review instead.

When unprocessed-file collection is enabled, Add classifies audio and companion
claims first. Classification-only companion claims still reserve recognized
lyrics/artwork when companion actions are disabled. Add then records every
remaining eligible regular, non-symlink file as a trackless, content-only
`move_unprocessed` action. The result always prints
`unprocessed_actions: N`. It then prints at most the recorded
`result_preview_limit` deterministic `unprocessed: SOURCE -> TARGET` lines and,
when more remain, `unprocessed_truncated: N`. This truncation is presentation
only: every candidate, including blocked candidates, remains persisted and
available in normal Plan review.

Detailed add behavior is defined in [execution/add.md](execution/add.md).

## plans

`plans` lists created Plans and shows one Plan in detail. It is the review gate before `apply`.

```bash
omym2 plans [--status STATUS] [--type TYPE] [--limit N] [--json]
omym2 plans <PLAN_ID> [--actions STATUS] [--blocked-only] [--summary] [--diff] [--json]
```

| Flag | Mode | Meaning |
| --- | --- | --- |
| `--status STATUS` | list | Only Plans with this Plan status. |
| `--type TYPE` | list | Only Plans with this Plan type. |
| `--limit N` | list | At most N rows, applied after filtering and sorting. |
| `--actions STATUS` | detail | Only actions with this action status. |
| `--blocked-only` | detail | Shorthand for `--actions blocked`. |
| `--summary` | detail | Header plus live action tallies without the per-action dump. |
| `--diff` | detail | One arrow-style `source -> target` line per action. |
| `--json` | both | Machine-readable JSON instead of text. |

The list is sorted newest-first by creation time. This default order is intentional so the most recent Plan is always the first row.

The recommended pre-apply review workflow is `omym2 plans <PLAN_ID> --blocked-only --diff`. It lists PlanActions recorded as `blocked` and their recorded reasons.

The default detail view and detail `--json` include each action's recorded
artist and album-artist resolution diagnostics when that action reached name
resolution during Plan creation. Inspection never re-runs the resolver.

Normal text and JSON detail also expose each action's recorded
`companion_asset_id`, `owner_action_id`, and durable `depends_on_action_ids` as review evidence.

`--json` output is stable enough for scripting, but it is not a versioned public API. `--json` cannot be combined with `--summary` or `--diff`.

`apply latest` means the most recently created Plan with status `ready`.

## apply

`apply` applies a reviewed Plan.

`apply <plan-id> --yes` skips confirmation through `ApplyOptions.yes`.

`apply` has no `--trust-stat` mode. It always captures a full audio source
snapshot or rooted content-only companion snapshot and verifies the recorded
PlanAction hashes before a managed file or state update.

Detailed apply behavior is defined in [execution/apply.md](execution/apply.md).

## refresh

`refresh` re-evaluates metadata after external tag correction and creates a relocation plan when needed.

When selected audio files relocate and companion processing is enabled,
Refresh may add reviewed moves for their managed or discovered lyrics and
artwork. A metadata-only Track refresh does not move companions.

`--trust-stat` explicitly opts into reusing a Track's stored hashes and metadata when the active Track has a unique current path and the current file size and modification time exactly match its complete verified-hash baseline. A missing, ambiguous, or mismatched baseline falls back to full snapshot capture. Size and modification time are optimization hints, not proof of content equality.

Detailed refresh behavior is defined in [execution/refresh.md](execution/refresh.md).

## organize

`organize --library <path>` registers or reconciles a Library.

When companion processing is enabled, Organize registers already canonical
companions without a file mutation and plans misplaced companions after their
audio dependencies. It also owns reviewed recovery for a definitively failed
Library-relative companion source.

`--trust-stat` applies the same explicit stat-baseline optimization used by `refresh`; files without an eligible exact verified baseline match receive full snapshot capture.

Detailed organize behavior is defined in [execution/organize.md](execution/organize.md).

## history

`history` lists execution Runs. `history [RUN_ID]` shows one Run followed by
all of its FileEvents in recorded sequence order, including audio, lyrics,
artwork, and unprocessed-file mutation evidence. Each event includes its
Library, Run, PlanAction, optional CompanionAsset, paths, timestamps, status,
and failure fields. A pending event retains null completion and failure fields:
its outcome is unknown and is never reported as an automatic rollback.

Run and FileEvent semantics are defined in [execution/model.md](execution/model.md#run-behavior) and [execution/model.md](execution/model.md#fileevent-behavior).

## undo

`undo <run-id>` creates an undo plan from a Run.

`undo <run-id> --apply` applies the created undo plan within the same command.

Succeeded companion events are reversed through reviewed companion actions.
A companion recovered in a later companion-only Run is undone through that
later Run, not attached retrospectively to the original audio Run.

Detailed undo behavior is defined in [execution/undo.md](execution/undo.md).

## check

`check` reports inconsistencies between the DB and the filesystem and reports
Library state. This includes managed/unmanaged companion drift, pending
companion events, and definitively failed companion sources eligible for a new
reviewed Add or Organize Plan. It also reports missing or content-changed files
from unreversed successful unprocessed moves and directs those findings to
History rather than proposing an automatic repair.

`--trust-stat` explicitly allows managed-file diagnostics to reuse stored hashes and metadata on an exact verified stat-baseline match. Other files and baseline misses still receive full capture. The Web check route does not enable this CLI-only opt-in.

Detailed check behavior is defined in [execution/check.md](execution/check.md).

## inspect

`inspect <file>` checks metadata, hash, and canonical path for a single file.

It is read-only.

## config show

`config show` displays the current TOML-backed configuration.

Config storage is defined in [contracts/config.md](contracts/config.md).

## config validate

`config validate` validates the current TOML-backed configuration.

Config validation is implemented through the config adapter and settings usecase boundaries defined in [contracts/config.md](contracts/config.md).

## artist-ids generate

`artist-ids generate` creates editable artist ID entries in TOML config. It
uses the shared whole-string artist-name resolver defined in
[DOMAIN.md](DOMAIN.md#artist-name-batch-resolution) without making the display
name and compact artist ID the same setting.

Without `--overwrite`, existing saved artist ID entries are preserved. The
flag permits replacing only those compact config entries; it does not replace
an exact display-name preference or a sticky accepted provider result.

Without `--fasttext-model`, each name is generated from its exact configured
display-name preference, then an accepted cached provider name, then the
original source value. The command does not load fastText or contact
MusicBrainz in this mode.

An explicit `--fasttext-model <path>` additionally permits eligible unresolved
names to use the shared fastText gate and deterministic MusicBrainz acceptance
rules. A newly accepted positive result is inserted into the SQLite
`accepted_artist_names` cache before its display value is used for artist ID
generation. Lookup misses, ambiguity, ineligibility, and provider failure fall
back to the original source value and do not prevent local generation.

The artist-ID generation work writes only editable artist ID config entries
and positive accepted-name cache rows. It does not create internal Artist
identities or directly mutate Tracks, Plans, PlanActions, Runs, FileEvents, or
music files.

## settings

`settings` opens the local Web UI in a browser. The Settings surface edits full
artist display-name preferences separately from compact artist IDs, exposes
the persisted naming/runtime, companion, and unprocessed controls above, and
saves the full draft through the same revision-safe Config boundary.
