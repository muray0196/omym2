---
type: Command Reference
title: Commands
description: CLI command surface, flags, and per-command behavior summaries with links to execution semantics.
tags: [cli, commands, reference, artist-names, musicbrainz, companions, unprocessed]
timestamp: 2026-07-18T12:00:00+09:00
---

# Commands

Authoritative for the CLI command surface; per-command descriptions are summaries. Plan/Run/FileEvent and failure semantics: [execution/](execution/); storage: [STORAGE.md](STORAGE.md). The CLI is a complete execution interface; the local Web UI is a peer inbound surface over the same usecases and safety contracts.

## Command List

```bash
omym2 settings                      # open local Web UI; edit persisted controls and name mappings
omym2 config show | config validate # display / validate TOML config
omym2 organize [--library <path>] [--apply] [--trust-stat]
omym2 add [<source-dir>] [--apply] [--yes]
omym2 plans [<plan-id>]
omym2 apply <plan-id>|latest [--yes]
omym2 refresh <file>|<dir>|--all [--apply] [--trust-stat]
omym2 history [RUN_ID]
omym2 undo <run-id> [--apply]
omym2 check [--trust-stat]
omym2 inspect <file>
```

Primary commands are purpose-based. Plan orchestration and lazy bootstrap rules: [execution/model.md](execution/model.md).

## Durable Command Coordination

Long-running state-changing CLI flows (Add, Organize, Refresh, Check, Apply, Undo Plan generation) run synchronously while recording the same durable Operation lifecycle used by the Web worker. Platform orchestration generates the internal idempotency key; there is no CLI flag for it. These commands hold the shared application-root exclusive lock for their full execution: a conflicting CLI command fails immediately rather than queueing, and a crashed Operation is marked interrupted, never resumed automatically. This control-plane record does not change Plan/Run/FileEvent output semantics or replace FileEvents as mutation evidence.

## Persisted Runtime, Companion, And Unprocessed Controls

`omym2 settings` edits the persisted MusicBrainz, hashing, logging, companion, and unprocessed-file controls; `config show` / `config validate` display and validate them. Keys and defaults: [Config Contract](contracts/config.md).

* Automatic artist naming runs only during Add/Organize/Refresh Plan creation, only when MusicBrainz is enabled and a source contains non-Latin letters. Saved mappings remain available without provider work. Apply, Undo, Check, History, and Plan inspection never contact MusicBrainz.
* Hashing chunk size changes read throughput, not content-hash identity. Logging changes take effect after process restart.
* `companions.enabled` controls creation of newly discovered unmanaged lyrics/artwork actions and Check discovery of unmanaged companion candidates. Disabling it does not discard managed assets, alter recorded Plan sources or events, suppress Check or its managed/recorded diagnostics, suppress recovery/History/Undo, or change an existing Plan. When unprocessed collection alone requests Add inventory, companion classification still reserves recognized lyrics/artwork from leftovers but creates no companion action, snapshot, asset ID, or dependency.
* `unprocessed.enabled` affects only newly created Add Plans. Its directory and preview limit never recalculate, truncate, or disable actions already stored in a Plan; Apply, History, Check, and Undo use recorded evidence even when the current setting differs.

## add

`add` creates an add plan from Incoming or a specified source directory. With companions enabled, the same review may contain associated same-stem lyrics and directory artwork actions after their owning audio actions; a definitively failed companion source is replanned through a new Add at the exact recorded external source root, while a pending outcome requires manual review.

With unprocessed collection enabled, Add classifies audio and companion claims first (classification-only companion claims still reserve recognized lyrics/artwork when companion actions are disabled), then records every remaining eligible regular, non-symlink file as a trackless content-only `move_unprocessed` action. Output always prints `unprocessed_actions: N`, then at most `result_preview_limit` deterministic `unprocessed: SOURCE -> TARGET` lines, then `unprocessed_truncated: N` when more remain. Truncation is presentation-only; every candidate, including blocked ones, stays persisted and reviewable. Details: [execution/add.md](execution/add.md).

## plans

`plans` lists created Plans and shows one Plan in detail; it is the review gate before `apply`.

```bash
omym2 plans [--status STATUS] [--type TYPE] [--limit N] [--json]
omym2 plans <PLAN_ID> [--actions STATUS] [--blocked-only] [--summary] [--diff] [--json]
```

