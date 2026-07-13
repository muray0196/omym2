CREATE TEMP TABLE m4_undo_action_event_candidates (
    undo_action_id TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    source_run_id TEXT NOT NULL,
    PRIMARY KEY (undo_action_id, source_event_id)
);

INSERT INTO m4_undo_action_event_candidates (
    undo_action_id,
    source_event_id,
    source_run_id
)
SELECT
    undo_action.action_id,
    source_event.event_id,
    source_event.run_id
FROM plans AS undo_plan
JOIN plan_actions AS undo_action
    ON undo_action.plan_id = undo_plan.plan_id
   AND undo_action.library_id = undo_plan.library_id
JOIN file_events AS source_event
    ON source_event.library_id = undo_action.library_id
   AND source_event.source_path = undo_action.target_path
   AND source_event.event_type = 'move_file'
   AND source_event.status = 'succeeded'
   AND source_event.completed_at IS NOT NULL
   AND source_event.completed_at <= undo_plan.created_at
JOIN plan_actions AS source_action
    ON source_action.action_id = source_event.plan_action_id
   AND source_action.library_id = source_event.library_id
   AND source_action.track_id = undo_action.track_id
   AND source_action.action_type = 'move'
   AND source_action.status = 'applied'
   AND source_action.source_path = source_event.source_path
   AND source_action.target_path = source_event.target_path
JOIN runs AS source_run
    ON source_run.run_id = source_event.run_id
   AND source_run.plan_id = source_action.plan_id
   AND source_run.library_id = source_event.library_id
   AND source_run.status IN ('succeeded', 'partial_failed', 'failed')
   AND source_run.completed_at IS NOT NULL
   AND source_run.completed_at <= undo_plan.created_at
JOIN plans AS source_plan
    ON source_plan.plan_id = source_run.plan_id
   AND source_plan.library_id = source_run.library_id
   AND source_plan.config_hash = undo_plan.config_hash
   AND source_plan.status IN ('applied', 'partial_failed', 'failed')
WHERE undo_plan.plan_type = 'undo'
  AND undo_action.action_type = 'move';

CREATE TEMP TABLE m4_migration_guard (
    invalid INTEGER NOT NULL CHECK (invalid = 0)
);

INSERT INTO m4_migration_guard (invalid)
SELECT 1
WHERE EXISTS (
    SELECT undo_action.action_id
    FROM plans AS undo_plan
    JOIN plan_actions AS undo_action
        ON undo_action.plan_id = undo_plan.plan_id
    LEFT JOIN m4_undo_action_event_candidates AS candidate
        ON candidate.undo_action_id = undo_action.action_id
    WHERE undo_plan.plan_type = 'undo'
    GROUP BY undo_action.action_id
    HAVING COUNT(candidate.source_event_id) <> 1
);

INSERT INTO m4_migration_guard (invalid)
SELECT 1
WHERE EXISTS (
    SELECT undo_plan.plan_id
    FROM plans AS undo_plan
    LEFT JOIN plan_actions AS undo_action
        ON undo_action.plan_id = undo_plan.plan_id
    LEFT JOIN m4_undo_action_event_candidates AS candidate
        ON candidate.undo_action_id = undo_action.action_id
    WHERE undo_plan.plan_type = 'undo'
    GROUP BY undo_plan.plan_id
    HAVING COUNT(undo_action.action_id) = 0
        OR COUNT(DISTINCT candidate.source_run_id) <> 1
);

INSERT INTO m4_migration_guard (invalid)
SELECT 1
WHERE EXISTS (
    SELECT undo_action.plan_id
    FROM m4_undo_action_event_candidates AS candidate
    JOIN plan_actions AS undo_action
        ON undo_action.action_id = candidate.undo_action_id
    GROUP BY undo_action.plan_id, candidate.source_event_id
    HAVING COUNT(DISTINCT candidate.undo_action_id) <> 1
);

ALTER TABLE plans
ADD COLUMN source_run_id TEXT REFERENCES runs (run_id) ON DELETE RESTRICT;

ALTER TABLE plan_actions
ADD COLUMN reverses_event_id TEXT REFERENCES file_events (event_id) ON DELETE RESTRICT;

UPDATE plans
SET source_run_id = (
    SELECT candidate.source_run_id
    FROM plan_actions AS undo_action
    JOIN m4_undo_action_event_candidates AS candidate
        ON candidate.undo_action_id = undo_action.action_id
    WHERE undo_action.plan_id = plans.plan_id
    LIMIT 1
)
WHERE plan_type = 'undo';

UPDATE plan_actions
SET reverses_event_id = (
    SELECT candidate.source_event_id
    FROM m4_undo_action_event_candidates AS candidate
    WHERE candidate.undo_action_id = plan_actions.action_id
)
WHERE plan_id IN (
    SELECT plan_id
    FROM plans
    WHERE plan_type = 'undo'
);

CREATE UNIQUE INDEX uq_runs_plan_id
ON runs (plan_id);

CREATE INDEX idx_plans_source_run_status
ON plans (source_run_id, status, created_at, plan_id);

CREATE UNIQUE INDEX uq_plans_active_undo_source_run
ON plans (source_run_id)
WHERE source_run_id IS NOT NULL
  AND status IN ('ready', 'applying', 'applied');

CREATE INDEX idx_plan_actions_reverse_event_status
ON plan_actions (reverses_event_id, status, action_id);

CREATE UNIQUE INDEX uq_plan_actions_plan_reverse_event
ON plan_actions (plan_id, reverses_event_id)
WHERE reverses_event_id IS NOT NULL;

DROP TABLE m4_migration_guard;

DROP TABLE m4_undo_action_event_candidates;
