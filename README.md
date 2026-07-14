# OMYM2

OMYM2 safely imports local music files into an organized music library.

It is a local-first tool built around reviewable plans. Commands that can move
library files create a plan first, let you inspect it, and then apply the
recorded actions.

## Requirements

- Local music files with readable metadata

The packaged desktop application supports Windows 11 x64 and requires the
[shared Evergreen Microsoft Edge WebView2 Runtime](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution).
It does not require a separate Python or Node.js installation and does not
bundle Chromium. Windows desktop archives are currently unsigned development
builds rather than public releases; use only an artifact you trust.

The command-line application requires Python 3.14 or newer.

From a source checkout, run commands with `uv run`:

```bash
uv run omym2 settings
```

After installing the package into an environment, use `omym2` directly.

## Quick Start

Open the local settings UI:

```bash
omym2 settings
```

Register or reconcile a library:

```bash
omym2 organize --library /path/to/music-library
omym2 plans
omym2 apply <plan-id>
```

Import new tracks after one library is registered:

```bash
omym2 add /path/to/incoming
omym2 plans
omym2 apply <plan-id>
```

Use `--apply` when you want a command to create and apply its plan in one run:

```bash
omym2 add /path/to/incoming --apply
```

## Usage

For the Windows desktop application, extract the complete ZIP and run
`OMYM2.exe`. It opens the same OMYM2 interface in one native window; no browser
or server startup is required.

Most common commands:

```bash
omym2 add <source-dir>
omym2 organize --library <path>
omym2 plans
omym2 apply <plan-id>
omym2 undo <run-id>
```

See [docs/COMMANDS.md](docs/COMMANDS.md) for the complete command surface,
including `refresh`, `history`, `check`, `inspect`, `config`, and
`artist-ids`.

## Common Workflow

1. Run `omym2 settings` and set the library, incoming folder, and path policy.
2. Run `omym2 organize --library <path>` for an existing library.
3. Review the generated plan with `omym2 plans` or `omym2 plans <plan-id>`.
4. Apply the reviewed plan with `omym2 apply <plan-id>`.
5. Use `omym2 add` or `omym2 add <source-dir>` for day-to-day imports.
6. Run `omym2 check` when you want to compare OMYM2 state with the filesystem.

## How OMYM2 Works

OMYM2 is not a tag editor and does not manage playback. Edit tags with your
preferred tool, then use `omym2 refresh` when existing library files need to be
re-evaluated after tag changes.

The Windows desktop application stores editable settings and managed state
under `%LOCALAPPDATA%\OMYM2`:

```text
%LOCALAPPDATA%\OMYM2\.config\config.toml
%LOCALAPPDATA%\OMYM2\.data\omym2.sqlite3
```

Replacing or deleting the extracted application directory does not delete this
state. Delete `%LOCALAPPDATA%\OMYM2` separately only when you intentionally want
to erase OMYM2's desktop settings, database, and logs.

The CLI instead stores them under its current application root:

```text
.config/config.toml
.data/omym2.sqlite3
```

Run the CLI from the same application root when you want to use the same
settings, plans, history, and library state. The desktop and CLI do not
implicitly share roots.

## More Information

- Product overview: [docs/PRODUCT.md](docs/PRODUCT.md)
- Command reference: [docs/COMMANDS.md](docs/COMMANDS.md)
- Settings contract: [docs/contracts/config.md](docs/contracts/config.md)
- Windows package development: [docs/development/desktop-packaging.md](docs/development/desktop-packaging.md)