| Flag | Mode | Meaning |
| --- | --- | --- |
| `--status STATUS` | list | Only Plans with this Plan status. |
| `--type TYPE` | list | Only Plans with this Plan type. |
| `--limit N` | list | At most N rows, after filtering and sorting. |
| `--actions STATUS` | detail | Only actions with this action status. |
| `--blocked-only` | detail | Shorthand for `--actions blocked`. |
| `--summary` | detail | Header plus live action tallies, no per-action dump. |
| `--diff` | detail | One `source -> target` line per action. |
| `--json` | both | Machine-readable JSON; not combinable with `--summary` or `--diff`. |

The list is sorted newest-first by creation time. Recommended pre-apply review: `omym2 plans <PLAN_ID> --blocked-only --diff`. Detail views (text and JSON) include each action's recorded artist/album-artist resolution diagnostics (inspection never re-runs the resolver) and its recorded `companion_asset_id`, `owner_action_id`, and `depends_on_action_ids`. `--json` is stable for scripting but not a versioned public API. `apply latest` targets the most recently created Plan with status `ready`.

## apply

`apply` applies a reviewed Plan; `--yes` skips confirmation via `ApplyOptions.yes`. There is no `--trust-stat`: apply always captures a full audio source snapshot or rooted content-only companion snapshot and verifies recorded PlanAction hashes before any managed file or state update. Details: [execution/apply.md](execution/apply.md).

## refresh

`refresh` re-evaluates metadata after external tag correction and creates a relocation plan when needed. When selected audio relocates and companions are enabled, Refresh may add reviewed moves for managed or discovered lyrics/artwork; a metadata-only refresh does not move companions.

`--trust-stat` opts into reusing a Track's stored hashes and metadata when the active Track has a unique current path and current size/mtime exactly match its complete verified-hash baseline; missing, ambiguous, or mismatched baselines fall back to full snapshot capture. Size and mtime are optimization hints, not proof of content equality. Details: [execution/refresh.md](execution/refresh.md).

## organize

`organize --library <path>` registers or reconciles a Library. With companions enabled, Organize registers already canonical companions without a file mutation, plans misplaced companions after their audio dependencies, and owns reviewed recovery for a definitively failed Library-relative companion source. `--trust-stat` uses the same stat-baseline optimization as `refresh`. Details: [execution/organize.md](execution/organize.md).

## history

`history` lists execution Runs. `history RUN_ID` shows one Run and all its FileEvents in recorded sequence order (audio, lyrics, artwork, unprocessed), each with Library, Run, PlanAction, optional CompanionAsset, paths, timestamps, status, and failure fields. A pending event retains null completion/failure fields: its outcome is unknown and never reported as an automatic rollback. Semantics: [execution/model.md](execution/model.md#run-behavior), [execution/model.md](execution/model.md#fileevent-behavior).

## undo

`undo <run-id>` creates an undo plan from a Run; `--apply` applies it in the same command. Succeeded companion events are reversed through reviewed companion actions; a companion recovered in a later companion-only Run is undone through that later Run, not the original audio Run. Details: [execution/undo.md](execution/undo.md).

## check

`check` reports DB/filesystem inconsistencies and Library state: managed/unmanaged companion drift, pending companion events, definitively failed companion sources eligible for a new reviewed Add/Organize Plan, and missing or content-changed files from unreversed successful unprocessed moves (directed to History, never auto-repaired).

`--trust-stat` lets managed-file diagnostics reuse stored hashes and metadata on an exact verified stat-baseline match; other files get full capture. The Web check route does not enable this CLI-only opt-in. Details: [execution/check.md](execution/check.md).

## inspect

`inspect <file>` checks metadata, hash, and canonical path for a single file. Read-only.

## config show

Displays the current TOML-backed configuration. Contract: [contracts/config.md](contracts/config.md).

## config validate

Validates the current TOML-backed configuration through the config adapter and settings usecase boundaries in [contracts/config.md](contracts/config.md).

## settings

Opens the local Web UI. The Settings surface lists shared romanized-name mappings populated by MusicBrainz and lets users add, correct, or delete them. Mapping saves use their own revision-checked SQLite boundary; ordinary settings use the Config revision boundary. Compact artist IDs are generated internally only when a path template uses `{artist_id}` and are not editable Settings data.
