CREATE TABLE accepted_artist_names (
    source_key TEXT NOT NULL PRIMARY KEY CHECK (trim(source_key) <> ''),
    source_name TEXT NOT NULL CHECK (trim(source_name) <> ''),
    resolved_name TEXT NOT NULL CHECK (trim(resolved_name) <> ''),
    provider TEXT NOT NULL CHECK (provider IN ('musicbrainz')),
    provider_artist_id TEXT NOT NULL CHECK (
        trim(provider_artist_id) <> '' AND length(provider_artist_id) = 36
    ),
    selected_name_kind TEXT NOT NULL CHECK (selected_name_kind IN ('alias', 'name')),
    selected_locale TEXT,
    accepted_at TEXT NOT NULL,
    CHECK (
        selected_locale IS NULL OR
        (selected_name_kind = 'alias' AND trim(selected_locale) <> '')
    )
);
