---
type: Command Reference
title: Commands
description: Lists the OMYM2 CLI surface, including Plan workflows, artist-name settings, diagnostics, and the explicit organize/refresh/check trust-stat optimization flags.
tags: [cli, commands, reference]
timestamp: 2026-07-16T00:44:26+09:00
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
omym2 history
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
output semantics or replace FileEvents for music-file mutation evidence.

## add

`add` creates an add plan from Incoming or a specified source directory.

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

`--json` output is stable enough for scripting, but it is not a versioned public API. `--json` cannot be combined with `--summary` or `--diff`.

`apply latest` means the most recently created Plan with status `ready`.

## apply

`apply` applies a reviewed Plan.

`apply <plan-id> --yes` skips confirmation through `ApplyOptions.yes`.

`apply` has no `--trust-stat` mode. It always captures a full source snapshot and verifies the recorded PlanAction hashes before a Library music file mutation or Track update.

Detailed apply behavior is defined in [execution/apply.md](execution/apply.md).

## refresh

`refresh` re-evaluates metadata after external tag correction and creates a relocation plan when needed.

`--trust-stat` explicitly opts into reusing a Track's stored hashes and metadata when the active Track has a unique current path and the current file size and modification time exactly match its complete verified-hash baseline. A missing, ambiguous, or mismatched baseline falls back to full snapshot capture. Size and modification time are optimization hints, not proof of content equality.

Detailed refresh behavior is defined in [execution/refresh.md](execution/refresh.md).

## organize

`organize --library <path>` registers or reconciles a Library.

`--trust-stat` applies the same explicit stat-baseline optimization used by `refresh`; files without an eligible exact verified baseline match receive full snapshot capture.

Detailed organize behavior is defined in [execution/organize.md](execution/organize.md).

## history

`history` shows execution history backed by Runs and FileEvents.

Run and FileEvent semantics are defined in [execution/model.md](execution/model.md#run-behavior) and [execution/model.md](execution/model.md#fileevent-behavior).

## undo

`undo <run-id>` creates an undo plan from a Run.

`undo <run-id> --apply` applies the created undo plan within the same command.

Detailed undo behavior is defined in [execution/undo.md](execution/undo.md).

## check

`check` reports inconsistencies between the DB and the filesystem and reports Library state.

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
artist display-name preferences separately from compact artist IDs and saves
both through the same revision-safe Config boundary.
