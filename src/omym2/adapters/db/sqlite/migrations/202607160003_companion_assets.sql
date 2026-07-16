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

CREATE INDEX idx_companion_assets_library_current_path
ON companion_assets (library_id, current_path, companion_asset_id);

CREATE INDEX idx_companion_assets_library_content_hash
ON companion_assets (library_id, content_hash);

ALTER TABLE plan_actions
ADD COLUMN companion_asset_id TEXT;

ALTER TABLE plan_actions
ADD COLUMN owner_action_id TEXT
REFERENCES plan_actions (action_id) ON DELETE SET NULL;

ALTER TABLE file_events
ADD COLUMN companion_asset_id TEXT;

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

CREATE INDEX idx_plan_action_dependencies_depends_on
ON plan_action_dependencies (depends_on_action_id, action_id);
