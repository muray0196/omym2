# Commands

This document is authoritative for the CLI command surface. Per-command descriptions are summaries only. Detailed Plan, Run, FileEvent, and failure semantics live in [execution/](execution/), and storage details live in [STORAGE.md](STORAGE.md).

The CLI is the primary execution interface. Complex settings editing is left to the GUI.

## Command List

The initial CLI is expected to include:

```bash
# Settings
omym2 settings
omym2 config show
omym2 config validate
omym2 artist-ids generate [--overwrite] [--fasttext-model <path>] <artist>...

# Register or organize existing Library
omym2 organize --library <path>
omym2 organize --library <path> --apply
omym2 organize
omym2 organize --apply

# Add new tracks to a registered Library
omym2 add
omym2 add <source-dir>
omym2 add --apply
omym2 add --apply --yes

# Plan
omym2 plans
omym2 apply <plan-id>
omym2 apply <plan-id> --yes
omym2 apply latest

# Re-evaluate after tag correction
omym2 refresh <file>
omym2 refresh <dir>
omym2 refresh --all
omym2 refresh <file> --apply

# History and recovery
omym2 history
omym2 undo <run-id>
omym2 undo <run-id> --apply

# Status check
omym2 check
omym2 inspect <file>
```

Primary commands are purpose-based. Plan orchestration and lazy bootstrap rules are defined in [execution/model.md](execution/model.md).

## add

`add` creates an add plan from Incoming or a specified source directory.

Detailed add behavior is defined in [execution/add.md](execution/add.md).

## plans

`plans` displays created plans.

`apply latest` means the most recently created Plan with status `ready`.

## apply

`apply` applies a reviewed Plan.

`apply <plan-id> --yes` skips confirmation through `ApplyOptions.yes`.

Detailed apply behavior is defined in [execution/apply.md](execution/apply.md).

## refresh

`refresh` re-evaluates metadata after external tag correction and creates a relocation plan when needed.

Detailed refresh behavior is defined in [execution/refresh.md](execution/refresh.md).

## organize

`organize --library <path>` registers or reconciles a Library.

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
`--fasttext-model`, the command can use fastText to decide whether a source
artist should attempt Japanese handling and then use MusicBrainz to prefer an
English or Latin name before deterministic ID generation.

The command does not create internal Artist identities and does not write
SQLite state.

## settings

`settings` opens the local settings screen in a browser.

Settings UI is represented by `omym2 settings`.
