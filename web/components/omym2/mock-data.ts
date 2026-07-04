import type {
  AppConfig,
  CheckResponse,
  CheckIssue,
  FileEvent,
  HistoryResponse,
  RunDetailResponse,
  RunSummary,
  SettingsPreviewResult,
  SettingsSaveResult,
  SettingsState,
  SettingsValidateResult,
  TracksResponse,
  TrackSummary,
  ArtistIdGenerationResult,
} from "./types"

export const LIBRARY_ID = "lib_9f3c1a7b-4e21-4d8a-9c10-2f6b0a5e7d44"

export const defaultConfig: AppConfig = {
  version: 1,
  paths: {
    library: "/music/library",
    incoming: "/music/incoming",
  },
  add: {
    default_mode: "plan_first",
    auto_apply: false,
  },
  organize: {
    default_mode: "plan_first",
    auto_apply: false,
    only_misplaced: true,
  },
  refresh: {
    default_mode: "plan_first",
    auto_apply: false,
  },
  path_policy: {
    template: "{album_artist}/{year}_{album}/{disc}-{track}_{title}",
    unknown_artist: "Unknown Artist",
    unknown_album: "Unknown Album",
    sanitize: true,
    max_filename_length: 180,
  },
  artist_ids: {
    max_length: 8,
    fallback_id: "NOART",
    entries: {
      Aimer: "AIMER",
      "John Smith": "JOHNSMTH",
    },
  },
  metadata: {
    prefer_album_artist: true,
    require_title: true,
    require_artist: true,
    require_album: false,
  },
  collision: {
    on_target_exists: "conflict",
    on_duplicate_hash: "skip",
    on_missing_metadata: "block",
  },
  ui: {
    theme: "system",
    show_advanced_settings: false,
  },
}

export const mockSettingsState: SettingsState = {
  config: defaultConfig,
  choices: {
    command_modes: ["plan_first"],
    duplicate_hash_policies: ["skip"],
    missing_metadata_policies: ["block"],
    target_exists_policies: ["conflict"],
    ui_themes: ["dark", "light", "oled", "system"],
  },
  validation: {
    valid: true,
    errors: [],
    config_hash: "mock-config-hash",
  },
  preview: {
    path: "Aimer/2024_Example-Album/1-03_Example-Song.flac",
    errors: [],
  },
  errors: [],
  csrf_token: "mock-csrf-token",
}

export function mockValidateSettings(config: AppConfig): SettingsValidateResult {
  return {
    valid: config.path_policy.template.trim() !== "",
    errors:
      config.path_policy.template.trim() === "" ? ["Path policy template must not be empty."] : [],
    changes: [],
    preview: mockPreviewSettings(),
  }
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
      config_hash: "mock-saved-config-hash",
    },
    preview: mockPreviewSettings(),
  }
}

export function mockPreviewSettings(): SettingsPreviewResult {
  return mockSettingsState.preview
}

export function mockGenerateArtistIds(artistNames: string[]): ArtistIdGenerationResult {
  return {
    generated: true,
    errors: [],
    entries: artistNames
      .map((name) => name.trim())
      .filter(Boolean)
      .map((name) => ({
        source_artist: name,
        generation_artist: name,
        artist_id: name === "John Smith" ? "JOHNSMTH" : "NOART",
        saved: true,
        overwritten: false,
      })),
  }
}

export const mockRuns: RunSummary[] = [
  {
    run_id: "run_3b9d0c2e-1f44-4a7c-8e21-5c0b9a1d2e33",
    plan_id: "plan_a12f8c4d-77e0-4b9a-91c2-0d4e6f8a1b22",
    library_id: LIBRARY_ID,
    status: "succeeded",
    started_at: "2026-06-29T09:14:02Z",
    completed_at: "2026-06-29T09:14:48Z",
    error_summary: null,
  },
  {
    run_id: "run_7c1a5e90-2d63-4f18-bb47-9a0e3c6d5f10",
    plan_id: "plan_d54b1a09-3c8e-4f2b-a6d7-1e9c0b4a7f55",
    library_id: LIBRARY_ID,
    status: "partial_failed",
    started_at: "2026-06-28T20:02:11Z",
    completed_at: "2026-06-28T20:03:37Z",
    error_summary: "2 of 41 actions failed (target exists, permission denied).",
  },
  {
    run_id: "run_1e8f4b22-9a07-4c5d-8b3e-6f2a1d0c9e88",
    plan_id: "plan_b98c2f10-5d4a-4e7b-8c61-3a0f9d2e1c44",
    library_id: LIBRARY_ID,
    status: "failed",
    started_at: "2026-06-27T11:48:55Z",
    completed_at: "2026-06-27T11:49:02Z",
    error_summary: "Library became unregistered before apply; aborted.",
  },
  {
    run_id: "run_5a2d9c71-6b40-4e83-a1f9-8c7b0e2d3a99",
    plan_id: "plan_f31e7a08-2b6c-4d90-8a5e-1c4f0b9d7e22",
    library_id: LIBRARY_ID,
    status: "running",
    started_at: "2026-06-29T10:31:20Z",
    completed_at: null,
    error_summary: null,
  },
  {
    run_id: "run_8f0b3d14-7c29-4a6e-9d52-0b1e8c4a2f77",
    plan_id: "plan_c72a9e15-4f31-4b8d-a09c-6d2e1f0a8b33",
    library_id: LIBRARY_ID,
    status: "succeeded",
    started_at: "2026-06-26T18:20:07Z",
    completed_at: "2026-06-26T18:20:51Z",
    error_summary: null,
  },
]

