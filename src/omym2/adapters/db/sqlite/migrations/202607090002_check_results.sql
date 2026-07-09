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
    detail TEXT
);

CREATE INDEX idx_check_issues_library_type
ON check_issues (library_id, issue_type, issue_seq);
