ALTER TABLE plan_actions
ADD COLUMN artist_name_diagnostics_json TEXT
CHECK (
    artist_name_diagnostics_json IS NULL
    OR (
        json_valid(artist_name_diagnostics_json)
        AND json_type(artist_name_diagnostics_json) = 'object'
    )
);
