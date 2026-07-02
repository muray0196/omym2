# Config Contract

This document is authoritative for the OMYM2 application config contract.

Storage responsibility is summarized in [../STORAGE.md](../STORAGE.md). Domain concepts are in [../DOMAIN.md](../DOMAIN.md).

## Responsibilities

Editable settings live in TOML, not SQLite.

Domain and usecases do not read TOML directly. Config loading, validation, saving, default creation, and migration are adapter concerns. Usecases receive `AppConfig` or narrower config objects through ports.

Missing config is not an error by itself. Config is created lazily when a command needs persisted settings.

Config files must stay under the application root so OMYM2 remains portable, excluding user-selected Library and Incoming paths.

## Location

Expected settings file:

```text
.config/config.toml
```

The `.config/` directory is reserved for OMYM2 internal data under the application root.

## AppConfig Shape

Initial settings areas:

```text
version
paths
add
organize
refresh
path_policy
artist_ids
metadata
collision
ui
```

Representative TOML shape:

```toml
version = 1

[paths]
library = "/Users/me/Music/Library"
incoming = "/Users/me/Music/Incoming"

[add]
default_mode = "plan_first"
auto_apply = false

[organize]
default_mode = "plan_first"
auto_apply = false
only_misplaced = true

[refresh]
default_mode = "plan_first"
auto_apply = false

[path_policy]
template = "{album_artist}/{year}_{album}/{disc}-{track}_{title}"
unknown_artist = "Unknown Artist"
unknown_album = "Unknown Album"
sanitize = true
max_filename_length = 180

[artist_ids]
max_length = 8
fallback = "NOART"

[artist_ids.entries]
"Aimer" = "AMR"

[metadata]
prefer_album_artist = true
require_title = true
require_artist = true
require_album = false

[collision]
on_target_exists = "conflict"
on_duplicate_hash = "skip"
on_missing_metadata = "block"

[ui]
theme = "system"
show_advanced_settings = false
```

## Versioning And Migration

Config has a version so future migrations can be supported.

Config migration policy belongs in this contract. Migration implementation belongs to the config adapter. Do not add a separate migration document.

## PathPolicyConfig

PathPolicy should receive a narrow config object where possible rather than the whole `AppConfig`.

Path policy templates render a Library-root-relative path stem. Templates must not include file extensions.

Allowed placeholders:

* `{album_artist}`
* `{album}`
* `{disc}`
* `{track}`
* `{title}`
* `{artist}`
* `{artist_id}`
* `{year}`

Initial template:

```text
{album_artist}/{year}_{album}/{disc}-{track}_{title}
```

The source music file suffix is appended after template rendering. Source suffixes are normalized to lowercase in the generated path.

The initial template does not include hash-based suffixes. If the final target path already exists, the PlanAction is blocked with `target_exists`.

PathPolicy is pure and does not perform I/O. Target existence is checked by usecases through ports.

`{artist_id}` resolves from the already-loaded `artist_ids` config and track metadata. PathPolicy never
loads a language model, calls MusicBrainz, reads TOML, or writes generated entries while rendering paths.
When no saved entry exists for the source artist text, PathPolicy uses the pure deterministic artist ID
generator and the configured fallback.

## ArtistIdConfig

Artist IDs are editable user-facing path/config values. They are not internal identities and are not stored
in SQLite.

TOML shape:

```toml
[artist_ids]
max_length = 8
fallback = "NOART"

[artist_ids.entries]
"宇多田ヒカル" = "HTDRHKR"
```

`artist_ids.entries` is keyed by the source artist name used for generation. Normal generation preserves
existing saved entries; users may edit them through the local settings surface. Explicit regenerate flows may
overwrite saved entries.

Generation behavior:

* split multiple artists by comma
* split normalized artist text by hyphen
* remove vowels after the first character per word
* allocate characters round-robin across words/artists up to `max_length`
* use `fallback` when no usable Latin artist text remains

Japanese handling is a feature/adapters concern before config is saved. fastText detects whether Japanese
lookup should be attempted. MusicBrainz may supply a preferred English/Latin artist name. Neither call occurs
during `add`, `organize`, `refresh`, apply, or PathPolicy rendering.

## Metadata And Collision Policy

Metadata policy controls which tag fields are required for plan creation.

Collision policy controls what plan creation records when:

* a target already exists
* a duplicate content hash is known
* required metadata is missing

The initial policy blocks target conflicts, skips duplicate hashes, and blocks missing required metadata.

## UI Settings

UI settings are application config. They are stored in TOML, not SQLite.

The local Web UI may edit settings, validate settings, and preview PathPolicy output. It must use config usecases and config adapters rather than reading or writing TOML directly from route logic.
