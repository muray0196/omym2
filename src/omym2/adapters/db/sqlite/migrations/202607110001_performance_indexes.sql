CREATE INDEX idx_check_issues_check_run_id
ON check_issues (check_run_id);

CREATE INDEX idx_file_events_library_status
ON file_events (library_id, status, sequence_no);

DROP INDEX idx_tracks_library_id;
DROP INDEX idx_plans_library_id;
