# OMYM2 Artist Naming and Intake Safety Roadmap

## Status and priority

This is an active, multi-session initiative with cross-cutting changes to configuration, metadata naming, Plan execution, persistence, Web/CLI settings, and desktop packaging.

Stages 1 and 2 are complete. Normal Add, Organize, and Refresh composition now
supports an explicit process-level development opt-in for lazy fastText-gated
MusicBrainz lookup, shares the loaded predictor and rate-limited provider, and
falls back locally when the optional runtime or model cannot load. Persisted
runtime controls and packaging hardening are the next delivery target.

The rollout order is intentional:

1. Established deterministic artist display-name preferences and the persistence foundation.
2. Delivered opt-in fastText-gated MusicBrainz English/Latin name resolution in normal Plan creation, with review diagnostics.
3. Next: harden runtime controls, packaging, and operational behavior.
4. Add companion lyrics and artwork handling.
5. Add reviewed collection of unprocessed files.

MusicBrainz-based naming is the first product outcome. Companion assets and unprocessed-file collection must not begin until the naming rollout is stable. Companion assets must be complete before unprocessed-file collection so recognized `.lrc` and artwork files are not misclassified as leftovers.

## Intended outcome

OMYM2 will provide all of the following while preserving its Plan-centered safety model:

* Automatic English/Latin naming for Japanese artist and album-artist metadata, gated by fastText and resolved through MusicBrainz.
* Editable full artist display-name preferences, separate from compact `artist_ids` path values.
* Deterministic naming precedence, provenance, and caching without changing embedded music tags.
* Runtime controls for MusicBrainz, fastText, file hashing, and logging.
* Reviewed, reversible movement of associated `.lrc` lyrics and directory artwork with their music.
* Reviewed, reversible collection of files not claimed by music or companion-asset processing into a configurable unprocessed area.

The initiative does not add tag editing, playback, remote lyrics or artwork downloads, cloud services, general-purpose file management, or automatic mutation outside a recorded Plan.

## Material decisions

### Naming and metadata boundaries

* Raw `TrackMetadata` remains the representation of tags read from the file. Automatic English/Latin names are a derived naming projection used for canonical path generation and presentation; they do not overwrite raw metadata or embedded tags.
* Full artist display-name preferences are independent from `artist_ids`. Changing a display preference must not silently rewrite a saved compact artist ID.
* PathPolicy remains pure. It receives already-resolved naming values and never loads config, reads SQLite, loads a fastText model, or calls MusicBrainz.
* The resolution precedence is:

  ```text
  explicit user preference
  -> accepted persisted MusicBrainz result
  -> new MusicBrainz lookup when eligible
  -> original metadata value
  ```

* Positive MusicBrainz results are sticky and carry provenance, the selected MusicBrainz identity, and the selected alias/name. Ordinary Plan creation does not silently replace an accepted result with a later provider response. Ambiguous or low-confidence matches remain unresolved and are surfaced for a user preference.
* MusicBrainz is the only automatic English/Latin naming source in the initial rollout. No `langid` dependency or automatic local transliteration fallback is introduced. A lookup miss, disabled network access, or provider failure preserves the original metadata value.
* Multi-artist behavior must be deterministic, preserve source order, and leave unresolved components unchanged. The exact separator contract must be made authoritative before automatic lookup is enabled.

### fastText and MusicBrainz execution

* fastText is the sole automatic language-detection gate. The initial target is the Japanese label, and lookup eligibility also requires non-Latin source text and a documented minimum confidence.
* Automatic network lookup occurs only while creating `add`, `organize`, or `refresh` Plans, or during an explicit naming-management operation. Apply, Undo, Check, history, Track browsing, and read-only inspection never initiate MusicBrainz requests.
* Apply always executes recorded PlanActions and never re-resolves names or recalculates target paths.
* MusicBrainz access is opt-in. Without an enabled provider and an available fastText model, OMYM2 uses preferences, accepted cache entries, and original metadata without blocking local operation.
* MusicBrainz matching must use deterministic acceptance criteria rather than accepting the first search result. English-locale aliases are preferred, then other Latin aliases or names; an uncertain result is treated as no result.
* Provider calls remain rate-limited, bounded by timeout and retry policy, and cached so large libraries do not repeat identical lookups. Stage 2 enforces request cadence within one composed process; Stage 3 owns persisted controls and durable cross-process cadence coordination.

### Persistence and configuration

