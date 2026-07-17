---
type: Contract
title: Config Contract
description: Complete TOML schema, defaults, validation, atomic-save protocol, path policy, and runtime control semantics.
tags: [config, toml, concurrency, atomic-save, path-policy, artist-names, musicbrainz, logging, companions, unprocessed]
timestamp: 2026-07-18T12:00:00+09:00
---

# Config Contract

Authoritative for the application config contract: the complete persisted TOML schema, defaults, and validation rules for the supported config version. Storage summary: [../STORAGE.md](../STORAGE.md); domain concepts: [../DOMAIN.md](../DOMAIN.md).

## Responsibilities

Editable settings live in TOML, not SQLite. Domain and usecases never read TOML directly; loading, validation, saving, and default creation are adapter concerns, with usecases receiving `AppConfig` or narrower objects through ports. Missing config is not an error; config is created lazily when a command needs persisted settings. Config files stay under the application root (excluding user-selected Library and Incoming paths).

## Raw Storage Revision And Atomic Save

`config_revision` is an opaque compare-and-set token for the raw Config storage state — not a TOML key, `AppConfig` field, Config version, or the Plan-audit `config_hash`. A Config change never invalidates or recalculates an already-reviewed PlanAction.

The adapter captures raw bytes and file identity before parsing, then finalizes and returns the revision with the parse-state tag even when TOML or AppConfig validation fails, so recovery remains possible for invalid raw state. The versioned digest input contains: one state tag (`missing` | `invalid` | `valid`); the exact raw bytes when a file exists; and the opened file's device/file identity, byte size, nanosecond mtime, and nanosecond ctime when the platform exposes them. The adapter reads and stats the same opened file, verifies the pathname still identifies it before returning, and retries a concurrent replacement rather than mixing bytes and metadata from different files. Identity+change metadata means an external rewrite with identical bytes still produces a different revision. Clients treat the digest as opaque and compare only for exact equality.

Every read that starts a Settings edit returns both the AppConfig (or recovery errors) and `config_revision`. Validation and save requests carry `expected_config_revision`. Previewing one self-contained PathPolicy draft needs no revision (it neither compares with nor writes storage).

All Web and CLI Config writes follow this protocol:

1. Acquire the shared exclusive-operation lock.
2. Re-read the raw storage revision while holding the lock.
3. On mismatch with `expected_config_revision`: no write, return `config_changed` (HTTP 409 on the Web boundary).
4. Validate the proposed complete AppConfig without requiring the stored TOML to be valid.
5. Write deterministic TOML to a uniquely created temporary file in the Config directory, flush, and sync its descriptor.
6. Re-read `config_revision` immediately before replacement; on mismatch, delete the temp file, write nothing, return `config_changed`.
7. Atomically replace the Config path with the same-filesystem temp file; sync the containing directory where supported.
8. Clear parsed-config caches and return the revision of the installed file.
9. Release the exclusive-operation lock.

A missing file has a real revision and participates in compare-and-set creation. Invalid raw TOML may be replaced only by a client supplying the revision it actually read. Last-write-wins, direct destination truncation, and Web-only or CLI-only locking paths are prohibited.

The no-lost-update guarantee is linearizable for cooperating OMYM2 writers honoring the shared lock and revision protocol. The raw revision plus the second check detects ordinary non-cooperating editor changes (including identical-content replacement) occurring before that check; portable `os.replace` has no conditional pathname CAS, so an external write in the final interval can still race — detection there is best-effort. Users must not edit Config concurrently with an OMYM2 save.

Config replacement and SQLite cannot commit atomically, so a save never rewrites `Library.status` in the same operation. Library readiness is derived by comparing each stored `path_policy_hash` with the fingerprint of the newly loaded Config; Add, Bootstrap capabilities, and Check must report the Library effectively stale on mismatch. Lock mechanism: [ADR 0003](../decisions/0003-cross-process-exclusive-operation-lock.md).

## Location

`.config/config.toml`. The `.config/` directory is reserved for OMYM2 internal data under the application root.

## TOML Schema, Defaults, And Validation

Complete schema; every table has a fixed key set.

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

