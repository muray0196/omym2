# Commands

This document is authoritative for the CLI command surface. Per-command descriptions are summaries only. Detailed Plan, Run, FileEvent, and failure semantics live in [execution.md](execution.md), and storage details live in [storage.md](storage.md).

The CLI is the primary execution interface. Complex settings editing is left to the GUI.

## Command List

The initial CLI is expected to include:

```bash
# Settings
omym2 settings
omym2 config show
omym2 config validate

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

Primary commands are purpose-based.

Internally, `add` and `refresh` create Plans, `organize` creates a Plan when Library music files need to move or blocking actions must be reviewed, and `apply` applies a Plan.

Config, DB, and internal directories are created lazily when commands need them. Missing config or DB is not an error by itself. Missing required paths are errors only for commands that need them.

## add

`add` creates an add plan from Incoming or a specified source directory.

In the MVP, `add` targets the sole registered Library. If no registered Library exists or Library selection is ambiguous, `add` refuses to create a plan. The user-facing remedy is `omym2 organize --library <path>`.

`add` does not organize existing Library files and does not mix Incoming import actions with existing Library organization actions. It does not register, reconcile, or relink a Library.

Incoming-source selection follows [Bootstrap Behavior](execution.md#bootstrap-behavior): without a configured Incoming path, `add` requires an explicit source directory.

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

`organize --library <path>` is the primary user-facing operation for registering and reconciling a Library. It scans the specified Library read-only, compares files with canonical paths under the current PathPolicy, and creates a move plan when files need to move.

Plain `organize` is valid only when exactly one known Library can be selected unambiguously. Otherwise it fails with a clear message and asks for `organize --library <path>`.

If no moves are needed and no blocking issues exist, `organize` can register the Library without creating a mutation Plan. If an organize Plan is applied successfully and no blocking Library-state issues remain, the Library becomes registered. If blocked actions remain, it does not become registered.

`organize --apply` applies the created plan within the same command. `organize --library <path> --apply` does the same after selecting or registering the Library identity for `<path>`.

Detailed organize behavior is defined in [execution.md](execution.md#organize-behavior).

## history

`history` shows execution history backed by Runs and FileEvents.

Run and FileEvent semantics are defined in [execution.md](execution.md#run-behavior) and [execution.md](execution.md#fileevent-behavior).

## undo

`undo <run-id>` creates an undo plan from a Run.

`undo <run-id> --apply` applies the created undo plan within the same command.

Detailed undo behavior is defined in [execution.md](execution.md#undo-behavior).

## check

`check` reports inconsistencies between the DB and the filesystem and reports Library state.

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

Settings UI is represented by `omym2 settings`.
