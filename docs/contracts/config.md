---
type: Contract
title: Config Contract
description: Defines OMYM2's TOML config schema, raw-storage revision and atomic-save protocol, path policy, artist IDs, and metadata/collision policy.
tags: [config, toml, concurrency, atomic-save, path-policy, artist-ids]
timestamp: 2026-07-14T01:47:14+09:00
---

# Config Contract

This document is authoritative for the OMYM2 application config contract. It
specifies the complete persisted TOML schema, defaults, and validation rules
for the supported config version.

Storage responsibility is summarized in [../STORAGE.md](../STORAGE.md). Domain concepts are in [../DOMAIN.md](../DOMAIN.md).

## Responsibilities

Editable settings live in TOML, not SQLite.

Domain and usecases do not read TOML directly. Config loading, validation, saving, default creation, and migration are adapter concerns. Usecases receive `AppConfig` or narrower config objects through ports.

Missing config is not an error by itself. Config is created lazily when a command needs persisted settings.

Config files must stay under the application root so OMYM2 remains portable, excluding user-selected Library and Incoming paths.

## Raw Storage Revision And Atomic Save

`config_revision` is an opaque compare-and-set token for the raw Config storage
state. It is not a TOML key, an `AppConfig` field, a Config version, or the
`config_hash` stored for Plan audit. A Config change does not invalidate or
recalculate an already-reviewed PlanAction.

The Config adapter captures the raw bytes and file identity before parsing,
then finalizes and returns the revision with the parse-state tag even when TOML
or AppConfig validation fails. Recovery therefore remains possible for invalid
raw state. The versioned digest input contains:

* one state tag: `missing`, `invalid`, or `valid`;
* the exact raw bytes when a file exists;
* the opened file's device/file identity, byte size, nanosecond modification
  time, and nanosecond change time when the platform exposes those values.

The adapter reads and stats the same opened file and verifies that the pathname
still identifies that file before returning. It retries a concurrent
replacement rather than combining bytes and metadata from different files.
Including file identity and change metadata means an external rewrite with
identical bytes still produces a different revision under ordinary filesystem
semantics. Clients treat the encoded digest as an opaque string and compare it
only for exact equality.

Every read used to start a Settings edit returns both the AppConfig or recovery
errors and `config_revision`. Settings validation and save requests carry
`expected_config_revision`. Previewing one self-contained PathPolicy draft does
not require a revision because it neither compares with nor writes current
storage.

All Web and CLI Config writes follow this protocol:

1. Acquire the shared exclusive-operation lock.
2. Re-read the raw storage revision while holding the lock.
3. If it differs from `expected_config_revision`, perform no write and return
   `config_changed` (HTTP 409 on the Web boundary).
4. Validate the proposed complete AppConfig without requiring the currently
   stored TOML to be valid.
5. Write deterministic TOML to a uniquely created temporary file in the Config
   directory, flush it, and sync its file descriptor.
6. Re-read `config_revision` immediately before replacement. On mismatch,
   delete the temporary file, perform no destination write, and return
   `config_changed`.
7. Atomically replace the Config path with that same-filesystem temporary file.
   Sync the containing directory where the platform supports directory sync.
8. Clear parsed-config caches and return the revision of the installed file.
9. Release the exclusive-operation lock.

A missing file has a real revision and therefore participates in compare-and-set
creation. Invalid raw TOML may be intentionally replaced only by a client that
supplies the revision it actually read. Last-write-wins, direct truncation of
the destination, and a Web-only or CLI-only locking path are prohibited.

The no-lost-update guarantee is linearizable for cooperating OMYM2 Web and CLI
writers because all of them honor the shared lock and revision protocol. The
raw revision plus the second check detects ordinary non-cooperating editor
changes, including identical-content replacement, when they occur before that
check. Portable `os.replace` does not provide a conditional pathname CAS, so an
external tool that writes in the final interval between the second check and
replace can still race; detection there is best-effort, not a false guarantee.
Users must not edit Config concurrently with an OMYM2 save.

