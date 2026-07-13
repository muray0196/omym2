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
    stage_code TEXT,
    completed_units INTEGER,
    total_units INTEGER,
    progress_message TEXT,
    result_kind TEXT CHECK (
        result_kind IS NULL OR
        result_kind IN ('plan_created', 'registered_without_plan', 'check_completed', 'run_completed')
    ),
    result_json TEXT,
    error_code TEXT CHECK (
        error_code IS NULL OR
        error_code IN ('operation_interrupted', 'metadata_read_failed', 'operation_failed')
    ),
    error_json TEXT,
    requested_at TEXT NOT NULL,
    started_at TEXT,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    result_expires_at TEXT,
    tombstone_expires_at TEXT,
    CHECK (
        (completed_units IS NULL AND total_units IS NULL) OR
        (
            completed_units IS NOT NULL AND
            total_units IS NOT NULL AND
            completed_units >= 0 AND
            total_units >= 0 AND
            completed_units <= total_units
        )
    ),
    CHECK (
        stage_code IS NULL OR
        (
            stage_code GLOB '[a-z]*' AND
            stage_code NOT GLOB '*[^a-z0-9_]*' AND
            stage_code NOT GLOB '*__*' AND
            substr(stage_code, -1) <> '_'
        )
    ),
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
        tombstone_expires_at IS NULL OR
        (result_expires_at IS NOT NULL AND tombstone_expires_at >= result_expires_at)
    ),
    CHECK (
        (status = 'queued' AND started_at IS NULL AND completed_at IS NULL AND
            result_kind IS NULL AND result_json IS NULL AND error_code IS NULL AND error_json IS NULL AND
            result_expires_at IS NULL AND tombstone_expires_at IS NULL) OR
        (status = 'running' AND started_at IS NOT NULL AND completed_at IS NULL AND
            result_kind IS NULL AND result_json IS NULL AND error_code IS NULL AND error_json IS NULL AND
            result_expires_at IS NULL AND tombstone_expires_at IS NULL) OR
        (status = 'succeeded' AND started_at IS NOT NULL AND completed_at IS NOT NULL AND
            error_code IS NULL AND error_json IS NULL AND
            result_expires_at IS NOT NULL AND tombstone_expires_at IS NOT NULL) OR
        (status = 'failed' AND started_at IS NOT NULL AND completed_at IS NOT NULL AND
            result_kind IS NULL AND result_json IS NULL AND
            result_expires_at IS NOT NULL AND tombstone_expires_at IS NOT NULL) OR
        (status = 'interrupted' AND completed_at IS NOT NULL AND
            result_kind IS NULL AND result_json IS NULL AND
            (error_code IS NULL OR error_code = 'operation_interrupted') AND
            result_expires_at IS NOT NULL AND tombstone_expires_at IS NOT NULL)
    ),
    CHECK (
        result_kind IS NULL OR
        (result_kind = 'plan_created' AND kind IN ('add_plan', 'organize_plan', 'refresh_plan', 'undo_plan')) OR
        (result_kind = 'registered_without_plan' AND kind = 'organize_plan') OR
        (result_kind = 'check_completed' AND kind = 'check') OR
        (result_kind = 'run_completed' AND kind = 'apply_plan')
    )
);

CREATE UNIQUE INDEX uq_operations_idempotency_key
ON operations (idempotency_key);

CREATE UNIQUE INDEX uq_operations_single_active
ON operations ((1))
WHERE status IN ('queued', 'running');

CREATE INDEX idx_operations_status_updated
ON operations (status, updated_at, operation_id);

CREATE INDEX idx_operations_result_expiry
ON operations (result_expires_at, operation_id);

CREATE INDEX idx_operations_tombstone_expiry
ON operations (tombstone_expires_at, operation_id);

CREATE INDEX idx_operations_plan
ON operations (plan_id, operation_id);

CREATE INDEX idx_operations_run
ON operations (run_id, operation_id);
