ALTER TABLE plans
ADD COLUMN source_root_at_plan TEXT;

ALTER TABLE check_issues
ADD COLUMN companion_asset_id TEXT;

CREATE INDEX idx_check_issues_companion_asset
ON check_issues (companion_asset_id, issue_seq);
