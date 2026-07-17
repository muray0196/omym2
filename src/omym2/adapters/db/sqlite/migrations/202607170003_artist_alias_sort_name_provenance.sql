-- Summary: Distinguishes MusicBrainz alias names from alias sort names.
-- Why: Lets users review the exact MusicBrainz field selected for an artist mapping.

CREATE TABLE accepted_artist_names_alias_sort_name (
    source_key TEXT NOT NULL PRIMARY KEY CHECK (trim(source_key) <> ''),
    source_name TEXT NOT NULL CHECK (trim(source_name) <> ''),
    resolved_name TEXT NOT NULL CHECK (trim(resolved_name) <> ''),
    provider TEXT NOT NULL CHECK (provider IN ('musicbrainz', 'user')),
    provider_artist_id TEXT,
    selected_name_kind TEXT CHECK (
        selected_name_kind IN ('alias', 'alias_sort_name', 'name', 'sort_name')
    ),
    selected_locale TEXT,
    accepted_at TEXT NOT NULL,
    CHECK (
        (
            provider = 'musicbrainz'
            AND provider_artist_id IS NOT NULL
            AND trim(provider_artist_id) <> ''
            AND length(provider_artist_id) = 36
            AND selected_name_kind IS NOT NULL
        )
        OR (
            provider = 'user'
            AND provider_artist_id IS NULL
            AND selected_name_kind IS NULL
            AND selected_locale IS NULL
        )
    ),
    CHECK (
        selected_locale IS NULL
        OR (
            selected_name_kind IN ('alias', 'alias_sort_name')
            AND trim(selected_locale) <> ''
        )
    )
);

INSERT INTO accepted_artist_names_alias_sort_name (
    source_key,
    source_name,
    resolved_name,
    provider,
    provider_artist_id,
    selected_name_kind,
    selected_locale,
    accepted_at
)
SELECT
    source_key,
    source_name,
    resolved_name,
    provider,
    provider_artist_id,
    selected_name_kind,
    selected_locale,
    accepted_at
FROM accepted_artist_names;

DROP TABLE accepted_artist_names;

ALTER TABLE accepted_artist_names_alias_sort_name RENAME TO accepted_artist_names;