Config replacement and SQLite cannot commit atomically. A save therefore does
not attempt to rewrite `Library.status` in the same operation. Library
readiness is derived by comparing each stored `path_policy_hash` with the
fingerprint of the newly loaded Config; Add, Bootstrap capabilities, and Check
must report the Library effectively stale on mismatch. This keeps Config
recovery available even when SQLite is degraded and avoids a false atomicity
claim across TOML and DB.

The exclusive lock mechanism is recorded in
[../decisions/0003-cross-process-exclusive-operation-lock.md](../decisions/0003-cross-process-exclusive-operation-lock.md).

## Location

Expected settings file:

```text
.config/config.toml
```

The `.config/` directory is reserved for OMYM2 internal data under the application root.

## TOML Schema, Defaults, And Validation

The table below is the complete schema for the persisted config. Every table
except `[artist_ids.entries]` has a fixed key set.

| TOML path | Accepted value | Default when omitted |
| --- | --- | --- |
| `version` | integer `1` exactly | Required; omission is invalid. |
| `paths.library` | non-empty string path | unset (`null` in `AppConfig`) |
| `paths.incoming` | non-empty string path | unset (`null` in `AppConfig`) |
| `add.default_mode` | `"plan_first"` | `"plan_first"` |
| `add.auto_apply` | boolean | `false` |
| `organize.default_mode` | `"plan_first"` | `"plan_first"` |
| `organize.auto_apply` | boolean | `false` |
| `refresh.default_mode` | `"plan_first"` | `"plan_first"` |
| `refresh.auto_apply` | boolean | `false` |
| `path_policy.template` | non-empty valid path-stem template | `{album_artist}/{year}_{album}/{disc}-{track}_{title}` |
| `path_policy.unknown_artist` | non-empty string | `"Unknown Artist"` |
| `path_policy.unknown_album` | non-empty string | `"Unknown Album"` |
| `path_policy.sanitize` | boolean | `true` |
| `path_policy.max_filename_length` | positive integer | `180` |
| `path_policy.disc_number_style` | `"plain"` or `"d_prefixed"` | `"plain"` |
| `path_policy.disc_number_condition` | `"always"` or `"multiple_discs"` | `"always"` |
| `artist_ids.max_length` | positive integer | `8` |
| `artist_ids.fallback_id` | value matching the saved artist-ID pattern below | `"NOART"` |
| `artist_ids.entries` | table mapping non-empty source-artist strings to valid saved artist-ID values | empty mapping |
| `metadata.prefer_album_artist` | boolean | `true` |
| `metadata.require_title` | boolean | `true` |
| `metadata.require_artist` | boolean | `true` |
| `metadata.require_album` | boolean | `false` |
| `metadata.album_year_resolution` | `"latest"`, `"oldest"`, or `"most_frequent"` | `"latest"` |
| `collision.on_target_exists` | `"conflict"` | `"conflict"` |
| `collision.on_duplicate_hash` | `"skip"` | `"skip"` |
| `collision.on_missing_metadata` | `"block"` | `"block"` |

Every named section is optional. A missing section, or a missing key in a
present section, uses the table's default; `version` is the sole exception.
`TomlConfigStore.save` serializes a deterministic configuration containing every
non-null setting and an `[artist_ids.entries]` table, even when that mapping is
empty.

Unknown top-level keys and unknown keys in a fixed section are validation
errors. `[artist_ids.entries]` is the only open-ended table: its keys are
user-provided source artist names, so any non-empty string key is allowed.
Its values must be non-empty strings. All ordinary string settings must be
non-empty when present; integers reject booleans; booleans must be TOML
booleans. TOML validation checks configured paths only for string type and
non-emptiness, not filesystem existence or accessibility.

The obsolete `[ui]` section is not part of AppConfig. Existing files that
still contain it fail validation as unknown-key configs; no migration or
compatibility translation is applied.

## Versioning And Migration

Only config version `1` is supported. Missing, non-integer, or unsupported
versions are validation errors. No version-based migration exists: a removed
or renamed key is rejected as unknown, and an older version is rejected rather
than silently upgraded.

