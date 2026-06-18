# MVP Completion Checklist

The MVP is complete when:

* `setup` can create config / DB.
* `setup` can scan the existing Library, capture file snapshots, and register tracks.
* Registered tracks receive stable UUIDv7-based `track_id` values.
* `config.toml` can be loaded.
* Canonical paths can be generated as Library-root-relative paths according to path policy.
* Track `current_path` and `canonical_path` are stored as Library-root-relative paths in the DB.
* An `add` plan can be created from the CLI.
* A plan can be applied from the CLI.
* Apply creates a Run before Library music file mutation.
* Apply records a file_event as pending before Library music file mutation.
* Apply updates file_event / run / plan status after execution.
* Run / file_events remain in the DB.
* A Plan cannot be applied twice.
* `refresh` can create a relocation plan.
* `organize` can create an organization plan for the existing Library.
* `check` can detect basic inconsistencies between the DB and the filesystem.
* `undo` can create an undo plan, and apply can perform basic rollback.
* The Web UI can edit the main settings.
* The Web UI can validate settings.