* User-editable display-name preferences live in TOML. Derived MusicBrainz results and lookup provenance live in SQLite.
* The current config version remains unchanged. New sections and keys are optional and load with documented defaults; this initiative does not add a version-based compatibility layer.
* Config writes continue to use the existing revision/CAS and atomic-replace contract.
* Settings that directly change known canonical naming values participate in Library staleness and path-policy fingerprint decisions when the active template consumes artist naming. Provider timeout, retry, hashing, and logging controls do not affect path identity.
* A newly accepted MusicBrainz name for an artist already present in a Library must not create mixed canonical naming. `add` must require Library reconciliation when importing under the new name would diverge from existing managed tracks; `organize` owns that reconciliation.
* Existing ready Plans are not rewritten when preferences, cache entries, or runtime settings change. New Plans use the new state; Apply continues to use the recorded actions.

### File-mutation safety

* Companion assets and unprocessed files are first-class reviewed mutations. They must have recorded PlanActions and pending-before-mutation durable events with the same crash, failure, history, and Undo guarantees as music-file moves.
* Companion assets are not Tracks. Their durable identity and ownership must reference the Library and the associated Track or deterministic album grouping without changing `track_id` semantics.
* No companion or unprocessed move may overwrite an existing target. Plan-time conflicts are blocked, and targets that appear after planning fail closed during Apply.
* Every Library-managed target remains normalized and Library-root-relative. External source paths remain explicit absolute paths only where the existing import contract permits them.

## Ordered rollout

### Stage 1 — Naming foundation and artist preferences

**Outcome:** OMYM2 has a shared naming projection, editable display-name preferences, and persistent provider-result storage, with no automatic path behavior change while the feature is disabled.

**Status:** Complete. Empty preferences preserve prior path identity and local
operation requires neither a fastText model nor MusicBrainz access.

The stage establishes the separation between raw tag metadata, preferred display names, accepted provider results, and compact artist IDs. It also establishes the config and SQLite contracts needed by CLI, Web, desktop, `add`, `organize`, and `refresh` without allowing adapters to bypass feature usecases.

**Release gate met:** Existing config files load unchanged; preference changes are atomic and revision-safe; raw metadata remains unchanged; path fingerprints react only when the active path template can consume the changed naming value; and disabling the feature preserves current OMYM2 behavior.

### Stage 2 — Automatic MusicBrainz English/Latin naming

**Outcome:** Eligible Japanese artist and album-artist values are resolved during normal Plan creation and appear as reviewable canonical target paths.

**Status:** Complete for source/runtime behavior. Add, Organize, and Refresh
share the resolver and sticky cache projection, and Add or a partial Refresh
requires Organize before an executable move could introduce mixed resolved
naming.
Their PlanActions persist and expose the exact artist and album-artist source,
resolved value, provenance, and unresolved/ambiguous issue observed during
target calculation; pre-resolution blocks and Undo actions explicitly carry
no naming snapshot.

Normal CLI and Web Plan composition honors the development-only
`OMYM2_ARTIST_NAME_FASTTEXT_MODEL_PATH` process opt-in. It loads the model only
for the first eligible uncached source, reuses the predictor and provider for
the process, and treats an unavailable optional runtime or model as a local
fallback without a MusicBrainz request. Apply remains resolver-free and uses
the recorded action. The available `lid.176.ftz` file remains a local
development input; persisted enablement and a CPython 3.14 and
Windows-compatible prediction runtime/model distribution have not yet passed
the Stage 3 gate.

`add`, `organize`, and `refresh` use one shared resolver and cache contract. `organize` can reconcile existing paths after a preference or accepted resolution changes. `add` may use a resolved name for a new artist, but it must refuse mixed naming when an existing Library artist requires reconciliation. The existing `artist-ids generate` flow should reuse the shared naming result where appropriate while keeping display-name preferences and compact IDs separate.

