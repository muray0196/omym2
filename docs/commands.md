# Commands

This document is authoritative for the CLI command surface. Per-command descriptions are summaries only. Detailed Plan, Run, FileEvent, and failure semantics live in [execution.md](execution.md), and storage details live in [storage.md](storage.md).

The CLI is the primary execution interface. Complex settings editing is left to the GUI.

## Command List

The initial CLI is expected to include:

```bash
# Initial setup
omym2 setup
omym2 setup --library ~/Music/Library --incoming ~/Music/Incoming
omym2 setup --no-scan

# Add new tracks
omym2 add
omym2 add <source-dir>
omym2 add --apply
omym2 add --apply --yes

# Organize existing Library
omym2 organize
omym2 organize --apply

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

# Settings
omym2 config show
omym2 config validate
omym2 settings
```

Primary commands are purpose-based.

Internally, `add`, `organize`, and `refresh` create Plans, and `apply` applies a Plan.

## setup

`setup` creates config / DB, sets Library / Incoming paths, and registers existing Library tracks unless scanning is disabled.

The no-plan setup rule and registration behavior are defined in [execution.md](execution.md#setup-behavior).

## add

`add` creates an add plan from Incoming or a specified source directory.

`add --apply` creates and applies the plan in the same command. `add --apply --yes` skips apply confirmation through `ApplyOptions.yes`.

Detailed add behavior is defined in [execution.md](execution.md#add-plan-behavior).

## plans

`plans` displays created plans.

`apply latest` means the most recently created Plan with status `ready`.

## apply

`apply` applies a reviewed Plan.

`apply <plan-id> --yes` skips confirmation through `ApplyOptions.yes`.

Detailed apply behavior is defined in [execution.md](execution.md#apply-behavior).

## refresh

`refresh` re-evaluates metadata after external tag correction and creates a relocation plan when needed.

Targets can be file / directory / all. `refresh <file> --apply` applies the created plan within the same command.

Detailed refresh behavior is defined in [execution.md](execution.md#refresh-behavior).

## organize

`organize` creates a move plan for existing Library files whose current path differs from the canonical path.

`organize --apply` applies the created plan within the same command.

Detailed organize behavior is defined in [execution.md](execution.md#organize-behavior).

## history

`history` shows execution history backed by Runs and FileEvents.

Run and FileEvent semantics are defined in [execution.md](execution.md#run-behavior) and [execution.md](execution.md#fileevent-behavior).

## undo

`undo <run-id>` creates an undo plan from a Run.

`undo <run-id> --apply` applies the created undo plan within the same command.

Detailed undo behavior is defined in [execution.md](execution.md#undo-behavior).

## check

`check` reports inconsistencies between the DB and the filesystem.

Detailed check behavior is defined in [execution.md](execution.md#check-behavior).

## inspect

`inspect <file>` checks metadata, hash, and canonical path for a single file.

It is read-only.

## config show

`config show` displays the current TOML-backed configuration.

Config storage is defined in [storage.md](storage.md#toml-config-design).

## config validate

`config validate` validates the current TOML-backed configuration.

Config validation is implemented through the config adapter and settings usecase boundaries defined in [../ARCHITECTURE.md](../ARCHITECTURE.md).

## settings

`settings` opens the local settings screen in a browser.

Settings UI is represented by `omym2 settings`; `omym2 web` is not a command.

## Aliases

The following may be allowed as compatibility or auxiliary aliases:

```bash
omym2 import   # alias of add
omym2 runs     # alias of history
omym2 doctor   # alias of check
```

`add`, `history`, and `check` remain the primary command names.