export const mockFileEvents: Record<string, FileEvent[]> = {
  "run_7c1a5e90-2d63-4f18-bb47-9a0e3c6d5f10": [
    {
      event_id: "evt_0a1b2c3d-0001",
      library_id: LIBRARY_ID,
      run_id: "run_7c1a5e90-2d63-4f18-bb47-9a0e3c6d5f10",
      plan_action_id: "pa_001",
      event_type: "create_dir",
      source_path: "",
      target_path: "Aimer/2024_Open α Door",
      status: "succeeded",
      started_at: "2026-06-28T20:02:11Z",
      completed_at: "2026-06-28T20:02:11Z",
      error_code: null,
      error_message: null,
      sequence_no: 1,
    },
    {
      event_id: "evt_0a1b2c3d-0002",
      library_id: LIBRARY_ID,
      run_id: "run_7c1a5e90-2d63-4f18-bb47-9a0e3c6d5f10",
      plan_action_id: "pa_002",
      event_type: "move",
      source_path: "/music/incoming/Example Song.flac",
      target_path: "Aimer/2024_Open α Door/1-03_Example Song.flac",
      status: "succeeded",
      started_at: "2026-06-28T20:02:12Z",
      completed_at: "2026-06-28T20:02:13Z",
      error_code: null,
      error_message: null,
      sequence_no: 2,
    },
    {
      event_id: "evt_0a1b2c3d-0003",
      library_id: LIBRARY_ID,
      run_id: "run_7c1a5e90-2d63-4f18-bb47-9a0e3c6d5f10",
      plan_action_id: "pa_017",
      event_type: "move",
      source_path: "/music/incoming/Deemo - Anima.mp3",
      target_path: "Various Artists/2013_Deemo/2-05_Anima.mp3",
      status: "failed",
      started_at: "2026-06-28T20:03:30Z",
      completed_at: "2026-06-28T20:03:30Z",
      error_code: "TARGET_EXISTS",
      error_message:
        "Target already exists and on_target_exists=skip is configured; action skipped as failure.",
      sequence_no: 17,
    },
    {
      event_id: "evt_0a1b2c3d-0004",
      library_id: LIBRARY_ID,
      run_id: "run_7c1a5e90-2d63-4f18-bb47-9a0e3c6d5f10",
      plan_action_id: "pa_034",
      event_type: "move",
      source_path: "/music/incoming/locked/Track 12.flac",
      target_path: "Sawano Hiroyuki/2019_R∃/1-12_Into the Sky.flac",
      status: "failed",
      started_at: "2026-06-28T20:03:36Z",
      completed_at: "2026-06-28T20:03:37Z",
      error_code: "PERMISSION_DENIED",
      error_message: "EACCES: permission denied on source file.",
      sequence_no: 34,
    },
  ],
  "run_3b9d0c2e-1f44-4a7c-8e21-5c0b9a1d2e33": [
    {
      event_id: "evt_1f2e3d4c-0001",
      library_id: LIBRARY_ID,
      run_id: "run_3b9d0c2e-1f44-4a7c-8e21-5c0b9a1d2e33",
      plan_action_id: "pa_101",
      event_type: "create_dir",
      source_path: "",
      target_path: "Aimer/2024_Example Album",
      status: "succeeded",
      started_at: "2026-06-29T09:14:02Z",
      completed_at: "2026-06-29T09:14:02Z",
      error_code: null,
      error_message: null,
      sequence_no: 1,
    },
    {
      event_id: "evt_1f2e3d4c-0002",
      library_id: LIBRARY_ID,
      run_id: "run_3b9d0c2e-1f44-4a7c-8e21-5c0b9a1d2e33",
      plan_action_id: "pa_102",
      event_type: "move",
      source_path: "/music/incoming/Example Song.flac",
      target_path: "Aimer/2024_Example Album/1-03_Example Song.flac",
      status: "succeeded",
      started_at: "2026-06-29T09:14:03Z",
      completed_at: "2026-06-29T09:14:04Z",
      error_code: null,
      error_message: null,
      sequence_no: 2,
    },
    {
      event_id: "evt_1f2e3d4c-0003",
      library_id: LIBRARY_ID,
      run_id: "run_3b9d0c2e-1f44-4a7c-8e21-5c0b9a1d2e33",
      plan_action_id: "pa_103",
      event_type: "verify",
      source_path: "",
      target_path: "Aimer/2024_Example Album/1-03_Example Song.flac",
      status: "succeeded",
      started_at: "2026-06-29T09:14:47Z",
      completed_at: "2026-06-29T09:14:48Z",
      error_code: null,
      error_message: null,
      sequence_no: 3,
    },
  ],
  // A run with no recorded file events (empty state).
  "run_1e8f4b22-9a07-4c5d-8b3e-6f2a1d0c9e88": [],
}

