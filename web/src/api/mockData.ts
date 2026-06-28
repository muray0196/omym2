/*
Summary: Provides deterministic React API fixture payloads.
Why: Lets design previews render without the local OMYM2 backend.
*/

import type {
  AppConfig,
  CheckResponse,
  HistoryResponse,
  RunDetail,
  RunDetailResponse,
  SettingsSaveResult,
  SettingsState,
  SettingsValidateResult,
  TracksResponse
} from "../types";

const MOCK_TIME = "2026-01-01T00:00:00+00:00";
const MOCK_LIBRARY_ID = "018f6a4f-3c2d-7b8a-9abc-def012345678";
const MOCK_TRACK_ID = "018f6a4f-3c2d-7b8a-9abc-def012345679";
const MOCK_PLAN_ID = "018f6a4f-3c2d-7b8a-9abc-def01234567a";
const MOCK_ACTION_ID = "018f6a4f-3c2d-7b8a-9abc-def01234567b";
const MOCK_RUN_ID = "018f6a4f-3c2d-7b8a-9abc-def01234567d";
const MOCK_EVENT_ID = "018f6a4f-3c2d-7b8a-9abc-def01234567e";
const MOCK_TRACK_PATH = "Aimer/2024_Example Album/1-03_Example Song.flac";

const mockConfig: AppConfig = {
  version: 1,
  paths: {
    library: "/music/library",
    incoming: "/music/incoming"
  },
  add: {
    default_mode: "plan_first",
    auto_apply: false
  },
  organize: {
    default_mode: "plan_first",
    auto_apply: false,
    only_misplaced: true
  },
  refresh: {
    default_mode: "plan_first",
    auto_apply: false
  },
  path_policy: {
    template: "{album_artist}/{year}_{album}/{disc}-{track}_{title}",
    unknown_artist: "Unknown Artist",
    unknown_album: "Unknown Album",
    sanitize: true,
    max_filename_length: 160
  },
  metadata: {
    prefer_album_artist: true,
    require_title: true,
    require_artist: true,
    require_album: false
  },
  collision: {
    on_target_exists: "fail",
    on_duplicate_hash: "skip",
    on_missing_metadata: "fail"
  },
  ui: {
    theme: "system",
    show_advanced_settings: false
  }
};

export const mockSettingsState: SettingsState = {
  config: mockConfig,
  choices: {
    command_modes: ["plan_first"],
    duplicate_hash_policies: ["skip", "fail"],
    missing_metadata_policies: ["fail", "skip"],
    target_exists_policies: ["fail", "skip"],
    ui_themes: ["system", "light", "dark"]
  },
  validation: {
    valid: true,
    errors: [],
    config_hash: "mock-config-hash"
  },
  preview: {
    path: MOCK_TRACK_PATH,
    errors: []
  },
  errors: [],
  csrf_token: "mock-csrf-token"
};

export const mockHistoryResponse: HistoryResponse = {
  runs: [
    {
      run_id: MOCK_RUN_ID,
      plan_id: MOCK_PLAN_ID,
      library_id: MOCK_LIBRARY_ID,
      status: "succeeded",
      started_at: MOCK_TIME,
      completed_at: MOCK_TIME,
      error_summary: null
    }
  ],
  errors: []
};

const mockRunDetail: RunDetail = {
  run: mockHistoryResponse.runs[0],
  file_events: [
    {
      event_id: MOCK_EVENT_ID,
      library_id: MOCK_LIBRARY_ID,
      run_id: MOCK_RUN_ID,
      plan_action_id: MOCK_ACTION_ID,
      event_type: "move_file",
      source_path: "/music/incoming/Example Song.flac",
      target_path: MOCK_TRACK_PATH,
      status: "succeeded",
      started_at: MOCK_TIME,
      completed_at: MOCK_TIME,
      error_code: null,
      error_message: null,
      sequence_no: 1
    }
  ]
};

export const mockCheckResponse: CheckResponse = {
  issues: [],
  errors: []
};

export const mockTracksResponse: TracksResponse = {
  tracks: [
    {
      track_id: MOCK_TRACK_ID,
      library_id: MOCK_LIBRARY_ID,
      current_path: MOCK_TRACK_PATH,
      canonical_path: MOCK_TRACK_PATH,
      content_hash: "mock-content-hash",
      metadata_hash: "mock-metadata-hash",
      metadata: {
        title: "Example Song",
        artist: "Aimer",
        album: "Example Album",
        album_artist: "Aimer",
        genre: "J-Pop",
        year: 2024,
        track_number: 3,
        track_total: 12,
        disc_number: 1,
        disc_total: 1
      },
      status: "active",
      first_seen_at: MOCK_TIME,
      last_seen_at: MOCK_TIME,
      updated_at: MOCK_TIME
    }
  ],
  errors: []
};

export function mockRunDetailResponse(runId: string): RunDetailResponse {
  if (runId !== MOCK_RUN_ID) {
    return { detail: null, errors: ["Run was not found."] };
  }
  return { detail: mockRunDetail, errors: [] };
}

export function mockValidateSettings(config: AppConfig): SettingsValidateResult {
  return {
    valid: true,
    errors: [],
    changes: [],
    preview: {
      path: config.path_policy.template === "" ? null : MOCK_TRACK_PATH,
      errors: []
    }
  };
}

export function mockSaveSettings(config: AppConfig): SettingsSaveResult {
  return {
    saved: true,
    errors: [],
    changes: [],
    config,
    validation: {
      valid: true,
      errors: [],
      config_hash: "mock-saved-config-hash"
    },
    preview: {
      path: config.path_policy.template === "" ? null : MOCK_TRACK_PATH,
      errors: []
    }
  };
}
