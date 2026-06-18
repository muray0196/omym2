# Testing

This document is authoritative for test requirements and test ordering.

Architecture rules are in [../ARCHITECTURE.md](../ARCHITECTURE.md), domain rules are in [domain.md](domain.md), execution semantics are in [execution.md](execution.md), and storage rules are in [storage.md](storage.md).

## Architecture Tests

Architecture tests should be written early to make later implementation hard to place in the wrong layer.

Required architecture tests:

* source files follow naming conventions
* usecases do not import concrete SQLite or filesystem adapters
* domain does not import adapters or platform
* forbidden dependencies remain forbidden

## Unit Tests

Unit tests should cover pure domain behavior and usecases through ports and fakes.

Initial unit focus:

* AppConfig and validation behavior
* typed IDs through IdGenerator
* Track identity stability
* Library-root-relative path normalization
* PathPolicy canonical path generation
* metadata and content fingerprint policies
* CollisionPolicy and DuplicatePolicy
* PlanAction status / reason behavior
* blocked vs failed behavior

## Integration Tests

Integration tests should cover adapters and vertical slices once their dependencies exist.

Initial integration focus:

* TOML config load / save / validation
* SQLite migrations and repositories
* DB path under app root `.data/`
* FileScanner behavior
* FileSnapshotReader behavior
* setup workspace creation and initial scan
* add plan persistence
* apply durable operation log behavior
* refresh, organize, check, history, and undo vertical slices

## Fixture Policy

Use in-memory repositories for usecase tests.

Use fixed Clock and IdGenerator ports in tests so time and IDs are deterministic.

Filesystem fixtures should be minimal and task-focused. Read-only filesystem fixtures are appropriate for FileScanner, metadata, hashing, and FileSnapshotReader tests. File-moving fixtures should wait until the apply vertical slice because apply is the first phase that mutates Library music files.

## Tests to Write First

```text
test_source_files_follow_naming_convention
test_usecase_does_not_import_concrete_sqlite_or_filesystem_adapter
test_domain_does_not_import_adapters_or_platform
test_config_loads_default
test_config_validation_fails_invalid_path_policy
test_db_path_is_under_app_root_data
test_track_id_is_generated_by_id_generator
test_track_id_is_not_derived_from_path_hash_or_metadata
test_track_paths_are_stored_relative_to_library_root
test_path_policy_generates_relative_path_without_hash_suffix
test_file_scanner_returns_file_scan_entries_not_snapshots
test_file_snapshot_reader_captures_metadata_and_hash
test_sqlite_migrations_create_required_tables
test_setup_creates_workspace_config_and_db
test_setup_scans_existing_library_when_enabled
test_setup_registers_tracks_with_relative_paths
test_add_plan_contains_move_action
test_add_plan_detects_target_conflict
test_add_plan_skips_duplicate_hash
test_add_plan_blocks_missing_required_metadata
test_apply_creates_run_before_file_move
test_apply_records_file_event_pending_before_file_move
test_apply_moves_file_and_updates_track
test_apply_marks_run_partial_failed_when_move_fails
test_plan_cannot_be_applied_twice
test_apply_uses_recorded_plan_action_target_path_not_latest_config
test_apply_expires_plan_when_library_root_changed
test_refresh_keeps_same_track_id_after_metadata_change
test_organize_creates_plan_for_misplaced_library_file
test_check_detects_missing_file_from_db
test_undo_creates_undo_plan_from_run
```
