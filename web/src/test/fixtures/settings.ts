/**
 * Summary: Defines deterministic Settings envelopes from committed generated API types.
 * Why: Makes Config recovery, review, preview, generation, and save tests drift with OpenAPI.
 */
import type {
  ApiEnvelopeArtistIdDraftData,
  ApiEnvelopePathPreview,
  ApiEnvelopeSettingsCandidateData,
  ApiEnvelopeSettingsData,
  ApiFailureEnvelope,
  AppConfigResource,
} from "../../api/generated";

export const settingsConfig = {
  add: { auto_apply: false, default_mode: "plan_first" },
  artist_ids: {
    entries: { "North Harbor": "NORTH" },
    fallback_id: "NOART",
    max_length: 8,
  },
  collision: {
    on_duplicate_hash: "skip",
    on_missing_metadata: "block",
    on_target_exists: "conflict",
  },
  metadata: {
    album_year_resolution: "latest",
    prefer_album_artist: true,
    require_album: false,
    require_artist: true,
    require_title: true,
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
  ui: {
    show_advanced_settings: true,
    theme: "oled",
  },
  version: 1,
} satisfies AppConfigResource;

export const settingsEnvelope = {
  data: {
    choices: {
      album_year_resolutions: ["latest", "oldest", "most_frequent"],
      command_modes: ["plan_first"],
      disc_number_conditions: ["always", "multiple_discs"],
      disc_number_styles: ["plain", "d_prefixed"],
      duplicate_hash_policies: ["skip"],
      missing_metadata_policies: ["block"],
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
    },
    config: settingsConfig,
    config_revision: "settings-revision-one",
    preview: {
      errors: [],
      path: "North Harbor/2026_Night Signals/1-1_First Light.flac",
    },
    validation: { errors: [], valid: true },
  },
  errors: [],
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
    path: "North Harbor/2026_Night Signals/1-1_First Light.flac",
  },
  errors: [],
} satisfies ApiEnvelopePathPreview;

export const artistIdDraftEnvelope = {
  data: {
    entries: [
      {
        artist_id: "GLASS",
        generation_artist: "Glass Harbor",
        overwritten: false,
        source_artist: "Glass Harbor",
      },
    ],
  },
  errors: [],
} satisfies ApiEnvelopeArtistIdDraftData;

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