Config migration policy belongs in this contract. Migration implementation
belongs to the config adapter. Do not add a separate migration document.

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
* `{year}`
* `{artist_id}`

Default template:

```text
{album_artist}/{year}_{album}/{disc}-{track}_{title}
```

The source music file suffix is appended after template rendering. Source suffixes are normalized to lowercase in the generated path. `max_filename_length` budgets the total generated file name including the extension; the extension is always preserved.

The default template does not include hash-based suffixes. If the final target path already exists, the PlanAction is blocked with `target_exists`.

PathPolicy is pure and does not perform I/O. Target existence is checked by usecases through ports.

`{disc}` renders from `TrackMetadata.disc_number` only. `disc_number_style`
controls the displayed value:

* `plain` renders the numeric value such as `1` or `2`.
* `d_prefixed` renders the configured `D` prefix plus the numeric value, such
  as `D1` or `D2`.

`disc_number_condition` controls when `{disc}` has a value:

* `always` preserves the initial behavior. It renders the disc number when
  `disc_number` is present and uses the empty-component replacement when the
  actual disc number is missing.
* `multiple_discs` renders the disc number only when already-loaded metadata
  for the album infers a total greater than 1. If the album is not inferred as
  multi-disc, PathPolicy suppresses the `{disc}` value; separators remain owned
  by the template.

Album multi-disc inference groups already-loaded `TrackMetadata` by album
artist fallback (`album_artist`, then `artist`, then `unknown_artist`), album
fallback (`album`, then `unknown_album`), and year. The inferred total is the
maximum positive value among `disc_total` and `disc_number` for tracks in that
group. Missing, zero, and negative disc values are ignored. PathPolicy and this
inference are pure domain logic and must not read the filesystem, SQLite,
TOML, Mutagen, or adapter state.

`{artist_id}` is a user-facing path/config value. It is resolved from the
already-loaded `artist_ids.entries` mapping using the source artist name from
metadata. When no saved entry exists, PathPolicy may use the pure deterministic
artist ID generator with `artist_ids.max_length` and `artist_ids.fallback_id`.
It must not load fastText models or call MusicBrainz during path rendering.
Artist ID settings participate in the Library registration path-policy
fingerprint only when the active template contains the `{artist_id}`
placeholder.

## ArtistIdConfig

Artist IDs are editable settings stored in TOML, not internal OMYM2 identities.
They are not Track, Library, or Artist entity IDs.

Fields:

* `max_length`: positive maximum generated ID length
* `fallback_id`: non-empty ID used when source text has no usable characters
* `entries`: editable mapping from source artist name to saved artist ID

Normal generation saves only missing entries. Existing entries are preserved
unless the user explicitly requests regeneration/overwrite.

Entry values must be non-empty ASCII letters, digits, or underscores with
optional single internal hyphens (no leading/trailing hyphen, no repeated
hyphens); invalid values are rejected at load/save time. `fallback_id` shares
this same rule, since it can flow into generated IDs and saved entries.

## Metadata And Collision Policy

Metadata policy controls which tag fields are required for plan creation.

`album_year_resolution` controls the effective album year used for `{year}`
path rendering when a planning batch can see related tracks in the same album
group. Raw per-track `TrackMetadata.year` values remain unchanged. Supported
values:

* `latest` (default): newest usable track year in the album group
* `oldest`: oldest usable track year in the album group
* `most_frequent`: most common usable year; ties choose the latest tied year

Missing years are ignored when at least one usable year exists in the group.
When every track in the group has no usable year, `{year}` keeps the existing
empty placeholder rendering.

Collision policy controls what plan creation records when:

* a target already exists
* a duplicate content hash is known
* required metadata is missing

The current policy blocks target conflicts, skips duplicate hashes, and blocks missing required metadata.

The local Web UI may edit settings, validate settings, and preview PathPolicy output. It must use config usecases and config adapters rather than reading or writing TOML directly from route logic.
