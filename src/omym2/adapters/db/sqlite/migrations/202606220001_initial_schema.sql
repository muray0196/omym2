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
    metadata_json TEXT NOT NULL,
    status TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_tracks_library_id
ON tracks (library_id);

CREATE INDEX idx_tracks_library_content_hash
ON tracks (library_id, content_hash);

CREATE TABLE plans (
    plan_id TEXT PRIMARY KEY,
    library_id TEXT NOT NULL REFERENCES libraries (library_id) ON DELETE RESTRICT,
    plan_type TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    library_root_at_plan TEXT NOT NULL,
    summary_json TEXT NOT NULL
);

CREATE INDEX idx_plans_library_id
ON plans (library_id);

CREATE TABLE plan_actions (
    action_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES plans (plan_id) ON DELETE CASCADE,
    library_id TEXT NOT NULL REFERENCES libraries (library_id) ON DELETE RESTRICT,
    track_id TEXT REFERENCES tracks (track_id) ON DELETE SET NULL,
    action_type TEXT NOT NULL,
    source_path TEXT,
    target_path TEXT,
    content_hash_at_plan TEXT,
    metadata_hash_at_plan TEXT,
    status TEXT NOT NULL,
    reason TEXT,
    sort_order INTEGER NOT NULL
);

CREATE INDEX idx_plan_actions_plan_sort
ON plan_actions (plan_id, sort_order, action_id);

CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES plans (plan_id) ON DELETE RESTRICT,
    library_id TEXT NOT NULL REFERENCES libraries (library_id) ON DELETE RESTRICT,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    error_summary TEXT
);

CREATE INDEX idx_runs_library_started
ON runs (library_id, started_at, run_id);

CREATE INDEX idx_runs_plan_id
ON runs (plan_id);

CREATE TABLE file_events (
    event_id TEXT PRIMARY KEY,
    library_id TEXT NOT NULL REFERENCES libraries (library_id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL REFERENCES runs (run_id) ON DELETE CASCADE,
    plan_action_id TEXT NOT NULL REFERENCES plan_actions (action_id) ON DELETE RESTRICT,
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

CREATE INDEX idx_file_events_run_sequence
ON file_events (run_id, sequence_no, event_id);