Every named section is optional; a missing section or key uses the default, with `version` the sole exception. `TomlConfigStore.save` serializes a deterministic configuration containing every non-null setting. Unknown top-level keys and unknown keys in a fixed section are validation errors. Ordinary string settings must be non-empty when present; integers reject booleans; booleans must be TOML booleans. Path values are checked only for string type and non-emptiness, never filesystem existence.

## Versioning And Reset

Only config version `2` is supported; missing, non-integer, or unsupported versions are validation errors. No version-based migration exists: the 2026-07-16 pre-release clean-slate cutover made older Config files unsupported — delete `.config/config.toml` and recreate Settings. The former `[artist_names.preferences]` table is removed (artist-name mappings live in SQLite); a Config still containing it is rejected as unknown, as are other removed/renamed/unknown keys. Any future version cutover and reset policy belongs in this contract — no implicit adapter migration or separate migration document.

## PathPolicyConfig

PathPolicy should receive a narrow config object rather than the whole `AppConfig`. Templates render a Library-root-relative path stem and must not include file extensions.

Allowed placeholders: `{album_artist}`, `{album}`, `{disc}`, `{track}`, `{title}`, `{artist}`, `{year}`, `{artist_id}`. Default template: `{album_artist}/{year}_{album}/{disc}-{track}_{title}`.

The source suffix is appended after rendering and normalized to lowercase. `max_filename_length` budgets the total generated file name including the extension; the extension is always preserved.

When `sanitize = true`, every rendered component follows current portability rules:

* normalize with Unicode NFKC;
* replace every character outside Unicode word characters and `-` with `-`, collapse repeated hyphens, trim leading/trailing hyphens;
* enforce the one configured `max_filename_length` as a UTF-8 byte budget for artist, album, directory, and final filename components;
* preserve an alphanumeric final extension and reserve its bytes before truncating the stem;
* use `_` for a component that sanitizes away, `Unknown-Title` for title text that sanitizes away, and prevent Windows reserved device-name stems (`CON`, `NUL`, `COM1`, `LPT1`, …);
* enforce Library-relative containment after rendering.

There is no apostrophe exception or artist/album-specific byte limit; spaces, apostrophes, punctuation, and separators all follow the unsafe-run replacement rule. These rules exist for deterministic Unicode output, portable component safety, Windows constraints, extension preservation, and containment — they do not reproduce an earlier application's output. With `sanitize = false`, text replacement is skipped but the byte budget, extension preservation, and containment still apply.

No hash-based suffixes: if the final target path already exists, the PlanAction blocks with `target_exists`. PathPolicy is pure, performs no I/O, and receives an already-derived artist-name projection; target existence is checked by usecases through ports.

`{disc}` renders from `TrackMetadata.disc_number` only. `disc_number_style`: `plain` renders `1`/`2`; `d_prefixed` renders `D1`/`D2`. `disc_number_condition`: `always` renders when `disc_number` is present (empty-component replacement otherwise); `multiple_discs` renders only when already-loaded album metadata infers a total greater than 1, else suppresses the value (separators stay owned by the template). Multi-disc inference groups already-loaded `TrackMetadata` by album-artist fallback (`album_artist` → `artist` → `unknown_artist`), album fallback (`album` → `unknown_album`), and year; the inferred total is the maximum positive value among `disc_total` and `disc_number` in the group, ignoring missing/zero/negative. PathPolicy and this inference are pure domain logic — no filesystem, SQLite, TOML, Mutagen, or adapter state.

`{artist_id}` is internally generated: PathPolicy passes the already-derived Latin display name (falling back to original source text) to the pure deterministic generator with `artist_ids.max_length` and `artist_ids.fallback_id`. It must not call MusicBrainz during rendering. Artist ID settings participate in the Library registration path-policy fingerprint only when the active template contains `{artist_id}`.