export const mockHistoryResponse: HistoryResponse = {
  runs: mockRuns,
  errors: [],
}

export function mockRunDetailResponse(runId: string): RunDetailResponse {
  const run = mockRuns.find((candidate) => candidate.run_id === runId)
  if (!run) {
    return { detail: null, errors: ["Run was not found."] }
  }
  return {
    detail: {
      run,
      file_events: mockFileEvents[runId] ?? [],
    },
    errors: [],
  }
}

// Static previews use this fixture when the FastAPI backend is unavailable.
export const mockIssues: CheckIssue[] = [
  {
    issue_id: "iss_0001",
    issue_type: "db_file_missing",
    severity: "error",
    library_id: LIBRARY_ID,
    path: "Sawano Hiroyuki/2019_R∃/1-12_Into the Sky.flac",
    track_id: "trk_4a1b2c3d-0009",
    plan_id: null,
    detail: "Tracked file is recorded in the DB but no longer exists on disk.",
  },
  {
    issue_id: "iss_0002",
    issue_type: "unmanaged_file_exists",
    severity: "warning",
    library_id: LIBRARY_ID,
    path: "Misc/_unsorted/random-download.mp3",
    track_id: null,
    plan_id: null,
    detail: "File exists under the library root but is not tracked in the DB.",
  },
  {
    issue_id: "iss_0003",
    issue_type: "current_path_differs_from_canonical_path",
    severity: "warning",
    library_id: LIBRARY_ID,
    path: "Aimer/Open a Door/03 Example Song.flac",
    track_id: "trk_4a1b2c3d-0002",
    plan_id: null,
    detail: "Current path does not match the canonical path produced by the active path policy.",
  },
  {
    issue_id: "iss_0004",
    issue_type: "content_hash_changed",
    severity: "error",
    library_id: LIBRARY_ID,
    path: "Kenshi Yonezu/2018_BOOTLEG/1-04_Lemon.flac",
    track_id: "trk_4a1b2c3d-0005",
    plan_id: null,
    detail: "Content hash differs from the recorded value; file may have been re-encoded.",
  },
  {
    issue_id: "iss_0005",
    issue_type: "metadata_hash_changed",
    severity: "info",
    library_id: LIBRARY_ID,
    path: "Kenshi Yonezu/2018_BOOTLEG/1-04_Lemon.flac",
    track_id: "trk_4a1b2c3d-0005",
    plan_id: null,
    detail: "Embedded metadata changed since last scan; canonical path may need refresh.",
  },
  {
    issue_id: "iss_0006",
    issue_type: "duplicate_candidate",
    severity: "warning",
    library_id: LIBRARY_ID,
    path: "Various Artists/2013_Deemo/2-05_Anima.mp3",
    track_id: "trk_4a1b2c3d-0011",
    plan_id: null,
    detail: "Another tracked file shares the same content hash.",
  },
  {
    issue_id: "iss_0007",
    issue_type: "pending_file_event_exists",
    severity: "warning",
    library_id: LIBRARY_ID,
    path: "Aimer/2024_Open α Door/1-03_Example Song.flac",
    track_id: null,
    plan_id: "plan_d54b1a09-3c8e-4f2b-a6d7-1e9c0b4a7f55",
    detail: "A file event from an interrupted run is still pending; recovery recommended.",
  },
  {
    issue_id: "iss_0008",
    issue_type: "library_stale",
    severity: "info",
    library_id: LIBRARY_ID,
    path: "/music/library",
    track_id: null,
    plan_id: null,
    detail: "Library has not been refreshed in over 14 days.",
  },
]

export const mockCheckResponse: CheckResponse = {
  issues: mockIssues,
  errors: [],
}

