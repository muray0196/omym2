/**
 * Summary: Defines deterministic Settings envelopes from committed generated API types.
 * Why: Makes Config recovery, review, preview, and save tests drift with OpenAPI.
 */
import type {
  ApiEnvelopePathPreview,
  ApiEnvelopeSettingsCandidateData,
  ApiEnvelopeSettingsData,
  ApiFailureEnvelope,
  AppConfigResource,
} from "../../api/generated";

export const settingsConfig = {
  add: { auto_apply: false, default_mode: "plan_first" },
  artist_ids: {
    fallback_id: "NOART",
    max_length: 8,
  },
  collision: {
    on_duplicate_hash: "skip",
    on_missing_metadata: "block",
    on_target_exists: "conflict",
  },
  companions: {
    enabled: false,
  },
  hashing: {
    read_chunk_size_bytes: 1_048_576,
  },
  logging: {
    destination: null,
    level: "INFO",
    retention_files: 3,
    rotation_max_bytes: 5_242_880,
  },
  metadata: {
    album_year_resolution: "latest",
    prefer_album_artist: true,
    require_album: false,
    require_artist: true,
    require_title: true,
  },
  musicbrainz: {
    application_name: "OMYM2",
    cache_policy: "sticky_positive",
    contact: "https://github.com/muray0196/omym2",
    enabled: true,
    rate_limit_seconds: 1,
    retry_limit: 1,
    timeout_seconds: 5,
  },
  organize: { auto_apply: false, default_mode: "plan_first" },
  path_policy: {
    disc_number_condition: "always",
    disc_number_style: "plain",
    max_filename_length: 180,
    sanitize: true,
    template: "{album_artist}/{year}_{album}/{disc}-{track}_{title}",
    unknown_album: "Unknown Album",
    unknown_artist: "Unknown Artist",
  },
  paths: {
    incoming: "/music/incoming",
    library: "/music/library",
  },
  refresh: { auto_apply: false, default_mode: "plan_first" },
  unprocessed: {
    directory: "Unprocessed",
    enabled: false,
    result_preview_limit: 100,
  },
  version: 2,
} satisfies AppConfigResource;

export const settingsEnvelope = {
  data: {
    choices: {
      album_year_resolutions: ["latest", "oldest", "most_frequent"],
      command_modes: ["plan_first"],
      disc_number_conditions: ["always", "multiple_discs"],
      disc_number_styles: ["plain", "d_prefixed"],
      duplicate_hash_policies: ["skip"],
      logging_levels: ["CRITICAL", "DEBUG", "ERROR", "INFO", "WARNING"],
      missing_metadata_policies: ["block"],
      musicbrainz_cache_policies: ["sticky_positive"],
      path_placeholders: [
        "{album_artist}",
        "{album}",
        "{disc}",
        "{track}",
        "{title}",
        "{artist}",
        "{year}",
        "{artist_id}",
      ],
      target_exists_policies: ["conflict"],
      unprocessed_result_preview_limit_max: 500,
      unprocessed_result_preview_limit_min: 1,
    },
    config: settingsConfig,
    config_revision: "settings-revision-one",
    artist_name_mappings: {
      entries: [],
      revision: "artist-name-mappings-revision-one",
    },
    preview: {
      errors: [],
      path: "Aimer/2024_Example-Album/1-03_Example-Song.flac",
    },
    validation: { errors: [], valid: true },
  },
  errors: [],
} satisfies ApiEnvelopeSettingsData;

export const settingsEnvelopeWithMusicBrainzMapping = {
  ...settingsEnvelope,
  data: {
    ...settingsEnvelope.data,
    artist_name_mappings: {
      entries: [
        {
          english_name: "Sakamoto Ryuichi",
          selected_locale: "ja-Latn",
          selected_name_kind: "alias_sort_name",
          source: "musicbrainz",
          source_name: "坂本龍一",
        },
        {
          english_name: "Hataya Misuzu",
          selected_locale: null,
          selected_name_kind: "sort_name",
          source: "musicbrainz",
          source_name: "秦谷美鈴",
        },
      ],
      revision: "artist-name-mappings-revision-musicbrainz",
    },
  },
} satisfies ApiEnvelopeSettingsData;

export const reviewedSettingsEnvelope = {
  data: {
    changes: [
      {
        after: "/music/new-library",
        before: "/music/library",
        field: "paths.library",
      },
    ],
    config: {
      ...settingsConfig,
      paths: { ...settingsConfig.paths, library: "/music/new-library" },
    },
    config_revision: "settings-revision-one",
    preview: settingsEnvelope.data.preview,
    validation: { errors: [], valid: true },
  },
  errors: [],
} satisfies ApiEnvelopeSettingsCandidateData;

export const savedSettingsEnvelope = {
  data: {
    ...reviewedSettingsEnvelope.data,
    config_revision: "settings-revision-two",
  },
  errors: [],
} satisfies ApiEnvelopeSettingsCandidateData;

export const previewEnvelope = {
  data: {
    errors: [],
    path: "Aimer/2024_Example-Album/1-03_Example-Song.flac",
  },
  errors: [],
} satisfies ApiEnvelopePathPreview;

export const invalidPersistedSettingsEnvelope = {
  data: {
    ...settingsEnvelope.data,
    config_revision: "invalid-settings-revision",
    validation: {
      errors: [
        {
          code: "config_invalid",
          field: "body.config.path_policy.template",
          message: "The persisted path template is invalid.",
          retryable: false,
        },
      ],
      valid: false,
    },
  },
  errors: [],
} satisfies ApiEnvelopeSettingsData;

export const configChangedEnvelope = {
  data: null,
  errors: [
    {
      code: "config_changed",
      field: "body.expected_config_revision",
      message: "Configuration changed after this draft was opened.",
      retryable: true,
    },
  ],
} satisfies ApiFailureEnvelope;

export const csrfInvalidEnvelope = {
  data: null,
  errors: [
    {
      code: "csrf_invalid",
      field: "header.X-OMYM2-CSRF-Token",
      message: "The security token is invalid.",
      retryable: true,
    },
  ],
} satisfies ApiFailureEnvelope;
