---
name: config-schema-change
description: Safety checklist for changes to the persisted TOML application-config contract — the AppConfig dataclass shape, TOML keys, defaults, allowed values or enums, validation rules, and config serialization such as the TOML store and web settings serializers or choices lists. Use before designing or reviewing any change to settings save or load paths. Do not use it for code that merely reads an existing config value inside a feature, and do not use it for runtime environment-variable configuration, which is docs/development/harness.md's domain.
---

# Config Schema Change

Authoritative doc: `docs/contracts/config.md`. Test policy: `docs/development/testing.md`'s
Contract Change Test Requirements table, "Config contract" row.

## Non-negotiable invariants

1. Domain and usecases never read TOML directly; `src/omym2/adapters/config/`
   owns parsing, validation, defaulting, and saving.
2. Config files stay under the application root
   (`src/omym2/adapters/config/application_paths.py`), excluding user-selected
   Library and Incoming paths.
3. A key missing from an on-disk file silently fills its documented default at
   load with no error (`src/omym2/adapters/config/config_validator.py`). An
   unknown key — including one you removed or renamed — fails validation
   instead of being ignored, and bumping `CONFIG_VERSION`
   (`src/omym2/config.py`) rejects every file still at the old version, since
   no version-based migration exists yet. Decide and test the exact
   existing-file rejection or defaulting behavior for every removed/renamed
   key or version bump. Do not add a compatibility layer.
4. Verify allowed values and enums against the constants in
   `src/omym2/config.py` (e.g. `ALLOWED_UI_THEMES`) rather than assuming
   `docs/contracts/config.md` is exhaustive; when the doc lags the source,
   update the doc in the same change (open `update-docs`).
5. `config_revision` is opaque raw-storage concurrency state, not an AppConfig
   field or TOML key. Web and CLI saves acquire the shared exclusive lock,
   recheck the expected revision, and use the Config adapter's atomic replace.
   Never add last-write-wins or update SQLite Library status as part of the
   Config file write; effective staleness is derived from fingerprints.

## Every changed or added key touches these surfaces

| Surface | File |
| --- | --- |
| Section dataclass, defaults, `__post_init__` validation | `src/omym2/domain/models/app_config.py` |
| TOML key allow-list, type/choice rule | `src/omym2/adapters/config/config_validator.py` |
| TOML writer | `src/omym2/adapters/config/toml_config_store.py` |
| Future typed Web settings boundary | Pydantic schemas under `src/omym2/adapters/web/schemas/` and routes under `src/omym2/adapters/web/routes/`; routes call Settings usecases and never import TOML validators or serializers |
| Raw revision read/CAS DTO and ConfigStore port | `src/omym2/features/common_ports.py`, `src/omym2/features/settings/` |
| Contract doc | `docs/contracts/config.md` (open `update-docs`) |
| Plan/Library staleness fingerprint, only if the field can change generated paths | `src/omym2/domain/services/config_fingerprint.py` |

`config_fingerprint.py` is not summarized anywhere in `docs/`; treat it as
source of truth and verify directly. A field left out of `_app_config_payload`
or `_path_policy_payload`/`_artist_id_payload` silently stops affecting
`config_hash` / `path_policy_hash`, so already-created Plans or registered
Libraries would not detect the settings change as stale.

## Overlap with other skills

| Overlap | Order |
| --- | --- |
| Key affects PathPolicy rendering, stored paths, Library identity, or registration | This skill first, then `path-identity-safety` |
| Change could affect behavior of already-created Plans | `plan-apply-safety` owns that boundary; open it — this skill does not restate its rule |

## Procedure

1. Confirm scope: AppConfig shape, TOML keys, defaults, allowed values,
   validation, or serialization. Reading an already-defined value, or
   changing an environment variable, is out of scope — see
   `docs/development/harness.md`.
2. Edit every surface in the table above in the same change.
   If the change touches save/load concurrency rather than the TOML schema,
   edit only the raw-revision/CAS surfaces and do not invent a TOML key.
3. Define and test the existing-file behavior from invariant 3 for the
   specific key(s) touched, without adding compatibility handling.
4. If the field affects generated paths or fingerprints, update
   `config_fingerprint.py` per the table above.
5. If PathPolicy, stored paths, or Library identity are affected, open
   `path-identity-safety`. If already-created Plans could be affected, open
   `plan-apply-safety` instead of deciding that here.

## Done means

- Tests cover load, save, validation, defaults, and existing-file rejection or
  defaulting behavior per `docs/development/testing.md`'s Contract Change Test
  Requirements table. Anchors: `tests/adapters/config/test_toml_config_store.py`
  and `tests/domain/test_app_config.py`; when the typed Web Settings slice
  exists, its route-level Pydantic contract tests are required too.
- `docs/contracts/config.md` reflects the new shape in the same change.

## Stop and report when

- The change would require domain or usecase code to parse TOML directly.
- An existing on-disk config file's fate for a missing, removed, or renamed
  key is undecided.
- A new/changed field would affect generated paths or Plan/Library staleness
  but there is no place for it in `config_fingerprint.py`'s payload builders.
