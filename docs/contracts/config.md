---
type: Contract
title: Config Contract
description: Defines OMYM2's TOML config schema, atomic-save protocol, naming and path policy, runtime controls, companion processing, and unprocessed-file collection.
tags: [config, toml, concurrency, atomic-save, path-policy, artist-names, musicbrainz, logging, companions, unprocessed]
timestamp: 2026-07-17T22:43:57+09:00
---

# Config Contract

This document is authoritative for the OMYM2 application config contract. It
specifies the complete persisted TOML schema, defaults, and validation rules
for the supported config version.

Storage responsibility is summarized in [../STORAGE.md](../STORAGE.md). Domain concepts are in [../DOMAIN.md](../DOMAIN.md).

## Responsibilities

Editable settings live in TOML, not SQLite.

Domain and usecases do not read TOML directly. Config loading, validation,
saving, and default creation are adapter concerns. Usecases receive `AppConfig`
or narrower config objects through ports.

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
has a fixed key set.

| TOML path | Accepted value | Default when omitted |
| --- | --- | --- |
| `version` | integer `2` exactly | Required; omission is invalid. |
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
| `artist_ids.fallback_id` | valid compact ID used when generation has no usable characters | `"NOART"` |
| `musicbrainz.enabled` | boolean | `true` |
| `musicbrainz.application_name` | non-empty string | `"OMYM2"` |
| `musicbrainz.contact` | non-empty string | `"https://github.com/muray0196/omym2"` |
| `musicbrainz.timeout_seconds` | finite number greater than `0` | `5.0` |
| `musicbrainz.retry_limit` | non-negative integer | `1` |
| `musicbrainz.rate_limit_seconds` | finite number at least `1.0` | `1.0` |
| `musicbrainz.cache_policy` | `"sticky_positive"` | `"sticky_positive"` |
| `hashing.read_chunk_size_bytes` | positive integer | `1048576` |
| `logging.destination` | normalized application-root-relative logical path | unset (the application-data log default) |
| `logging.level` | `"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`, or `"CRITICAL"` | `"INFO"` |
| `logging.rotation_max_bytes` | positive integer | `5242880` |
| `logging.retention_files` | positive integer | `3` |
| `companions.enabled` | boolean | `false` |
| `unprocessed.enabled` | boolean | `false` |
| `unprocessed.directory` | one portable relative path component | `"Unprocessed"` |
| `unprocessed.result_preview_limit` | integer from `1` through `500` | `100` |
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
non-null setting.

Unknown top-level keys and unknown keys in a fixed section are validation
errors. All ordinary string settings must be non-empty when present; integers
reject booleans; booleans must be TOML booleans. TOML validation checks
configured paths only for string type and non-emptiness, not filesystem
existence or accessibility.

## Versioning And Reset

Only config version `2` is supported. Missing, non-integer, or unsupported
versions are validation errors. No version-based migration exists. The
2026-07-16 pre-release clean-slate cutover intentionally made older Config
files unsupported; delete `.config/config.toml` and recreate Settings with the
current binary. The former `[artist_names.preferences]` table is removed;
artist-name mappings now live in SQLite, so a Config file that still contains
that table is rejected as unknown rather than translated. Other removed,
renamed, and unknown keys follow the same rule.

Any future version cutover and its reset policy belong in this contract. Do not
add an implicit adapter migration or a separate migration document.

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

When `sanitize = true`, every rendered component follows current OMYM2
portability rules:

* normalize text with Unicode NFKC;
* replace every character outside Unicode word characters and `-` with `-`,
  collapse repeated hyphens, and trim leading or trailing hyphens;
* enforce the one configured `max_filename_length` as a UTF-8 byte budget for
  artist, album, directory, and final filename components;
* preserve an alphanumeric final extension and reserve its bytes before
  truncating the stem;
* use `_` for a component that sanitizes away, use `Unknown-Title` for title
  text that sanitizes away, and prevent Windows reserved device-name
  stems such as `CON`, `NUL`, `COM1`, and `LPT1`;
* continue to enforce Library-relative containment after rendering.

There is no apostrophe exception or artist/album-specific byte limit. Spaces,
apostrophes, punctuation, and path separators all follow the same unsafe-run
replacement rule. These rules are justified by deterministic Unicode output,
portable component safety, Windows filename constraints, extension
preservation, and containment; they do not reproduce an earlier application's
output. With `sanitize = false`, OMYM2 skips text replacement but still applies
the configured byte budget, preserves the extension, and enforces
Library-relative containment.

The default template does not include hash-based suffixes. If the final target path already exists, the PlanAction is blocked with `target_exists`.

PathPolicy is pure and does not perform I/O. It receives an already-derived
artist-name projection rather than reading preferences or provider state.
Target existence is checked by usecases through ports.

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

