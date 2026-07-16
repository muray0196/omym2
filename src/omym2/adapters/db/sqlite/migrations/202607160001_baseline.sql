CREATE TABLE libraries (
    library_id TEXT PRIMARY KEY,
    root_path TEXT NOT NULL UNIQUE,
    path_policy_hash TEXT NOT NULL,
    registered_at TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE tracks (
    track_id TEXT PRIMARY KEY,
    library_id TEXT NOT NULL REFERENCES libraries (library_id) ON DELETE RESTRICT,
    current_path TEXT NOT NULL,
    canonical_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    metadata_hash TEXT NOT NULL,
    size INTEGER CHECK (size IS NULL OR size >= 0),
    mtime TEXT,
    metadata_json TEXT NOT NULL,
    status TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE companion_assets (
    companion_asset_id TEXT PRIMARY KEY,
    library_id TEXT NOT NULL REFERENCES libraries (library_id) ON DELETE RESTRICT,
    kind TEXT NOT NULL,
    owner_track_id TEXT NOT NULL REFERENCES tracks (track_id) ON DELETE RESTRICT,
    current_path TEXT NOT NULL,
    canonical_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    size INTEGER CHECK (size IS NULL OR size >= 0),
    mtime TEXT,
    status TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE plans (
    plan_id TEXT PRIMARY KEY,
    library_id TEXT NOT NULL REFERENCES libraries (library_id) ON DELETE RESTRICT,
    source_run_id TEXT REFERENCES runs (run_id) ON DELETE RESTRICT,
    plan_type TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    library_root_at_plan TEXT NOT NULL,
    source_root_at_plan TEXT,
    summary_json TEXT NOT NULL
);

CREATE TABLE plan_actions (
    action_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES plans (plan_id) ON DELETE CASCADE,
    library_id TEXT NOT NULL REFERENCES libraries (library_id) ON DELETE RESTRICT,
    track_id TEXT REFERENCES tracks (track_id) ON DELETE SET NULL,
    action_type TEXT NOT NULL,
    source_path TEXT,
    target_path TEXT,
    reverses_event_id TEXT REFERENCES file_events (event_id) ON DELETE RESTRICT,
    companion_asset_id TEXT,
    owner_action_id TEXT REFERENCES plan_actions (action_id) ON DELETE SET NULL,
    content_hash_at_plan TEXT,
    metadata_hash_at_plan TEXT,
    artist_name_diagnostics_json TEXT CHECK (
        artist_name_diagnostics_json IS NULL
        OR (
            json_valid(artist_name_diagnostics_json)
            AND json_type(artist_name_diagnostics_json) = 'object'
        )
    ),
    status TEXT NOT NULL,
    reason TEXT,
    sort_order INTEGER NOT NULL
);

CREATE UNIQUE INDEX uq_plan_actions_action_plan
ON plan_actions (action_id, plan_id);

CREATE TRIGGER plan_actions_owner_same_plan_insert
BEFORE INSERT ON plan_actions
WHEN NEW.owner_action_id IS NOT NULL
    AND NOT EXISTS (
        SELECT 1
        FROM plan_actions AS owner
        WHERE owner.action_id = NEW.owner_action_id
          AND owner.plan_id = NEW.plan_id
    )
BEGIN
    SELECT RAISE(ABORT, 'owner_action_id must reference an action in the same Plan');
END;

CREATE TRIGGER plan_actions_owner_same_plan_update
BEFORE UPDATE OF owner_action_id, plan_id ON plan_actions
WHEN (
    NEW.owner_action_id IS NOT NULL
    AND NOT EXISTS (
        SELECT 1
        FROM plan_actions AS owner
        WHERE owner.action_id = NEW.owner_action_id
          AND owner.plan_id = NEW.plan_id
    )
)
OR (
    NEW.plan_id <> OLD.plan_id
    AND EXISTS (
        SELECT 1
        FROM plan_actions AS owned
        WHERE owned.owner_action_id = OLD.action_id
          AND owned.plan_id <> NEW.plan_id
    )
)
BEGIN
    SELECT RAISE(ABORT, 'owner_action_id must reference an action in the same Plan');
END;

CREATE TABLE plan_action_dependencies (
    plan_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    depends_on_action_id TEXT NOT NULL,
    PRIMARY KEY (action_id, depends_on_action_id),
    CHECK (action_id <> depends_on_action_id),
    FOREIGN KEY (action_id, plan_id)
        REFERENCES plan_actions (action_id, plan_id) ON DELETE CASCADE,
    FOREIGN KEY (depends_on_action_id, plan_id)
        REFERENCES plan_actions (action_id, plan_id) ON DELETE CASCADE
);

CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES plans (plan_id) ON DELETE RESTRICT,
    library_id TEXT NOT NULL REFERENCES libraries (library_id) ON DELETE RESTRICT,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    error_summary TEXT
);

CREATE TABLE file_events (
    event_id TEXT PRIMARY KEY,
    library_id TEXT NOT NULL REFERENCES libraries (library_id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL REFERENCES runs (run_id) ON DELETE CASCADE,
    plan_action_id TEXT NOT NULL REFERENCES plan_actions (action_id) ON DELETE RESTRICT,
    companion_asset_id TEXT,
    event_type TEXT NOT NULL,
    source_path TEXT NOT NULL,
    target_path TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    error_code TEXT,
    error_message TEXT,
    sequence_no INTEGER NOT NULL
);

CREATE TABLE operations (
    operation_id TEXT PRIMARY KEY,
    library_id TEXT REFERENCES libraries (library_id) ON DELETE RESTRICT,
    plan_id TEXT REFERENCES plans (plan_id) ON DELETE RESTRICT,
    run_id TEXT REFERENCES runs (run_id) ON DELETE RESTRICT,
    kind TEXT NOT NULL CHECK (
        kind IN ('add_plan', 'organize_plan', 'refresh_plan', 'check', 'apply_plan', 'undo_plan')
    ),
    status TEXT NOT NULL CHECK (
        status IN ('queued', 'running', 'succeeded', 'failed', 'interrupted')
    ),
    idempotency_key TEXT NOT NULL CHECK (idempotency_key <> ''),
    request_fingerprint TEXT NOT NULL CHECK (request_fingerprint <> ''),
    result_kind TEXT CHECK (
        result_kind IS NULL
        OR result_kind IN ('plan_created', 'registered_without_plan', 'check_completed', 'run_completed')
    ),
    result_json TEXT,
    error_code TEXT CHECK (
        error_code IS NULL
        OR error_code IN ('operation_interrupted', 'metadata_read_failed', 'operation_failed')
    ),
    error_json TEXT,
    requested_at TEXT NOT NULL,
    started_at TEXT,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    result_expires_at TEXT,
    tombstone_expires_at TEXT,
    CHECK (result_json IS NULL OR json_valid(result_json)),
    CHECK (error_json IS NULL OR json_valid(error_json)),
    CHECK ((result_kind IS NULL) = (result_json IS NULL)),
    CHECK ((error_code IS NULL) = (error_json IS NULL)),
    CHECK (updated_at >= requested_at),
    CHECK (started_at IS NULL OR started_at >= requested_at),
    CHECK (completed_at IS NULL OR completed_at >= requested_at),
    CHECK (completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at),
    CHECK (result_expires_at IS NULL OR (completed_at IS NOT NULL AND result_expires_at >= completed_at)),
    CHECK (
        tombstone_expires_at IS NULL
        OR (result_expires_at IS NOT NULL AND tombstone_expires_at >= result_expires_at)
    ),
    CHECK (
        (status = 'queued' AND started_at IS NULL AND completed_at IS NULL
            AND result_kind IS NULL AND result_json IS NULL AND error_code IS NULL AND error_json IS NULL
            AND result_expires_at IS NULL AND tombstone_expires_at IS NULL)
        OR
        (status = 'running' AND started_at IS NOT NULL AND completed_at IS NULL
            AND result_kind IS NULL AND result_json IS NULL AND error_code IS NULL AND error_json IS NULL
            AND result_expires_at IS NULL AND tombstone_expires_at IS NULL)
        OR
        (status = 'succeeded' AND started_at IS NOT NULL AND completed_at IS NOT NULL
            AND error_code IS NULL AND error_json IS NULL
            AND result_expires_at IS NOT NULL AND tombstone_expires_at IS NOT NULL)
        OR
        (status = 'failed' AND started_at IS NOT NULL AND completed_at IS NOT NULL
            AND result_kind IS NULL AND result_json IS NULL
            AND result_expires_at IS NOT NULL AND tombstone_expires_at IS NOT NULL)
        OR
        (status = 'interrupted' AND completed_at IS NOT NULL
            AND result_kind IS NULL AND result_json IS NULL
            AND (error_code IS NULL OR error_code = 'operation_interrupted')
            AND result_expires_at IS NOT NULL AND tombstone_expires_at IS NOT NULL)
    ),
    CHECK (
        result_kind IS NULL
        OR (result_kind = 'plan_created' AND kind IN ('add_plan', 'organize_plan', 'refresh_plan', 'undo_plan'))
        OR (result_kind = 'registered_without_plan' AND kind = 'organize_plan')
        OR (result_kind = 'check_completed' AND kind = 'check')
        OR (result_kind = 'run_completed' AND kind = 'apply_plan')
    )
);

CREATE TABLE check_runs (
    check_run_id TEXT PRIMARY KEY,
    library_id TEXT NOT NULL UNIQUE REFERENCES libraries (library_id) ON DELETE RESTRICT,
    checked_at TEXT NOT NULL,
    total_count INTEGER NOT NULL
);

CREATE TABLE check_issues (
    issue_seq INTEGER PRIMARY KEY AUTOINCREMENT,
    check_run_id TEXT NOT NULL REFERENCES check_runs (check_run_id) ON DELETE CASCADE,
    library_id TEXT NOT NULL REFERENCES libraries (library_id) ON DELETE RESTRICT,
    issue_type TEXT NOT NULL,
    path TEXT,
    track_id TEXT REFERENCES tracks (track_id) ON DELETE SET NULL,
    plan_id TEXT REFERENCES plans (plan_id) ON DELETE SET NULL,
    companion_asset_id TEXT,
    detail TEXT
);

CREATE TABLE accepted_artist_names (
    source_key TEXT NOT NULL PRIMARY KEY CHECK (trim(source_key) <> ''),
    source_name TEXT NOT NULL CHECK (trim(source_name) <> ''),
    resolved_name TEXT NOT NULL CHECK (trim(resolved_name) <> ''),
    provider TEXT NOT NULL CHECK (provider IN ('musicbrainz')),
    provider_artist_id TEXT NOT NULL CHECK (
        trim(provider_artist_id) <> '' AND length(provider_artist_id) = 36
    ),
    selected_name_kind TEXT NOT NULL CHECK (selected_name_kind IN ('alias', 'name')),
    selected_locale TEXT,
    accepted_at TEXT NOT NULL,
    CHECK (
        selected_locale IS NULL
        OR (selected_name_kind = 'alias' AND trim(selected_locale) <> '')
    )
);

CREATE TABLE provider_request_cadence (
    provider TEXT PRIMARY KEY,
    last_request_at TEXT NOT NULL
);

CREATE INDEX idx_tracks_current_path ON tracks (current_path, track_id);
CREATE INDEX idx_tracks_library_content_hash ON tracks (library_id, content_hash);
CREATE INDEX idx_tracks_status ON tracks (library_id, status);

CREATE INDEX idx_companion_assets_library_current_path
ON companion_assets (library_id, current_path, companion_asset_id);
CREATE INDEX idx_companion_assets_library_content_hash
ON companion_assets (library_id, content_hash);

CREATE INDEX idx_plans_created ON plans (created_at, plan_id);
CREATE INDEX idx_plans_library_created ON plans (library_id, created_at, plan_id);
CREATE INDEX idx_plans_source_run_status ON plans (source_run_id, status, created_at, plan_id);
CREATE UNIQUE INDEX uq_plans_active_undo_source_run
ON plans (source_run_id)
WHERE source_run_id IS NOT NULL
  AND status IN ('ready', 'applying', 'applied');

CREATE INDEX idx_plan_actions_plan_sort ON plan_actions (plan_id, sort_order, action_id);
CREATE INDEX idx_plan_actions_reverse_event_status ON plan_actions (reverses_event_id, status, action_id);
CREATE INDEX idx_plan_actions_status ON plan_actions (plan_id, status);
CREATE INDEX idx_plan_actions_type ON plan_actions (plan_id, action_type);
CREATE UNIQUE INDEX uq_plan_actions_plan_reverse_event
ON plan_actions (plan_id, reverses_event_id)
WHERE reverses_event_id IS NOT NULL;

CREATE INDEX idx_plan_action_dependencies_depends_on
ON plan_action_dependencies (depends_on_action_id, action_id);

CREATE INDEX idx_runs_library_started ON runs (library_id, started_at, run_id);
CREATE INDEX idx_runs_plan_id ON runs (plan_id);
CREATE INDEX idx_runs_started ON runs (started_at, run_id);
CREATE UNIQUE INDEX uq_runs_plan_id ON runs (plan_id);

CREATE INDEX idx_file_events_run_sequence ON file_events (run_id, sequence_no, event_id);
CREATE INDEX idx_file_events_library_status ON file_events (library_id, status, sequence_no);

CREATE UNIQUE INDEX uq_operations_idempotency_key ON operations (idempotency_key);
CREATE UNIQUE INDEX uq_operations_single_active
ON operations ((1))
WHERE status IN ('queued', 'running');
CREATE INDEX idx_operations_status_updated ON operations (status, updated_at, operation_id);
CREATE INDEX idx_operations_result_expiry ON operations (result_expires_at, operation_id);
CREATE INDEX idx_operations_tombstone_expiry ON operations (tombstone_expires_at, operation_id);
CREATE INDEX idx_operations_plan ON operations (plan_id, operation_id);
CREATE INDEX idx_operations_run ON operations (run_id, operation_id);

CREATE INDEX idx_check_issues_check_run_id ON check_issues (check_run_id);
CREATE INDEX idx_check_issues_library_type ON check_issues (library_id, issue_type, issue_seq);
CREATE INDEX idx_check_issues_companion_asset ON check_issues (companion_asset_id, issue_seq);