`{artist}` and `{album_artist}` use the already-derived Latin-name projection when supplied. `{artist_id}` uses the original metadata value only as its memoization key; the Latin projection is the generation input. Original-to-Latin mappings are SQLite feature data ([DB Schema](db-schema.md#accepted_artist_names)), not AppConfig, so mapping contents participate in neither `config_hash` nor the Library path-policy fingerprint. Plans record the resolved-name diagnostics and targets they actually used; Add and partial Refresh keep their whole-Library reconciliation guard, and Apply executes only recorded targets.

## MusicBrainz Runtime Controls

`musicbrainz.enabled` controls new automatic provider work (default enabled). Saved mappings remain available when disabled; an eligible uncached source records `automatic_lookup_disabled` with no network call.

Application identity and contact form the MusicBrainz User-Agent. One initial request plus at most `retry_limit` retries, each with `timeout_seconds`. `rate_limit_seconds` cannot go below the provider minimum of 1 s; SQLite coordinates cadence across processes and restarts without holding a transaction while sleeping. The only cache policy is `sticky_positive`: automatic results persist insert-if-absent; misses and failures never become negative cache entries. Users may edit or delete positive mappings through Settings.

Eligibility is deterministic: Latin-only sources (including diacritics) remain unchanged; any alphabetic character outside the Unicode Latin script permits provider lookup. Changing provider, timeout, retry, or cadence controls changes the Plan-audit `config_hash` but not the Library path-policy fingerprint. Apply never reloads these controls or rewrites a reviewed target.

## Hashing And Logging Controls

`hashing.read_chunk_size_bytes` controls streaming reads for full music snapshots, content-only companion/unprocessed snapshots, duplicate checks, and standalone inspection. It is a throughput control only: changing it must not change resulting content hashes or Library staleness.

Logging is configured once at process startup. A null destination selects the writable application-data log. A configured destination must use normalized forward-slash relative syntax, without `..`, a Windows drive, or a backslash, anchored beneath the application root. Rotation occurs after `rotation_max_bytes`; `retention_files` counts rotated backups. Configured application paths, log destinations, and MusicBrainz contact identity are redacted from rendered messages and exception text. Logging changes take effect after process restart and never mark a Library stale.

## Companion And Unprocessed Controls

`companions.enabled` allows new Add/Organize/Refresh Plans to create actions for unmanaged same-stem lyrics and directory artwork, and allows Check to discover unmanaged companion candidates. Disabling stops those new actions and that unmanaged Check classification only — it never deletes managed companion state, alters recorded Plan sources or events, suppresses Check or its managed/recorded diagnostics, suppresses recovery/History/Undo, or changes an existing Plan. When `unprocessed.enabled` alone requests Add inventory, companion classification still reserves recognized lyrics/artwork from leftovers without creating companion actions, snapshots, IDs, or dependencies.

`unprocessed.enabled` independently allows new Add review to include regular files left unclaimed by music and companion classification. `unprocessed.directory` is exactly one portable component: rejects path separators, roots, `.`/`..`, trailing dots or spaces, control and Windows-invalid characters, and reserved Windows device names; the destination stays under the selected source root. `result_preview_limit` bounds presentation only, never the durable candidate/action set.

These controls participate in the Plan-audit `config_hash` but not Library path-policy identity. Both default to disabled; disabling never rewrites prior durable state. The unprocessed directory is recorded indirectly in every action's exact source/target shape, and the preview limit is copied into the Plan summary. Apply, Check, History, and Undo never consult the current unprocessed toggle, directory, or preview limit when interpreting recorded evidence.

## ArtistIdConfig

Artist IDs are automatic internal path values, not Track/Library/Artist entity IDs. TOML stores only generation tunables: `max_length` (positive maximum generated length) and `fallback_id` (non-empty ID used when source text has no usable characters). `fallback_id` must be non-empty ASCII letters, digits, or underscores with optional single internal hyphens (no leading/trailing or repeated hyphens); invalid values are rejected at load/save because the value can flow directly into generated paths.

## Metadata And Collision Policy

Metadata policy controls which tag fields are required for plan creation.

`album_year_resolution` controls the effective album year for `{year}` rendering when a planning batch sees related tracks in one album group (raw per-track `TrackMetadata.year` unchanged): `latest` (default) newest usable year; `oldest` oldest; `most_frequent` most common, ties choosing the latest tied year. Missing years are ignored when at least one usable year exists; when none exists, `{year}` keeps the empty placeholder rendering.

Collision policy controls what plan creation records when a target exists, a duplicate content hash is known, or required metadata is missing. Current policy: block target conflicts, skip duplicate hashes, block missing required metadata.

The local Web UI may edit settings, validate settings, and preview PathPolicy output; it must use config usecases and adapters, never reading or writing TOML from route logic.