`{artist_id}` is an internally generated path value. PathPolicy passes the
already-derived Latin display name to the pure deterministic artist ID
generator, falling back to the original source text, and applies
`artist_ids.max_length` and `artist_ids.fallback_id`.
It must not call MusicBrainz during path rendering.
Artist ID settings participate in the Library registration path-policy
fingerprint only when the active template contains the `{artist_id}`
placeholder.

`{artist}` and `{album_artist}` use the already-derived Latin-name projection
when one is supplied. `{artist_id}` uses the original metadata value only as
its internal memoization key; the Latin projection is the generation input.
Original-to-Latin mappings are SQLite feature data, not
AppConfig; their contract is in
[DB Schema](db-schema.md#accepted_artist_names). Mapping contents therefore do
not participate in `config_hash` or the Config-derived Library path-policy
fingerprint. Plans record the resolved-name diagnostics and target paths they
actually used; Add and partial Refresh keep their whole-Library reconciliation
guard, and Apply executes only those recorded targets.

## MusicBrainz Runtime Controls

`musicbrainz.enabled` controls new automatic provider work and defaults to
enabled. A saved artist-name mapping remains available when it is disabled. An
eligible uncached source records `automatic_lookup_disabled`, and no network
call occurs.

The application identity and contact form the MusicBrainz User-Agent. One
initial request plus at most `retry_limit` retries uses `timeout_seconds` for
each attempt. `rate_limit_seconds` cannot be below the provider minimum of one
second. SQLite coordinates that cadence across processes and restarts without
holding a transaction while sleeping. The only cache policy is
`sticky_positive`: automatic results persist insert-if-absent, while misses and
failures do not become negative cache entries. Users may subsequently edit or
delete positive mappings through Settings.

Eligibility is deterministic: Latin-only sources, including diacritics, remain
unchanged, while any alphabetic character outside the Unicode Latin script
permits provider lookup. Changing provider, timeout, retry, or cadence controls
changes the full Plan audit `config_hash`, but it does not change the Library
path-policy fingerprint. Apply never reloads these controls or rewrites an
already-reviewed target.

## Hashing And Logging Controls

`hashing.read_chunk_size_bytes` controls streaming reads for full music
snapshots, content-only companion and unprocessed snapshots, duplicate checks,
and standalone inspection. It is an operational throughput control: changing
it must not change the resulting content hash or Library staleness.

Logging is configured once at process startup. A null destination selects the
writable application-data log. A configured destination must use normalized
forward-slash relative syntax, cannot contain `..`, a Windows drive, or a
backslash, and is anchored beneath the application root. Rotation occurs after
`rotation_max_bytes`; `retention_files` is the number of rotated backups.
Configured application paths, model/log destinations, and MusicBrainz contact
identity are redacted from rendered messages and exception text. A logging
settings change therefore takes effect after restarting the process and never
marks a Library stale.

## Companion And Unprocessed Controls

`companions.enabled` allows new Add, Organize, and Refresh Plans to create
actions for unmanaged same-stem lyrics and directory artwork, and allows Check
to discover unmanaged companion candidates. Disabling it stops those new
actions and that unmanaged Check classification; it does not delete managed
companion state, alter recorded Plan sources or events, suppress Check itself
or its managed/recorded diagnostics, suppress recovery, History, or Undo, or
change an existing Plan. When `unprocessed.enabled` alone requests Add
inventory, companion classification still reserves recognized lyrics/artwork
from leftovers without creating companion actions, content snapshots, IDs, or
dependencies.

`unprocessed.enabled` independently allows new Add review to include regular
files left unclaimed by music and companion classification.
`unprocessed.directory` is exactly one portable component: it rejects path
separators, roots, `.`/`..`, trailing dots or spaces, control and Windows-
invalid characters, and reserved Windows device names. The destination remains
under the selected source root. `result_preview_limit` bounds presentation
only; it never truncates the durable candidate/action set.

These controls participate in full Plan audit `config_hash` but not in Library
path-policy identity. Both default to disabled, and disabling either one never
rewrites prior durable state.

The unprocessed directory is recorded indirectly in every action's exact
source/target shape, and the preview limit is copied into the Plan summary for
deterministic result presentation. Apply, Check, History, and Undo do not
consult the current unprocessed toggle, directory, or preview limit when
interpreting already-recorded evidence.

## ArtistIdConfig

Artist IDs are automatic internal path values, not Track, Library, or Artist
entity IDs. TOML stores only general generation tunables.

Fields:

* `max_length`: positive maximum generated ID length
* `fallback_id`: non-empty ID used when source text has no usable characters

`fallback_id` must be non-empty ASCII letters, digits, or underscores with
optional single internal hyphens (no leading/trailing hyphen, no repeated
hyphens); invalid values are rejected at load/save time because it can flow
directly into generated paths.

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
