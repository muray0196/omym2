# MVP Completion Checklist

The MVP is complete when:

* Config, DB, and internal directories are created lazily when needed.
* Missing config or DB is not an error by itself.
* `organize` can scan the existing Library read-only and capture file snapshots.
* `organize` can register a clean Library without creating a mutation Plan.
* `organize` can create an organization plan when existing Library files need to move.
* Library registration records the resolved Library root, current PathPolicy identity, registration time, and status.
* Changing PathPolicy invalidates prior Library registration.
* Managed Tracks receive stable UUIDv7-based `track_id` values.
* `config.toml` can be loaded.
* Canonical paths can be generated as Library-root-relative paths according to path policy.
* Track `current_path` and `canonical_path` are stored as Library-root-relative paths in the DB.
* `add` refuses to create a plan for an unregistered or stale Library.
* An `add` plan can be created from the CLI for a registered Library.
* A plan can be applied from the CLI.
* Apply creates a Run before Library music file mutation.
* Apply records a file_event as pending before Library music file mutation.
* Apply updates file_event / run / plan status after execution.
* Run / file_events remain in the DB.
* A Plan cannot be applied twice.
* `refresh` can create a relocation plan.
* `check` can detect basic inconsistencies between the DB and the filesystem.
* `check` can report Library registration state.
* `undo` can create an undo plan, and apply can perform basic rollback.
* The Web UI can edit the main settings.
* The Web UI can validate settings.