export const mockTracks: TrackSummary[] = [
  {
    track_id: "trk_4a1b2c3d-0001",
    library_id: LIBRARY_ID,
    current_path: "Aimer/2024_Example Album/1-03_Example Song.flac",
    canonical_path: "Aimer/2024_Example Album/1-03_Example Song.flac",
    content_hash: "blake3:9af1c0b27e3d4a5f6c8b0e1d2a3f4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b",
    metadata_hash: "blake3:1122334455667788990011223344556677889900aabbccddeeff0011223344",
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
      disc_total: 1,
    },
    status: "active",
    first_seen_at: "2026-06-29T09:14:04Z",
    last_seen_at: "2026-06-29T10:00:00Z",
    updated_at: "2026-06-29T09:14:48Z",
  },
  {
    track_id: "trk_4a1b2c3d-0002",
    library_id: LIBRARY_ID,
    current_path: "Aimer/Open a Door/03 Example Song.flac",
    canonical_path: "Aimer/2024_Open α Door/1-03_Open the Door.flac",
    content_hash: "blake3:abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
    metadata_hash: "blake3:00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff",
    metadata: {
      title: "Open the Door",
      artist: "Aimer",
      album: "Open α Door",
      album_artist: "Aimer",
      genre: "J-Pop",
      year: 2024,
      track_number: 3,
      track_total: 14,
      disc_number: 1,
      disc_total: 1,
    },
    status: "active",
    first_seen_at: "2026-06-20T12:00:00Z",
    last_seen_at: "2026-06-29T08:00:00Z",
    updated_at: "2026-06-25T14:22:10Z",
  },
  {
    track_id: "trk_4a1b2c3d-0005",
    library_id: LIBRARY_ID,
    current_path: "Kenshi Yonezu/2018_BOOTLEG/1-04_Lemon.flac",
    canonical_path: "Kenshi Yonezu/2018_BOOTLEG/1-04_Lemon.flac",
    content_hash: "blake3:dead00beef11cafe22f00d33ba5e44dead00beef11cafe22f00d33ba5e44dead",
    metadata_hash: "blake3:cafe11dead22beef33f00d44ba5e55cafe11dead22beef33f00d44ba5e55cafe",
    metadata: {
      title: "Lemon",
      artist: "Kenshi Yonezu",
      album: "BOOTLEG",
      album_artist: "Kenshi Yonezu",
      genre: "J-Pop",
      year: 2018,
      track_number: 4,
      track_total: 15,
      disc_number: 1,
      disc_total: 1,
    },
    status: "active",
    first_seen_at: "2026-05-01T10:00:00Z",
    last_seen_at: "2026-06-29T08:00:00Z",
    updated_at: "2026-06-28T19:00:00Z",
  },
  {
    track_id: "trk_4a1b2c3d-0009",
    library_id: LIBRARY_ID,
    current_path: "Sawano Hiroyuki/2019_R∃/1-12_Into the Sky.flac",
    canonical_path: "Sawano Hiroyuki/2019_R∃/1-12_Into the Sky.flac",
    content_hash: "blake3:0011223344556677889900112233445566778899001122334455667788990011",
    metadata_hash: "blake3:9988776655443322110099887766554433221100998877665544332211009988",
    metadata: {
      title: "Into the Sky",
      artist: "SawanoHiroyuki[nZk]",
      album: "R∃/MEMBER",
      album_artist: "Sawano Hiroyuki",
      genre: "Soundtrack",
      year: 2019,
      track_number: 12,
      track_total: 12,
      disc_number: 1,
      disc_total: 1,
    },
    status: "removed",
    first_seen_at: "2026-04-12T09:00:00Z",
    last_seen_at: "2026-06-27T11:48:00Z",
    updated_at: "2026-06-27T11:49:02Z",
  },
  {
    track_id: "trk_4a1b2c3d-0011",
    library_id: LIBRARY_ID,
    current_path: "Various Artists/2013_Deemo/2-05_Anima.mp3",
    canonical_path: "Various Artists/2013_Deemo/2-05_Anima.mp3",
    content_hash: "blake3:5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a",
    metadata_hash: "blake3:3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c3c",
    metadata: {
      title: "Anima",
      artist: "M2U",
      album: "Deemo",
      album_artist: "Various Artists",
      genre: "Game",
      year: 2013,
      track_number: 5,
      track_total: 20,
      disc_number: 2,
      disc_total: 2,
    },
    status: "active",
    first_seen_at: "2026-06-10T15:30:00Z",
    last_seen_at: "2026-06-29T08:00:00Z",
    updated_at: "2026-06-10T15:31:00Z",
  },
]

export const mockTracksResponse: TracksResponse = {
  tracks: mockTracks,
  errors: [],
}
