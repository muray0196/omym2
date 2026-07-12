---
type: Command Reference
title: Commands
description: Lists the OMYM2 CLI surface, including Plan workflows, diagnostics, settings, and the explicit organize/refresh/check trust-stat optimization flags.
tags: [cli, commands, reference]
timestamp: 2026-07-12T02:41:12+09:00
---

# Commands

This document is authoritative for the CLI command surface. Per-command descriptions are summaries only. Detailed Plan, Run, FileEvent, and failure semantics live in [execution/](execution/), and storage details live in [STORAGE.md](STORAGE.md).

The CLI is the primary execution interface. Complex settings editing is handled
in the local Web UI.

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

`artist-ids generate` creates editable artist ID entries in TOML config.

Without `--overwrite`, existing saved entries are preserved. With
`--fasttext-model`, the command uses fastText to identify Japanese source artist
names. For each name that needs generation, it queries MusicBrainz to prefer an
English or Latin name before deterministic ID generation.

The command does not create internal Artist identities and does not write
SQLite state.

## settings

`settings` opens the local Web UI in a browser.
