CREATE INDEX idx_tracks_current_path ON tracks (current_path, track_id);
CREATE INDEX idx_tracks_status       ON tracks (library_id, status);
CREATE INDEX idx_plan_actions_status ON plan_actions (plan_id, status);
CREATE INDEX idx_plan_actions_type   ON plan_actions (plan_id, action_type);
CREATE INDEX idx_runs_started        ON runs (started_at, run_id);
