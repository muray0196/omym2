CREATE INDEX idx_plans_created ON plans (created_at, plan_id);
CREATE INDEX idx_plans_library_created ON plans (library_id, created_at, plan_id);