Accepted-name cache reads and writes use the pure whole-string source-key
contract in [DOMAIN.md](docs/DOMAIN.md#artistnamesourcekey) and
[db-schema.md](docs/contracts/db-schema.md#accepted_artist_names). It is
independent from PathPolicy sanitization and preserves multi-artist text as one
opaque value.

Plan review surfaces the source value, resolved value, provenance, and unresolved/ambiguous state. Provider failure is non-fatal and falls back to the original value.

**Release gate met:** Apply performs no network or model work; identical source/config/cache state produces identical targets; offline and timeout cases remain usable; ambiguous MusicBrainz results do not become canonical automatically; and user overrides deterministically win over provider data.

### Stage 3 — Runtime controls and distribution hardening

**Outcome:** MusicBrainz naming and supporting operational behavior can be configured consistently from the persisted settings boundary and used safely by CLI, browser-hosted Web, and the packaged Windows application.

The runtime-control scope includes:

* MusicBrainz enablement, application/contact identity, timeout, retry limit, rate limit, and cache behavior.
* fastText model location and minimum confidence.
* File-hash read chunk sizing.
* Log destination, level, rotation size, and retention, while preserving a writable application-data default and avoiding packaged-resource directories.

The fastText dependency and selected language-identification model must have an explicit redistribution, size, licensing, Python 3.14, and Windows packaging decision. Automatic lookup must not be enabled by default in packaged builds until the native dependency and model pass packaged smoke validation.

**Release gate:** Settings round-trip through TOML, CLI, and Web without lost updates; operational-only changes do not mark a Library stale; logs redact sensitive values; hashing changes do not change content-hash results; and packaged Windows builds can load the model or degrade clearly to local-only naming.

### Stage 4 — Companion lyrics and artwork

**Outcome:** OMYM2 discovers, reviews, moves, checks, and undoes associated `.lrc`, `.jpg`, and `.png` files as part of music organization without hidden filesystem side effects.

A same-stem `.lrc` belongs to one source track. Directory artwork is planned once under a deterministic ownership rule rather than once per track. Companion handling applies wherever an audio move can occur, including import, organization, metadata-driven relocation, and Undo.

The stage requires an additive persistence model and explicit action/event contracts before any adapter begins moving assets. Companion failures must remain distinguishable from audio failures and must not falsely report a fully successful Run.

**Release gate:** Golden source/target fixtures prove Plan, Apply, partial failure, crash inspection, Check, and Undo behavior; shared artwork is never duplicated or moved more than once; and collision handling never overwrites user files.

### Stage 5 — Unprocessed-file collection

**Outcome:** Files left unclaimed after music and companion classification can be reviewed and moved under `<source-root>/<unprocessed-directory>/` while preserving their source-root-relative paths.

The initial rollout is opt-in and Plan-first. It operates only on regular files observed under the selected source root, excludes symlinks, OMYM2 internal data, the unprocessed destination itself, and any path already claimed by music or companion actions. Unsupported audio and unrelated files may be included only when they are visible as individual reviewed actions.

The directory name and result-preview limit are configurable. Occupied destinations are blocked rather than overwritten or silently renamed. Apply revalidates source identity before each move, and Undo restores the recorded original path through durable events.

**Release gate:** Companion assets are excluded from leftovers; overlapping source/Library/Incoming roots cannot escape their allowed boundary; dry review accurately reports every candidate; interrupted moves remain diagnosable; and disabling collection stops new collection Plans without damaging previously managed state.

## Cross-cutting validation and release requirements

* Network behavior is tested with deterministic adapter fixtures; normal automated tests do not depend on live MusicBrainz.
* Naming fixtures cover Japanese detection, low-confidence classification, MusicBrainz ambiguity, cached results, user overrides, offline operation, Unicode normalization, and multi-artist ordering.
* End-to-end filesystem fixtures cover Plan, Apply, Check, history, crash/pending-event handling, and Undo for audio, lyrics, artwork, and unprocessed files.
* Large-library validation measures fastText startup, cache effectiveness, MusicBrainz request bounds, hash throughput, memory use, and exclusive-operation duration.
* Config and DB changes remain additive and are validated against existing user state. Applied migrations are never edited or reordered.
* Status, reason, action, and event additions are defined in their authoritative contracts before persistence or UI exposure.
* CLI, Web, and desktop use the same feature usecases, availability rules, and disabled reasons; no surface implements an independent naming or file-movement policy.

## Rollback requirements

* Automatic MusicBrainz lookup, companion processing, and unprocessed collection remain independently disableable so a release can stop creating new behavior without rewriting existing Plans or managed state.
* Disabling MusicBrainz does not delete preferences or accepted cache entries and does not revert already-recorded Plan targets.
* Saving new optional config keys can make the file unreadable to an older binary that rejects unknown keys. Downgrade instructions must require restoration of a pre-change config copy rather than implying transparent backward compatibility.
* DB migrations must be additive. Before a release persists new action/event values or companion state, downgrade behavior and backup requirements must be documented and exercised.
* A binary that does not understand new companion or unprocessed action types must not apply those Plans. Ready Plans using new action types must be applied or cancelled before downgrade.
* No rollback procedure may infer the result of a pending filesystem mutation. Pending events remain manual-review items under the existing recovery model.

## Completion and roadmap clearing

As each stage stabilizes, durable product, config, storage, path, execution, status, and packaging decisions move into their authoritative documents. This file keeps only the remaining cross-stage ordering, material risks, and release/rollback constraints.

When all stages meet their release gates and no cross-cutting uncertainty remains, clear this file to an explicit no-active-roadmap state. Keep `ROADMAP.md` tracked; do not delete it.
