/*
Summary: Provides static mock payloads for the OMYM2 console.
Why: Keeps exported frontend previews usable when the local API is unavailable.
*/

import type {
  AppConfig,
  CheckFacetsResponse,
  CheckGroupBy,
  CheckGroupCount,
  CheckGroupsResponse,
  CheckIssue,
  CheckIssueType,
  CheckPageResponse,
  CheckRunResponse,
  FacetsResponse,
  FacetValue,
  FileEvent,
  FileEventStatus,
  GroupCount,
  GroupsResponse,
  PagedResponse,
  PlanAction,
  PlanActionReason,
  PlanActionStatus,
  PlanActionType,
  PlanCreateResult,
  PlanDetailResponse,
  PlanFacetsResponse,
  PlanGroupBy,
  PlanGroupCount,
  PlanGroupsResponse,
  PlanStatus,
  PlanSummary,
  PlanType,
  RunDetailResponse,
  RunStatus,
  RunSummary,
  SettingsPreviewResult,
  SettingsSaveResult,
  SettingsState,
  SettingsValidateResult,
  TrackGroupBy,
  TrackStatus,
  TrackSummary,
  ArtistIdGenerationResult,
} from "./types"
import { severityForIssue } from "./lib"
import {
  assertTrackGroupFilter,
  assertTrackGroupParentKey,
  compareSqliteBinaryText,
  hasTrackGroupMetadataText,
} from "./track-browsing"

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
    disc_number_style: "plain",
    disc_number_condition: "always",
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
    album_year_resolution: "latest",
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
    album_year_resolution_methods: ["latest", "most_frequent", "oldest"],
    disc_number_styles: ["d_prefixed", "plain"],
    disc_number_conditions: ["always", "multiple_discs"],
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

export const mockPlans: PlanSummary[] = [
  {
    plan_id: "plan_d54b1a09-3c8e-4f2b-a6d7-1e9c0b4a7f55",
    library_id: LIBRARY_ID,
    plan_type: "add",
    status: "ready",
    created_at: "2026-06-29T10:12:03Z",
    // Three actions are blocked (target_exists, missing_required_metadata
    // with a null target, duplicate_hash onto an already-used target) so this
    // default "ready" Plan exercises every risk-summary state on its detail
    // screen: blocked count, unknown-metadata count, and a target collision.
    summary: { action_count: "6", move_actions: "6", blocked_actions: "3" },
  },
  {
    plan_id: "plan_b98c2f10-5d4a-4e7b-8c61-3a0f9d2e1c44",
    library_id: LIBRARY_ID,
    plan_type: "refresh",
    status: "ready",
    created_at: "2026-06-28T18:42:16Z",
    summary: { action_count: "2", move_actions: "1", metadata_actions: "1", blocked_actions: "0" },
  },
  {
    plan_id: "plan_f31e7a08-2b6c-4d90-8a5e-1c4f0b9d7e22",
    library_id: LIBRARY_ID,
    plan_type: "organize",
    status: "applied",
    created_at: "2026-06-27T08:31:11Z",
    // Matches the single applied action row below; its apply Run is
    // run_9c4f7a35 (succeeded), exercising the "View run" cross-link
    // for the applied status.
    summary: { action_count: "1", applied_actions: "1", blocked_actions: "0" },
  },
  {
    plan_id: "plan_9e2c6b41-8a37-4d19-b5f0-2c7e4a9d1f66",
    library_id: LIBRARY_ID,
    plan_type: "organize",
    status: "partial_failed",
    // Created shortly before its apply Run (run_7c1a5e90, started
    // 2026-06-28T20:02:11Z) — a Run cannot precede its Plan.
    created_at: "2026-06-28T19:40:05Z",
    // Matches the action rows below: 3 applied + 1 failed + 2 blocked.
    summary: {
      action_count: "6",
      applied_actions: "3",
      failed_actions: "1",
      blocked_actions: "2",
    },
  },
  {
    plan_id: "plan_2f8a4d17-6c93-4b52-9e0d-8b1f3c6a7e29",
    library_id: LIBRARY_ID,
    plan_type: "add",
    status: "failed",
    created_at: "2026-06-26T14:05:31Z",
    // Matches the action rows below: apply aborted, all 4 moves failed.
    summary: { action_count: "4", move_actions: "4", failed_actions: "4", blocked_actions: "0" },
  },
  {
    plan_id: "plan_6b3d9f52-1e74-4a86-9c2f-5d0a8e1b3c47",
    library_id: LIBRARY_ID,
    plan_type: "refresh",
    status: "cancelled",
    created_at: "2026-06-25T09:47:12Z",
    summary: { action_count: "3", move_actions: "2", metadata_actions: "1", blocked_actions: "0" },
  },
  {
    plan_id: "plan_a12f8c4d-77e0-4b9a-91c2-0d4e6f8a1b22",
    library_id: LIBRARY_ID,
    plan_type: "add",
    status: "applied",
    created_at: "2026-06-29T09:12:00Z",
    summary: { action_count: "3", move_actions: "3", applied_actions: "3", blocked_actions: "0" },
  },
  {
    plan_id: "plan_7f3e9c21-4a68-4d91-b0f3-8d6e2c9a1b57",
    library_id: LIBRARY_ID,
    plan_type: "organize",
    status: "applying",
    created_at: "2026-06-29T10:30:00Z",
    summary: { action_count: "1", move_actions: "1", blocked_actions: "0" },
  },
  {
    plan_id: "plan_c72a9e15-4f31-4b8d-a09c-6d2e1f0a8b33",
    library_id: LIBRARY_ID,
    plan_type: "organize",
    status: "applied",
    created_at: "2026-06-26T18:19:00Z",
    summary: { action_count: "0", blocked_actions: "0" },
  },
]

const mockPlanActions: Record<string, PlanAction[]> = {
  "plan_d54b1a09-3c8e-4f2b-a6d7-1e9c0b4a7f55": [
    {
      action_id: "act_001",
      plan_id: "plan_d54b1a09-3c8e-4f2b-a6d7-1e9c0b4a7f55",
      library_id: LIBRARY_ID,
      track_id: null,
      action_type: "move",
      source_path: "/music/incoming/Aimer - Spark Again.flac",
      target_path: "Aimer/2020_Walpurgis/1-01_Spark-Again.flac",
      content_hash_at_plan: "sha256:mock-content-001",
      metadata_hash_at_plan: "sha256:mock-metadata-001",
      status: "planned",
      reason: null,
      sort_order: 1,
    },
    {
      action_id: "act_002",
      plan_id: "plan_d54b1a09-3c8e-4f2b-a6d7-1e9c0b4a7f55",
      library_id: LIBRARY_ID,
      track_id: null,
      action_type: "move",
      source_path: "/music/incoming/Aimer - Deep down.flac",
      target_path: "Aimer/2022_Deep-Down/1-02_Deep-down.flac",
      content_hash_at_plan: "sha256:mock-content-002",
      metadata_hash_at_plan: "sha256:mock-metadata-002",
      status: "planned",
      reason: null,
      sort_order: 2,
    },
    {
      action_id: "act_003",
      plan_id: "plan_d54b1a09-3c8e-4f2b-a6d7-1e9c0b4a7f55",
      library_id: LIBRARY_ID,
      track_id: null,
      action_type: "move",
      source_path: "/music/incoming/Aimer - Resonantia.flac",
      target_path: "Aimer/2023_Resonantia/1-03_Resonantia.flac",
      content_hash_at_plan: "sha256:mock-content-003",
      metadata_hash_at_plan: "sha256:mock-metadata-003",
      status: "planned",
      reason: null,
      sort_order: 3,
    },
    {
      action_id: "act_004",
      plan_id: "plan_d54b1a09-3c8e-4f2b-a6d7-1e9c0b4a7f55",
      library_id: LIBRARY_ID,
      track_id: null,
      action_type: "move",
      source_path: "/music/incoming/Aimer - Insane Dream.flac",
      target_path: "Aimer/2021_Insane-Dream/1-04_Insane-Dream.flac",
      content_hash_at_plan: "sha256:mock-content-004",
      metadata_hash_at_plan: "sha256:mock-metadata-004",
      status: "blocked",
      reason: "target_exists",
      sort_order: 4,
    },
    {
      // Blocked with a null target: required metadata is missing, so no
      // canonical path could be generated. Exercises the "(unknown)"
      // artist_album group, the unknown-metadata risk metric, and a second
      // file extension (mp3) in the extension grouping.
      action_id: "act_005",
      plan_id: "plan_d54b1a09-3c8e-4f2b-a6d7-1e9c0b4a7f55",
      library_id: LIBRARY_ID,
      track_id: null,
      action_type: "move",
      source_path: "/music/incoming/Unknown Artist - Track 7.mp3",
      target_path: null,
      content_hash_at_plan: "sha256:mock-content-005",
      metadata_hash_at_plan: "sha256:mock-metadata-005",
      status: "blocked",
      reason: "missing_required_metadata",
      sort_order: 5,
    },
    {
      // Duplicate of act_001's content resolving to the same target path.
      // Exercises the target-collision risk metric on a "ready" Plan.
      action_id: "act_006",
      plan_id: "plan_d54b1a09-3c8e-4f2b-a6d7-1e9c0b4a7f55",
      library_id: LIBRARY_ID,
      track_id: null,
      action_type: "move",
      source_path: "/music/incoming/dupes/Aimer - Spark Again (copy).flac",
      target_path: "Aimer/2020_Walpurgis/1-01_Spark-Again.flac",
      content_hash_at_plan: "sha256:mock-content-001",
      metadata_hash_at_plan: "sha256:mock-metadata-006",
      status: "blocked",
      reason: "duplicate_hash",
      sort_order: 6,
    },
  ],
  "plan_b98c2f10-5d4a-4e7b-8c61-3a0f9d2e1c44": [
    {
      action_id: "act_101",
      plan_id: "plan_b98c2f10-5d4a-4e7b-8c61-3a0f9d2e1c44",
      library_id: LIBRARY_ID,
      track_id: "trk_refresh_001",
      action_type: "move",
      source_path: "Aimer/Open-a-Door/1-03_Old-Title.flac",
      target_path: "Aimer/2023_Open-a-Door/1-03_New-Title.flac",
      content_hash_at_plan: "sha256:mock-content-101",
      metadata_hash_at_plan: "sha256:mock-metadata-101",
      status: "planned",
      reason: null,
      sort_order: 1,
    },
    {
      action_id: "act_102",
      plan_id: "plan_b98c2f10-5d4a-4e7b-8c61-3a0f9d2e1c44",
      library_id: LIBRARY_ID,
      track_id: "trk_refresh_002",
      action_type: "refresh_metadata",
      source_path: "Aimer/2023_Open-a-Door/1-04_Unchanged.flac",
      target_path: "Aimer/2023_Open-a-Door/1-04_Unchanged.flac",
      content_hash_at_plan: "sha256:mock-content-102",
      metadata_hash_at_plan: "sha256:mock-metadata-102",
      status: "planned",
      reason: null,
      sort_order: 2,
    },
  ],
  "plan_f31e7a08-2b6c-4d90-8a5e-1c4f0b9d7e22": [
    {
      action_id: "act_201",
      plan_id: "plan_f31e7a08-2b6c-4d90-8a5e-1c4f0b9d7e22",
      library_id: LIBRARY_ID,
      track_id: "trk_organize_001",
      action_type: "move",
      source_path: "Loose/Track.flac",
      target_path: "Aimer/2019_Sun-Dance/1-01_Track.flac",
      content_hash_at_plan: "sha256:mock-content-201",
      metadata_hash_at_plan: "sha256:mock-metadata-201",
      status: "applied",
      reason: null,
      sort_order: 1,
    },
  ],
  // partial_failed: 3 applied + 1 failed + 2 blocked, matching its summary.
  "plan_9e2c6b41-8a37-4d19-b5f0-2c7e4a9d1f66": [
    {
      action_id: "act_301",
      plan_id: "plan_9e2c6b41-8a37-4d19-b5f0-2c7e4a9d1f66",
      library_id: LIBRARY_ID,
      track_id: "trk_organize_101",
      action_type: "move",
      source_path: "Loose/Aimer - Torches.flac",
      target_path: "Aimer/2019_Torches/1-01_Torches.flac",
      content_hash_at_plan: "sha256:mock-content-301",
      metadata_hash_at_plan: "sha256:mock-metadata-301",
      status: "applied",
      reason: null,
      sort_order: 1,
    },
    {
      action_id: "act_302",
      plan_id: "plan_9e2c6b41-8a37-4d19-b5f0-2c7e4a9d1f66",
      library_id: LIBRARY_ID,
      track_id: "trk_organize_102",
      action_type: "move",
      source_path: "Loose/Aimer - Ref-rain.flac",
      target_path: "Aimer/2018_Ref-rain/1-01_Ref-rain.flac",
      content_hash_at_plan: "sha256:mock-content-302",
      metadata_hash_at_plan: "sha256:mock-metadata-302",
      status: "applied",
      reason: null,
      sort_order: 2,
    },
    {
      action_id: "act_303",
      plan_id: "plan_9e2c6b41-8a37-4d19-b5f0-2c7e4a9d1f66",
      library_id: LIBRARY_ID,
      track_id: "trk_organize_103",
      action_type: "move",
      source_path: "Loose/Aimer - Black Bird.flac",
      target_path: "Aimer/2018_Black-Bird/1-01_Black-Bird.flac",
      content_hash_at_plan: "sha256:mock-content-303",
      metadata_hash_at_plan: "sha256:mock-metadata-303",
      status: "applied",
      reason: null,
      sort_order: 3,
    },
    {
      // Apply-time precondition failure (source changed after planning).
      action_id: "act_304",
      plan_id: "plan_9e2c6b41-8a37-4d19-b5f0-2c7e4a9d1f66",
      library_id: LIBRARY_ID,
      track_id: "trk_organize_104",
      action_type: "move",
      source_path: "Loose/Aimer - Zankyosanka.flac",
      target_path: "Aimer/2022_Zankyosanka/1-01_Zankyosanka.flac",
      content_hash_at_plan: "sha256:mock-content-304",
      metadata_hash_at_plan: "sha256:mock-metadata-304",
      status: "failed",
      reason: "source_changed",
      sort_order: 4,
    },
    {
      action_id: "act_305",
      plan_id: "plan_9e2c6b41-8a37-4d19-b5f0-2c7e4a9d1f66",
      library_id: LIBRARY_ID,
      track_id: "trk_organize_105",
      action_type: "move",
      source_path: "Loose/Unknown - Untitled.flac",
      target_path: null,
      content_hash_at_plan: "sha256:mock-content-305",
      metadata_hash_at_plan: "sha256:mock-metadata-305",
      status: "blocked",
      reason: "missing_required_metadata",
      sort_order: 5,
    },
    {
      action_id: "act_306",
      plan_id: "plan_9e2c6b41-8a37-4d19-b5f0-2c7e4a9d1f66",
      library_id: LIBRARY_ID,
      track_id: "trk_organize_106",
      action_type: "move",
      source_path: "Loose/Aimer - Torches (copy).flac",
      target_path: "Aimer/2019_Torches/1-01_Torches.flac",
      content_hash_at_plan: "sha256:mock-content-301",
      metadata_hash_at_plan: "sha256:mock-metadata-306",
      status: "blocked",
      reason: "duplicate_hash",
      sort_order: 6,
    },
  ],
  // failed: the run aborted before any mutation, all 4 moves failed.
  "plan_2f8a4d17-6c93-4b52-9e0d-8b1f3c6a7e29": [
    {
      action_id: "act_401",
      plan_id: "plan_2f8a4d17-6c93-4b52-9e0d-8b1f3c6a7e29",
      library_id: LIBRARY_ID,
      track_id: null,
      action_type: "move",
      source_path: "/music/incoming/Yorushika - Haru Dorobou.flac",
      target_path: "Yorushika/2020_Haru-Dorobou/1-01_Haru-Dorobou.flac",
      content_hash_at_plan: "sha256:mock-content-401",
      metadata_hash_at_plan: "sha256:mock-metadata-401",
      status: "failed",
      reason: null,
      sort_order: 1,
    },
    {
      action_id: "act_402",
      plan_id: "plan_2f8a4d17-6c93-4b52-9e0d-8b1f3c6a7e29",
      library_id: LIBRARY_ID,
      track_id: null,
      action_type: "move",
      source_path: "/music/incoming/Yorushika - Itte.flac",
      target_path: "Yorushika/2017_Natsukusa/1-01_Itte.flac",
      content_hash_at_plan: "sha256:mock-content-402",
      metadata_hash_at_plan: "sha256:mock-metadata-402",
      status: "failed",
      reason: null,
      sort_order: 2,
    },
    {
      action_id: "act_403",
      plan_id: "plan_2f8a4d17-6c93-4b52-9e0d-8b1f3c6a7e29",
      library_id: LIBRARY_ID,
      track_id: null,
      action_type: "move",
      source_path: "/music/incoming/Yorushika - Tada Kimi ni Hare.flac",
      target_path: "Yorushika/2018_Makeinu/1-01_Tada-Kimi-ni-Hare.flac",
      content_hash_at_plan: "sha256:mock-content-403",
      metadata_hash_at_plan: "sha256:mock-metadata-403",
      status: "failed",
      reason: null,
      sort_order: 3,
    },
    {
      action_id: "act_404",
      plan_id: "plan_2f8a4d17-6c93-4b52-9e0d-8b1f3c6a7e29",
      library_id: LIBRARY_ID,
      track_id: null,
      action_type: "move",
      source_path: "/music/incoming/Yorushika - Say It.flac",
      target_path: "Yorushika/2019_Elma/1-02_Say-It.flac",
      content_hash_at_plan: "sha256:mock-content-404",
      metadata_hash_at_plan: "sha256:mock-metadata-404",
      status: "failed",
      reason: null,
      sort_order: 4,
    },
  ],
  // cancelled: never applied, actions remain planned (2 moves + 1 metadata).
  "plan_6b3d9f52-1e74-4a86-9c2f-5d0a8e1b3c47": [
    {
      action_id: "act_501",
      plan_id: "plan_6b3d9f52-1e74-4a86-9c2f-5d0a8e1b3c47",
      library_id: LIBRARY_ID,
      track_id: "trk_refresh_102",
      action_type: "move",
      source_path: "Kenshi Yonezu/BOOTLEG/04 Lemon.flac",
      target_path: "Kenshi Yonezu/2018_BOOTLEG/1-04_Lemon.flac",
      content_hash_at_plan: "sha256:mock-content-501",
      metadata_hash_at_plan: "sha256:mock-metadata-501",
      status: "planned",
      reason: null,
      sort_order: 1,
    },
    {
      action_id: "act_502",
      plan_id: "plan_6b3d9f52-1e74-4a86-9c2f-5d0a8e1b3c47",
      library_id: LIBRARY_ID,
      track_id: "trk_refresh_103",
      action_type: "move",
      source_path: "Kenshi Yonezu/BOOTLEG/05 Uchiage Hanabi.flac",
      target_path: "Kenshi Yonezu/2018_BOOTLEG/1-05_Uchiage-Hanabi.flac",
      content_hash_at_plan: "sha256:mock-content-502",
      metadata_hash_at_plan: "sha256:mock-metadata-502",
      status: "planned",
      reason: null,
      sort_order: 2,
    },
    {
      action_id: "act_503",
      plan_id: "plan_6b3d9f52-1e74-4a86-9c2f-5d0a8e1b3c47",
      library_id: LIBRARY_ID,
      track_id: "trk_4a1b2c3d-0005",
      action_type: "refresh_metadata",
      source_path: "Kenshi Yonezu/2018_BOOTLEG/1-06_Loser.flac",
      target_path: "Kenshi Yonezu/2018_BOOTLEG/1-06_Loser.flac",
      content_hash_at_plan: "sha256:mock-content-503",
      metadata_hash_at_plan: "sha256:mock-metadata-503",
      status: "planned",
      reason: null,
      sort_order: 3,
    },
  ],
  "plan_a12f8c4d-77e0-4b9a-91c2-0d4e6f8a1b22": [
    {
      action_id: "pa_101",
      plan_id: "plan_a12f8c4d-77e0-4b9a-91c2-0d4e6f8a1b22",
      library_id: LIBRARY_ID,
      track_id: null,
      action_type: "move",
      source_path: "/music/incoming/Intro.flac",
      target_path: "Aimer/2024_Example Album/1-01_Intro.flac",
      content_hash_at_plan: null,
      metadata_hash_at_plan: null,
      status: "applied",
      reason: null,
      sort_order: 1,
    },
    {
      action_id: "pa_102",
      plan_id: "plan_a12f8c4d-77e0-4b9a-91c2-0d4e6f8a1b22",
      library_id: LIBRARY_ID,
      track_id: null,
      action_type: "move",
      source_path: "/music/incoming/Example Song.flac",
      target_path: "Aimer/2024_Example Album/1-03_Example Song.flac",
      content_hash_at_plan: "sha256:mock-content-102",
      metadata_hash_at_plan: "sha256:mock-metadata-102",
      status: "applied",
      reason: null,
      sort_order: 2,
    },
    {
      action_id: "pa_103",
      plan_id: "plan_a12f8c4d-77e0-4b9a-91c2-0d4e6f8a1b22",
      library_id: LIBRARY_ID,
      track_id: null,
      action_type: "move",
      source_path: "/music/incoming/Example Song.flac",
      target_path: "Aimer/2024_Example Album/1-03_Example Song.flac",
      content_hash_at_plan: null,
      metadata_hash_at_plan: null,
      status: "applied",
      reason: null,
      sort_order: 3,
    },
  ],
}

export function mockPlanDetailResponse(planId: string): PlanDetailResponse {
  const plan = mockPlans.find((candidate) => candidate.plan_id === planId)
  if (!plan) {
    return { detail: null, errors: ["Plan was not found."] }
  }
  return {
    detail: {
      plan: {
        ...plan,
        config_hash: "mock-config-hash",
        library_root_at_plan: defaultConfig.paths.library ?? "/music/library",
      },
    },
    errors: [],
  }
}

export function mockCreatePlan(planType: PlanType): PlanCreateResult {
  const createdPlan: PlanSummary = {
    plan_id: `plan_mock_${planType}_${Date.now()}`,
    library_id: LIBRARY_ID,
    plan_type: planType,
    status: "ready",
    created_at: new Date().toISOString(),
    summary: { action_count: "1", blocked_actions: "0" },
  }
  return {
    created: true,
    detail: {
      plan: {
        ...createdPlan,
        config_hash: "mock-created-config-hash",
        library_root_at_plan: defaultConfig.paths.library ?? "/music/library",
      },
    },
    registration: null,
    errors: [],
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
    // Points at plan_9e2c6b41 (status partial_failed below) rather than a
    // "ready" Plan: Plans are single-use snapshots, so a Plan referenced by
    // a completed Run must itself carry that Run's terminal status. This
    // also exercises the Plan detail "View run" cross-link for a
    // partial_failed Plan (see mock coverage notes on mockPlans).
    plan_id: "plan_9e2c6b41-8a37-4d19-b5f0-2c7e4a9d1f66",
    library_id: LIBRARY_ID,
    status: "partial_failed",
    started_at: "2026-06-28T20:02:11Z",
    completed_at: "2026-06-28T20:03:37Z",
    error_summary: "1 action failed (permission denied).",
  },
  {
    run_id: "run_1e8f4b22-9a07-4c5d-8b3e-6f2a1d0c9e88",
    // Points at plan_2f8a4d17 (status failed below) for the same reason as
    // run_7c1a5e90 above.
    plan_id: "plan_2f8a4d17-6c93-4b52-9e0d-8b1f3c6a7e29",
    library_id: LIBRARY_ID,
    status: "failed",
    started_at: "2026-06-27T11:48:55Z",
    completed_at: "2026-06-27T11:49:02Z",
    error_summary: "Library became unregistered before apply; aborted.",
  },
  {
    run_id: "run_5a2d9c71-6b40-4e83-a1f9-8c7b0e2d3a99",
    // The in-progress Run matches its applying Plan, so the Run-to-Plan
    // cross-link remains usable in static preview mode.
    plan_id: "plan_7f3e9c21-4a68-4d91-b0f3-8d6e2c9a1b57",
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
  {
    run_id: "run_9c4f7a35-8d12-4b6e-a97f-1e5c3d8b0a44",
    // The apply Run for plan_f31e7a08 (status "applied" in mockPlans), so
    // the Plan detail "View run" cross-link is exercised for the applied
    // status in mock mode.
    plan_id: "plan_f31e7a08-2b6c-4d90-8a5e-1c4f0b9d7e22",
    library_id: LIBRARY_ID,
    status: "succeeded",
    started_at: "2026-06-27T08:45:10Z",
    completed_at: "2026-06-27T08:45:41Z",
    error_summary: null,
  },
]

export const mockFileEvents: Record<string, FileEvent[]> = {
  "run_7c1a5e90-2d63-4f18-bb47-9a0e3c6d5f10": [
    {
      event_id: "evt_0a1b2c3d-0001",
      library_id: LIBRARY_ID,
      run_id: "run_7c1a5e90-2d63-4f18-bb47-9a0e3c6d5f10",
      plan_action_id: "act_301",
      event_type: "move_file",
      source_path: "Loose/Aimer - Torches.flac",
      target_path: "Aimer/2019_Torches/1-01_Torches.flac",
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
      plan_action_id: "act_302",
      event_type: "move_file",
      source_path: "Loose/Aimer - Ref-rain.flac",
      target_path: "Aimer/2018_Ref-rain/1-01_Ref-rain.flac",
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
      plan_action_id: "act_303",
      event_type: "move_file",
      source_path: "Loose/Aimer - Black Bird.flac",
      target_path: "Aimer/2018_Black-Bird/1-01_Black-Bird.flac",
      status: "succeeded",
      started_at: "2026-06-28T20:03:30Z",
      completed_at: "2026-06-28T20:03:30Z",
      error_code: null,
      error_message: null,
      sequence_no: 17,
    },
    {
      event_id: "evt_0a1b2c3d-0004",
      library_id: LIBRARY_ID,
      run_id: "run_7c1a5e90-2d63-4f18-bb47-9a0e3c6d5f10",
      plan_action_id: "act_304",
      event_type: "move_file",
      source_path: "Loose/Aimer - Zankyosanka.flac",
      target_path: "Aimer/2022_Zankyosanka/1-01_Zankyosanka.flac",
      status: "failed",
      started_at: "2026-06-28T20:03:36Z",
      completed_at: "2026-06-28T20:03:37Z",
      error_code: "move_failed",
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
      event_type: "move_file",
      source_path: "/music/incoming/Intro.flac",
      target_path: "Aimer/2024_Example Album/1-01_Intro.flac",
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
      event_type: "move_file",
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
      event_type: "move_file",
      source_path: "/music/incoming/Example Song.flac",
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
  // Apply Run for plan_f31e7a08: one move event mirroring its single
  // applied action (act_201).
  "run_9c4f7a35-8d12-4b6e-a97f-1e5c3d8b0a44": [
    {
      event_id: "evt_9c4f7a35-0001",
      library_id: LIBRARY_ID,
      run_id: "run_9c4f7a35-8d12-4b6e-a97f-1e5c3d8b0a44",
      plan_action_id: "act_201",
      event_type: "move",
      source_path: "Loose/Track.flac",
      target_path: "Aimer/2019_Sun-Dance/1-01_Track.flac",
      status: "succeeded",
      started_at: "2026-06-27T08:45:11Z",
      completed_at: "2026-06-27T08:45:12Z",
      error_code: null,
      error_message: null,
      sequence_no: 1,
    },
  ],
}

export function mockRunDetailResponse(runId: string): RunDetailResponse {
  const run = mockRuns.find((candidate) => candidate.run_id === runId)
  if (!run) {
    return { detail: null, errors: ["Run was not found."] }
  }
  return {
    detail: {
      run,
    },
    errors: [],
  }
}

// A former/candidate library referenced only by library-state issues below —
// distinct from LIBRARY_ID (the single actively registered library that
// Plans/Runs/Tracks fixtures point to) so registered-vs-unregistered issue
// types don't contradict each other for the same library.
const CANDIDATE_LIBRARY_ID = "lib_5c2e8f91-6a34-4b7d-8e01-9f3a2b6d4c88"
const BLOCKED_LIBRARY_ID = "lib_7d4f1a63-2b95-4e18-a706-3c8d5f0b9e21"

// Static previews use this fixture when the FastAPI backend is unavailable.
// Note: `severity` and `issue_id` are intentionally omitted — the real
// serializer (serialize_check_issue) never emits them, so mock issues must
// exercise the same client-side severityForIssue() derivation as production.
export const mockIssues: CheckIssue[] = [
  {
    issue_type: "db_file_missing",
    library_id: LIBRARY_ID,
    path: "Sawano Hiroyuki/2019_R∃/1-12_Into the Sky.flac",
    track_id: "trk_4a1b2c3d-0009",
    plan_id: null,
    detail: "Tracked file is recorded in the DB but no longer exists on disk.",
  },
  {
    issue_type: "unmanaged_file_exists",
    library_id: LIBRARY_ID,
    path: "Misc/_unsorted/random-download.mp3",
    track_id: null,
    plan_id: null,
    detail: "File exists under the library root but is not tracked in the DB.",
  },
  {
    issue_type: "current_path_differs_from_canonical_path",
    library_id: LIBRARY_ID,
    path: "Aimer/Open a Door/03 Example Song.flac",
    track_id: "trk_4a1b2c3d-0002",
    plan_id: null,
    detail: "Current path does not match the canonical path produced by the active path policy.",
  },
  {
    issue_type: "content_hash_changed",
    library_id: LIBRARY_ID,
    path: "Kenshi Yonezu/2018_BOOTLEG/1-04_Lemon.flac",
    track_id: "trk_4a1b2c3d-0005",
    plan_id: null,
    detail: "Content hash differs from the recorded value; file may have been re-encoded.",
  },
  {
    issue_type: "metadata_hash_changed",
    library_id: LIBRARY_ID,
    path: "Kenshi Yonezu/2018_BOOTLEG/1-04_Lemon.flac",
    track_id: "trk_4a1b2c3d-0005",
    plan_id: null,
    detail: "Embedded metadata changed since last scan; canonical path may need refresh.",
  },
  {
    issue_type: "duplicate_candidate",
    library_id: LIBRARY_ID,
    path: "Various Artists/2013_Deemo/2-05_Anima.mp3",
    track_id: "trk_4a1b2c3d-0011",
    plan_id: null,
    detail: "Another tracked file shares the same content hash.",
  },
  {
    issue_type: "pending_file_event_exists",
    library_id: LIBRARY_ID,
    path: "Aimer/2024_Open α Door/1-03_Example Song.flac",
    track_id: null,
    plan_id: "plan_d54b1a09-3c8e-4f2b-a6d7-1e9c0b4a7f55",
    detail: "A file event from an interrupted run is still pending; recovery recommended.",
  },
  {
    issue_type: "library_stale",
    library_id: LIBRARY_ID,
    path: "/music/library",
    track_id: null,
    plan_id: null,
    detail: "Library has not been refreshed in over 14 days.",
  },
  {
    issue_type: "plan_source_changed",
    library_id: LIBRARY_ID,
    path: "Aimer/Open a Door/03 Example Song.flac",
    track_id: "trk_4a1b2c3d-0002",
    plan_id: "plan_b98c2f10-5d4a-4e7b-8c61-3a0f9d2e1c44",
    detail: "The tracked file changed after this Plan was created; re-plan before applying.",
  },
  {
    issue_type: "library_unregistered",
    library_id: CANDIDATE_LIBRARY_ID,
    path: "/music/archive",
    track_id: null,
    plan_id: null,
    detail:
      "This library root was scanned but has no matching registration; run `omym2 organize` to register it.",
  },
  {
    issue_type: "library_blocked",
    library_id: BLOCKED_LIBRARY_ID,
    path: "/music/blocked-import",
    track_id: null,
    plan_id: null,
    detail:
      "Library registration is blocked pending manual review; CLI commands targeting it will be rejected.",
  },
]

// Cross-link previews must resolve every PlanAction.track_id to a managed Track.
function mockActionTrack(
  trackId: string,
  currentPath: string,
  title: string | null,
  artist: string | null,
  album: string | null,
  year: number | null,
  trackNumber: number | null,
): TrackSummary {
  return {
    track_id: trackId,
    library_id: LIBRARY_ID,
    current_path: currentPath,
    canonical_path: currentPath,
    content_hash: `blake3:mock-content-${trackId}`,
    metadata_hash: `blake3:mock-metadata-${trackId}`,
    metadata: {
      title,
      artist,
      album,
      album_artist: artist,
      genre: null,
      year,
      track_number: trackNumber,
      track_total: null,
      disc_number: trackNumber === null ? null : 1,
      disc_total: trackNumber === null ? null : 1,
    },
    status: "active",
    first_seen_at: "2026-06-20T12:00:00Z",
    last_seen_at: "2026-06-29T08:00:00Z",
    updated_at: "2026-06-29T08:00:00Z",
  }
}

const mockActionTracks: TrackSummary[] = [
  mockActionTrack(
    "trk_refresh_001",
    "Aimer/2023_Open-a-Door/1-03_New-Title.flac",
    "New Title",
    "Aimer",
    "Open-a-Door",
    2023,
    3,
  ),
  mockActionTrack(
    "trk_refresh_002",
    "Aimer/2023_Open-a-Door/1-04_Unchanged.flac",
    "Unchanged",
    "Aimer",
    "Open-a-Door",
    2023,
    4,
  ),
  mockActionTrack(
    "trk_organize_001",
    "Aimer/2019_Sun-Dance/1-01_Track.flac",
    "Track",
    "Aimer",
    "Sun Dance",
    2019,
    1,
  ),
  mockActionTrack(
    "trk_organize_101",
    "Aimer/2019_Torches/1-01_Torches.flac",
    "Torches",
    "Aimer",
    "Torches",
    2019,
    1,
  ),
  mockActionTrack(
    "trk_organize_102",
    "Aimer/2018_Ref-rain/1-01_Ref-rain.flac",
    "Ref-rain",
    "Aimer",
    "Ref-rain",
    2018,
    1,
  ),
  mockActionTrack(
    "trk_organize_103",
    "Aimer/2018_Black-Bird/1-01_Black-Bird.flac",
    "Black Bird",
    "Aimer",
    "Black Bird",
    2018,
    1,
  ),
  mockActionTrack(
    "trk_organize_104",
    "Aimer/2022_Zankyosanka/1-01_Zankyosanka.flac",
    "Zankyosanka",
    "Aimer",
    "Zankyosanka",
    2022,
    1,
  ),
  mockActionTrack(
    "trk_organize_105",
    "Loose/Unknown - Untitled.flac",
    null,
    null,
    null,
    null,
    null,
  ),
  mockActionTrack(
    "trk_organize_106",
    "Loose/Aimer - Torches (copy).flac",
    "Torches",
    "Aimer",
    "Torches",
    2019,
    1,
  ),
  mockActionTrack(
    "trk_refresh_102",
    "Kenshi Yonezu/2018_BOOTLEG/1-05_Uchiage-Hanabi.flac",
    "Uchiage Hanabi",
    "Kenshi Yonezu",
    "BOOTLEG",
    2018,
    5,
  ),
  mockActionTrack(
    "trk_refresh_103",
    "Kenshi Yonezu/2018_BOOTLEG/1-06_Loser.flac",
    "Loser",
    "Kenshi Yonezu",
    "BOOTLEG",
    2018,
    6,
  ),
]

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
  {
    track_id: "trk_4a1b2c3d-0012",
    library_id: LIBRARY_ID,
    current_path: "Various Artists/2013_Deemo/1-01_Dream.mp3",
    canonical_path: "Various Artists/2013_Deemo/1-01_Dream.mp3",
    content_hash: "blake3:1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a",
    metadata_hash: "blake3:4c4c4c4c4c4c4c4c4c4c4c4c4c4c4c4c4c4c4c4c4c4c4c4c4c4c4c4c4c4c4c4c4c",
    metadata: {
      title: "Dream",
      artist: "M2U",
      album: "Deemo",
      album_artist: "Various Artists",
      genre: "Game",
      year: 2013,
      track_number: 1,
      track_total: 20,
      disc_number: 1,
      disc_total: 2,
    },
    status: "active",
    first_seen_at: "2026-06-10T15:28:00Z",
    last_seen_at: "2026-06-29T08:00:00Z",
    updated_at: "2026-06-10T15:29:00Z",
  },
  ...mockActionTracks,
]

// --- Paginated Web API mocks (D6) -------------------------------------------
// Pure paging/faceting/grouping helpers plus a mock branch for every new
// api-client.ts method (getTracksPage, getTrackFacets, getTrackGroups,
// getPlansPage, getPlanActionsPage, getPlanFacets, getPlanGroups,
// getCheckPage, getCheckFacets, getCheckGroups, runCheck, getHistoryPage,
// getHistoryFacets, getRunEventsPage). Matches the server envelope shapes in
// types.ts (PagedResponse/FacetsResponse/GroupsResponse) exactly so screens
// added in later dispatches can switch between mock and live data freely.

const DEFAULT_PAGE_LIMIT = 100

// Cursors are opaque to callers; the mock encodes them as a base64url string
// over the UTF-8 bytes of the decimal row index. This is a mock-only
// encoding — it has no relationship to the real server's cursor format.
const BASE64URL_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"

function encodeCursor(index: number): string {
  const bytes = new TextEncoder().encode(String(index))
  let output = ""
  for (let i = 0; i < bytes.length; i += 3) {
    const b0 = bytes[i] ?? 0
    const b1 = bytes[i + 1]
    const b2 = bytes[i + 2]
    const triplet = (b0 << 16) | ((b1 ?? 0) << 8) | (b2 ?? 0)
    output += BASE64URL_ALPHABET[(triplet >> 18) & 0x3f]
    output += BASE64URL_ALPHABET[(triplet >> 12) & 0x3f]
    output += b1 === undefined ? "" : BASE64URL_ALPHABET[(triplet >> 6) & 0x3f]
    output += b2 === undefined ? "" : BASE64URL_ALPHABET[triplet & 0x3f]
  }
  return output
}

function decodeCursor(cursor: string): number {
  const bytes: number[] = []
  let buffer = 0
  let bitsCollected = 0
  for (const ch of cursor) {
    const value = BASE64URL_ALPHABET.indexOf(ch)
    if (value < 0) {
      continue
    }
    buffer = (buffer << 6) | value
    bitsCollected += 6
    if (bitsCollected >= 8) {
      bitsCollected -= 8
      bytes.push((buffer >> bitsCollected) & 0xff)
    }
  }
  const text = new TextDecoder().decode(new Uint8Array(bytes))
  const parsed = Number.parseInt(text, 10)
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0
}

/**
 * Filters `rows` with `predicate` (if given), then pages the result.
 * `page.total` is the filtered count (not the unfiltered fixture size).
 * Behaves sanely when `limit` exceeds the number of remaining rows: the
 * page simply contains everything left and `next_cursor` is null.
 */
export function pageMock<T>(
  rows: T[],
  opts: { limit?: number; cursor?: string; predicate?: (row: T) => boolean } = {},
): PagedResponse<T> {
  const filtered = opts.predicate ? rows.filter(opts.predicate) : rows.slice()
  const limit = opts.limit && opts.limit > 0 ? opts.limit : DEFAULT_PAGE_LIMIT
  const requestedStart = opts.cursor ? decodeCursor(opts.cursor) : 0
  const start =
    Number.isFinite(requestedStart) && requestedStart >= 0
      ? Math.min(requestedStart, filtered.length)
      : 0
  const items = filtered.slice(start, start + limit)
  const nextIndex = start + items.length
  const nextCursor = nextIndex < filtered.length ? encodeCursor(nextIndex) : null
  return {
    items,
    page: { limit, next_cursor: nextCursor, total: filtered.length },
    errors: [],
  }
}

/** Counts each extractor's values over `rows`; order is count DESC, value ASC. */
export function facetsMock<T>(
  rows: T[],
  extractors: Record<string, (row: T) => string | null | undefined>,
): FacetsResponse {
  const facets: Record<string, FacetValue[]> = {}
  for (const [field, extractor] of Object.entries(extractors)) {
    const counts = new Map<string, number>()
    for (const row of rows) {
      const value = extractor(row)
      if (value === null || value === undefined || value === "") {
        continue
      }
      counts.set(value, (counts.get(value) ?? 0) + 1)
    }
    facets[field] = Array.from(counts.entries())
      .map(([value, count]): FacetValue => ({ value, count }))
      .sort((a, b) => b.count - a.count || compareSqliteBinaryText(a.value, b.value))
  }
  return { facets, total: rows.length, errors: [] }
}

/** Groups `rows` by `keyFn`, counts each group, then pages the group list. */
export function groupsMock<T>(
  groupBy: string,
  rows: T[],
  keyFn: (row: T) => string,
  options: {
    labelFn?: (row: T) => string
    limit?: number
    cursor?: string
  } = {},
): GroupsResponse {
  const counts = new Map<string, { label: string; count: number }>()
  for (const row of rows) {
    const key = keyFn(row)
    const label = options.labelFn ? options.labelFn(row) : key
    const existing = counts.get(key)
    if (existing) {
      existing.count += 1
    } else {
      counts.set(key, { label, count: 1 })
    }
  }
  const allItems: GroupCount[] = Array.from(counts.entries())
    .map(([key, { label, count }]): GroupCount => ({ key, label, count }))
    .sort((a, b) => b.count - a.count || compareSqliteBinaryText(a.key, b.key))
  const paged = pageMock(allItems, { limit: options.limit, cursor: options.cursor })
  return { group_by: groupBy, items: paged.items, page: paged.page, errors: [] }
}

// --- Filter predicates mirroring server semantics (see filterPlanRows above)

// The live API folds case with SQLite's LOWER(), which is ASCII-only, and
// matches each stored field independently — never across field boundaries.
function asciiLowerCase(text: string): string {
  return text.replace(/[A-Z]/g, (letter) => letter.toLowerCase())
}

function matchesSearch(values: (string | null | undefined)[], needle: string): boolean {
  return values.some((value) => value != null && asciiLowerCase(value).includes(needle))
}

function searchNeedle(query: string | undefined): string | undefined {
  const trimmed = query?.trim()
  return trimmed ? asciiLowerCase(trimmed) : undefined
}

function buildTrackPredicate(options: {
  query?: string
  status?: TrackStatus | "all"
  libraryId?: string
  trackId?: string
  groupBy?: TrackGroupBy
  groupKey?: string
}): (row: TrackSummary) => boolean {
  const query = searchNeedle(options.query)
  return (row) => {
    if (options.libraryId && row.library_id !== options.libraryId) {
      return false
    }
    if (options.trackId && row.track_id !== options.trackId) {
      return false
    }
    if (options.status && options.status !== "all" && row.status !== options.status) {
      return false
    }
    if (
      options.groupBy &&
      options.groupKey !== undefined &&
      trackGroupEntry(row, options.groupBy).key !== options.groupKey
    ) {
      return false
    }
    if (
      query &&
      !matchesSearch(
        [
          row.metadata.title,
          row.metadata.artist,
          row.metadata.album,
          row.current_path,
          row.track_id,
        ],
        query,
      )
    ) {
      return false
    }
    return true
  }
}

const UNKNOWN_TRACK_GROUP_VALUE = "(unknown)"
const TRACK_GROUP_LEGACY_SEPARATOR = "\u001f"

interface TrackGroupParts {
  artist: string
  album: string
  year: number | null
  discKey: number | string
}

interface TrackGroupEntry {
  key: string
  label: string
}

function nonBlankTrackValue(value: string | null): string | null {
  return hasTrackGroupMetadataText(value) ? value : null
}

function trackGroupParts(track: TrackSummary): TrackGroupParts {
  const artist =
    nonBlankTrackValue(track.metadata.album_artist) ??
    nonBlankTrackValue(track.metadata.artist) ??
    UNKNOWN_TRACK_GROUP_VALUE
  const album = nonBlankTrackValue(track.metadata.album) ?? UNKNOWN_TRACK_GROUP_VALUE
  const discNumber = track.metadata.disc_number
  const discKey = discNumber !== null && discNumber > 0 ? discNumber : UNKNOWN_TRACK_GROUP_VALUE
  return { artist, album, year: track.metadata.year, discKey }
}

function trackArtistGroup(track: TrackSummary): TrackGroupEntry {
  const { artist } = trackGroupParts(track)
  return { key: JSON.stringify([artist]), label: artist }
}

function trackAlbumGroup(track: TrackSummary): TrackGroupEntry {
  const { artist, album, year } = trackGroupParts(track)
  return {
    key: JSON.stringify([artist, album, year]),
    label: year === null ? album : `${album} — ${year}`,
  }
}

function trackDiscGroup(track: TrackSummary): TrackGroupEntry {
  const { artist, album, year, discKey } = trackGroupParts(track)
  return {
    key: JSON.stringify([artist, album, year, discKey]),
    label: typeof discKey === "number" ? `Disc ${discKey}` : "Unnumbered disc",
  }
}

function trackArtistAlbumGroup(track: TrackSummary): TrackGroupEntry {
  const artist = track.metadata.album_artist ?? track.metadata.artist ?? UNKNOWN_TRACK_GROUP_VALUE
  const album = track.metadata.album ?? UNKNOWN_TRACK_GROUP_VALUE
  return {
    key: `${artist}${TRACK_GROUP_LEGACY_SEPARATOR}${album}`,
    label: `${artist} — ${album}`,
  }
}

function trackGroupEntry(track: TrackSummary, groupBy: TrackGroupBy): TrackGroupEntry {
  switch (groupBy) {
    case "artist":
      return trackArtistGroup(track)
    case "album":
      return trackAlbumGroup(track)
    case "disc":
      return trackDiscGroup(track)
    case "artist_album":
      return trackArtistAlbumGroup(track)
  }
}

function trackBrowserLeafOrder(left: TrackSummary, right: TrackSummary): number {
  const leftTrackNumber = left.metadata.track_number
  const rightTrackNumber = right.metadata.track_number
  const leftIsNumbered = leftTrackNumber !== null && leftTrackNumber > 0
  const rightIsNumbered = rightTrackNumber !== null && rightTrackNumber > 0
  if (leftIsNumbered !== rightIsNumbered) {
    return leftIsNumbered ? -1 : 1
  }
  if (leftIsNumbered && rightIsNumbered && leftTrackNumber !== rightTrackNumber) {
    return leftTrackNumber - rightTrackNumber
  }
  const titleOrder = compareSqliteBinaryText(left.metadata.title ?? "", right.metadata.title ?? "")
  return titleOrder || compareSqliteBinaryText(left.track_id, right.track_id)
}

function buildPlanPredicate(options: {
  status?: PlanStatus | "all"
  type?: PlanType | "all"
  blockedOnly?: boolean
}): (row: PlanSummary) => boolean {
  return (row) => {
    if (options.status && options.status !== "all" && row.status !== options.status) {
      return false
    }
    if (options.type && options.type !== "all" && row.plan_type !== options.type) {
      return false
    }
    if (options.blockedOnly && !(Number.parseInt(row.summary.blocked_actions ?? "0", 10) > 0)) {
      return false
    }
    return true
  }
}

function buildPlanActionPredicate(options: {
  query?: string
  status?: PlanActionStatus | "all"
  actionType?: PlanActionType | "all"
  reason?: PlanActionReason | "all"
  groupBy?: PlanGroupBy
  groupKey?: string
}): (row: PlanAction) => boolean {
  const query = searchNeedle(options.query)
  return (row) => {
    if (options.status && options.status !== "all" && row.status !== options.status) {
      return false
    }
    if (
      options.actionType &&
      options.actionType !== "all" &&
      row.action_type !== options.actionType
    ) {
      return false
    }
    if (options.reason && options.reason !== "all" && row.reason !== options.reason) {
      return false
    }
    if (options.groupBy && options.groupKey !== undefined) {
      const entry = planGroupEntry(row, options.groupBy)
      if (!entry || entry.key !== options.groupKey) {
        return false
      }
    }
    if (
      query &&
      !matchesSearch(
        [
          row.action_id,
          row.track_id,
          row.source_path,
          row.target_path,
          row.content_hash_at_plan,
          row.metadata_hash_at_plan,
        ],
        query,
      )
    ) {
      return false
    }
    return true
  }
}

// --- Plan group key semantics (mirrors the backend groups endpoint) ----------
// These derive group keys from the action fixtures with the same rules as the
// server so mock counts always match what filtering the fixtures produces.

/** Posix dirname: text before the final "/", "" for bare names, "/" for root files. */
function posixDirname(path: string): string {
  const index = path.lastIndexOf("/")
  if (index < 0) {
    return ""
  }
  return index === 0 ? "/" : path.slice(0, index)
}

/** Lowercased final suffix (no dot) of the source basename, falling back to target. */
function planActionExtension(action: PlanAction): string {
  const path = action.source_path ?? action.target_path
  if (!path) {
    return "(none)"
  }
  const basename = path.split("/").pop() ?? ""
  const dot = basename.lastIndexOf(".")
  if (dot <= 0 || dot === basename.length - 1) {
    return "(none)"
  }
  return basename.slice(dot + 1).toLowerCase()
}

/**
 * The group an action belongs to under `groupBy`, or null when the action is
 * skipped for that key (null target/source directory, null block reason).
 */
function planGroupEntry(
  action: PlanAction,
  groupBy: PlanGroupBy,
): { key: string; label: string } | null {
  switch (groupBy) {
    case "target_directory": {
      if (action.target_path === null) {
        return null
      }
      const dir = posixDirname(action.target_path)
      const key = dir === "" ? "(root)" : dir
      return { key, label: key }
    }
    case "source_directory": {
      if (action.source_path === null) {
        return null
      }
      const dir = posixDirname(action.source_path)
      const key = dir === "" ? "(root)" : dir
      return { key, label: key }
    }
    case "artist_album": {
      if (action.target_path === null) {
        return { key: "(unknown)", label: "Unknown Artist / Unknown Album" }
      }
      const segments = posixDirname(action.target_path).split("/").filter(Boolean).slice(0, 2)
      if (segments.length === 0) {
        return { key: "(root)", label: "(root)" }
      }
      return { key: segments.join("/"), label: segments.join(" / ") }
    }
    case "action_type":
      return { key: action.action_type, label: action.action_type }
    case "status":
      return { key: action.status, label: action.status }
    case "block_reason": {
      if (action.reason === null) {
        return null
      }
      return { key: action.reason, label: action.reason }
    }
    case "extension": {
      const extension = planActionExtension(action)
      return { key: extension, label: extension }
    }
  }
}

/** Most frequent non-null reason (ties break to the lexicographically smallest). */
function topReasonOf(reasonCounts: Map<string, number>): string | null {
  let top: string | null = null
  let topCount = 0
  for (const [reason, count] of reasonCounts) {
    if (count > topCount || (count === topCount && top !== null && reason < top)) {
      top = reason
      topCount = count
    }
  }
  return top
}

/** Distinct non-null target paths used by two or more actions. */
function countTargetCollisions(rows: PlanAction[]): number {
  const counts = new Map<string, number>()
  for (const row of rows) {
    if (row.target_path === null) {
      continue
    }
    counts.set(row.target_path, (counts.get(row.target_path) ?? 0) + 1)
  }
  let collisions = 0
  for (const count of counts.values()) {
    if (count >= 2) {
      collisions += 1
    }
  }
  return collisions
}

function buildCheckPredicate(options: {
  query?: string
  issueType?: CheckIssueType | "all"
  libraryId?: string
  groupBy?: CheckGroupBy
  groupKey?: string
}): (row: CheckIssue) => boolean {
  const query = searchNeedle(options.query)
  return (row) => {
    if (options.libraryId && row.library_id !== options.libraryId) {
      return false
    }
    if (options.issueType && options.issueType !== "all" && row.issue_type !== options.issueType) {
      return false
    }
    if (options.groupBy && options.groupKey !== undefined) {
      const entry = checkGroupEntry(row, options.groupBy)
      if (entry.key !== options.groupKey) {
        return false
      }
    }
    if (
      query &&
      !matchesSearch([row.library_id, row.path, row.track_id, row.plan_id, row.detail], query)
    ) {
      return false
    }
    return true
  }
}

/** Match the API's path-root grouping for relative, root-level, and external paths. */
function checkPathRoot(path: string | null): string {
  if (!path) {
    return "(unknown)"
  }
  if (path.startsWith("/")) {
    return "(external)"
  }
  const directories = path.split("/").slice(0, -1)
  if (directories.length === 0) {
    return "(root)"
  }
  return `${directories[0]}/`
}

/** Match the API's nullable common-root summary for pathless issues. */
function commonCheckPathRootValue(path: string | null): string | null {
  return path ? checkPathRoot(path) : null
}

/** Stable command families keep per-path refresh/add commands in one group. */
function checkSuggestedCommand(issueType: CheckIssueType): { key: string; label: string } {
  switch (issueType) {
    case "db_file_missing":
    case "content_hash_changed":
    case "metadata_hash_changed":
      return { key: "refresh", label: "omym2 refresh <file>" }
    case "unmanaged_file_exists":
      return { key: "add", label: "omym2 add <path>" }
    case "current_path_differs_from_canonical_path":
    case "duplicate_candidate":
    case "plan_source_changed":
      return { key: "organize", label: "omym2 organize" }
    case "pending_file_event_exists":
      return { key: "history", label: "omym2 history" }
    case "library_unregistered":
    case "library_stale":
    case "library_blocked":
      return { key: "check", label: "omym2 check" }
  }
}

/** Path-based mock grouping used until a static preview has a real track join. */
function checkArtistAlbum(path: string | null): { key: string; label: string } {
  if (!path) {
    return { key: "(unknown)", label: "Unknown Artist / Unknown Album" }
  }
  if (path.startsWith("/")) {
    return { key: "(external)", label: "(external)" }
  }
  // Positional segments, matching the server's SQL derivation byte for byte.
  const directories = path.split("/").slice(0, -1)
  if (directories.length === 0) {
    return { key: "(root)", label: "(root)" }
  }
  const artist = directories[0]
  const album = directories[1] ?? "(root)"
  return { key: `${artist}\u001f${album}`, label: `${artist} / ${album}` }
}

/** Derive the Check grouping key from one persisted issue fixture. */
function checkGroupEntry(issue: CheckIssue, groupBy: CheckGroupBy): { key: string; label: string } {
  switch (groupBy) {
    case "issue_type":
      return { key: issue.issue_type, label: issue.issue_type }
    case "severity": {
      const severity = issue.severity ?? severityForIssue(issue.issue_type)
      return { key: severity, label: severity }
    }
    case "path_root": {
      const pathRoot = checkPathRoot(issue.path)
      return { key: pathRoot, label: pathRoot }
    }
    case "artist_album":
      return checkArtistAlbum(issue.path)
    case "suggested_command":
      return checkSuggestedCommand(issue.issue_type)
    case "library_id":
      return { key: issue.library_id, label: issue.library_id }
  }
}

/** Most common path root, with deterministic lexical tie-breaking. */
function commonCheckPathRoot(rootCounts: Map<string, number>): string | null {
  let commonRoot: string | null = null
  let commonCount = 0
  for (const [root, count] of rootCounts) {
    if (
      count > commonCount ||
      (count === commonCount && commonRoot !== null && root < commonRoot)
    ) {
      commonRoot = root
      commonCount = count
    }
  }
  return commonRoot
}

function buildRunPredicate(options: {
  status?: RunStatus | "all"
  libraryId?: string
  planId?: string
}): (row: RunSummary) => boolean {
  return (row) => {
    if (options.libraryId && row.library_id !== options.libraryId) {
      return false
    }
    if (options.planId && row.plan_id !== options.planId) {
      return false
    }
    if (options.status && options.status !== "all" && row.status !== options.status) {
      return false
    }
    return true
  }
}

function buildFileEventPredicate(options: {
  status?: FileEventStatus | "all"
}): (row: FileEvent) => boolean {
  return (row) => {
    if (options.status && options.status !== "all" && row.status !== options.status) {
      return false
    }
    return true
  }
}

function targetDirectoryOf(path: string | null): string {
  if (!path) {
    return "(unresolved)"
  }
  const segments = path.split("/")
  segments.pop()
  return segments.length > 0 ? segments.join("/") : "(root)"
}

// --- Tracks ------------------------------------------------------------------

export function mockGetTracksPage(
  options: {
    query?: string
    status?: TrackStatus | "all"
    libraryId?: string
    trackId?: string
    groupBy?: TrackGroupBy
    groupKey?: string
    limit?: number
    cursor?: string
  } = {},
): PagedResponse<TrackSummary> {
  assertTrackGroupFilter(options)
  const rows =
    options.groupBy && options.groupKey !== undefined
      ? mockTracks.slice().sort(trackBrowserLeafOrder)
      : mockTracks
  return pageMock(rows, {
    limit: options.limit,
    cursor: options.cursor,
    predicate: buildTrackPredicate(options),
  })
}

export function mockGetTrackFacets(
  options: { query?: string; libraryId?: string } = {},
): FacetsResponse {
  const rows = mockTracks.filter(buildTrackPredicate(options))
  return facetsMock(rows, { status: (track) => track.status })
}

export function mockGetTrackGroups(options: {
  groupBy: TrackGroupBy
  parentKey?: string
  query?: string
  status?: TrackStatus | "all"
  libraryId?: string
  limit?: number
  cursor?: string
}): GroupsResponse {
  assertTrackGroupParentKey(options)
  const libraryRows = mockTracks.filter(buildTrackPredicate(options))
  const rows = libraryRows.filter((track) => {
    if (options.groupBy === "album" && options.parentKey !== undefined) {
      return trackArtistGroup(track).key === options.parentKey
    }
    if (options.groupBy === "disc" && options.parentKey !== undefined) {
      return trackAlbumGroup(track).key === options.parentKey
    }
    return true
  })
  return groupsMock(options.groupBy, rows, (track) => trackGroupEntry(track, options.groupBy).key, {
    labelFn: (track) => trackGroupEntry(track, options.groupBy).label,
    limit: options.limit,
    cursor: options.cursor,
  })
}

// --- Plans / plan actions -----------------------------------------------------

export function mockGetPlansPage(
  options: {
    status?: PlanStatus | "all"
    type?: PlanType | "all"
    blockedOnly?: boolean
    limit?: number
    cursor?: string
  } = {},
): PagedResponse<PlanSummary> {
  return pageMock(mockPlans, {
    limit: options.limit,
    cursor: options.cursor,
    predicate: buildPlanPredicate(options),
  })
}

export function mockGetPlanActionsPage(
  planId: string,
  options: {
    query?: string
    status?: PlanActionStatus | "all"
    actionType?: PlanActionType | "all"
    reason?: PlanActionReason | "all"
    groupBy?: PlanGroupBy
    groupKey?: string
    limit?: number
    cursor?: string
  } = {},
): PagedResponse<PlanAction> {
  const rows = mockPlanActions[planId] ?? []
  return pageMock(rows, {
    limit: options.limit,
    cursor: options.cursor,
    predicate: buildPlanActionPredicate(options),
  })
}

export function mockGetPlanFacets(
  planId: string,
  options: {
    query?: string
    status?: PlanActionStatus | "all"
    actionType?: PlanActionType | "all"
    reason?: PlanActionReason | "all"
  } = {},
): PlanFacetsResponse {
  const rows = mockPlanActions[planId] ?? []
  const statusRows = rows.filter(buildPlanActionPredicate({ ...options, status: "all" }))
  const typeRows = rows.filter(buildPlanActionPredicate({ ...options, actionType: "all" }))
  const reasonRows = rows.filter(buildPlanActionPredicate({ ...options, reason: "all" }))
  const filteredRows = rows.filter(buildPlanActionPredicate(options))
  return {
    facets: {
      status: facetsMock(statusRows, { status: (action) => action.status }).facets.status,
      action_type: facetsMock(typeRows, { action_type: (action) => action.action_type }).facets
        .action_type,
      reason: facetsMock(reasonRows, { reason: (action) => action.reason }).facets.reason,
    },
    total: filteredRows.length,
    errors: [],
    target_collisions: countTargetCollisions(rows),
  }
}

export function mockGetPlanGroups(
  planId: string,
  options: {
    groupBy: PlanGroupBy
    query?: string
    status?: PlanActionStatus | "all"
    actionType?: PlanActionType | "all"
    reason?: PlanActionReason | "all"
    limit?: number
    cursor?: string
  },
): PlanGroupsResponse {
  const rows = (mockPlanActions[planId] ?? []).filter(buildPlanActionPredicate(options))
  const groups = new Map<
    string,
    { label: string; count: number; blockedCount: number; reasons: Map<string, number> }
  >()
  for (const action of rows) {
    const entry = planGroupEntry(action, options.groupBy)
    if (!entry) {
      continue
    }
    let group = groups.get(entry.key)
    if (!group) {
      group = { label: entry.label, count: 0, blockedCount: 0, reasons: new Map() }
      groups.set(entry.key, group)
    }
    group.count += 1
    if (action.status === "blocked") {
      group.blockedCount += 1
    }
    if (action.reason !== null) {
      group.reasons.set(action.reason, (group.reasons.get(action.reason) ?? 0) + 1)
    }
  }
  const allItems: PlanGroupCount[] = Array.from(groups.entries())
    .map(([key, group]): PlanGroupCount => ({
      key,
      label: group.label,
      count: group.count,
      blocked_count: group.blockedCount,
      top_reason: topReasonOf(group.reasons),
    }))
    .sort((a, b) => b.count - a.count || compareSqliteBinaryText(a.key, b.key))
  const paged = pageMock(allItems, { limit: options.limit, cursor: options.cursor })
  return { group_by: options.groupBy, items: paged.items, page: paged.page, errors: [] }
}

// --- Check ---------------------------------------------------------------------

// Static previews use this fixture as the "last check run" timestamp for
// getCheckPage/getCheckFacets/runCheck — it has no relationship to any
// individual issue's detection time.
export const MOCK_CHECKED_AT = "2026-06-29T10:05:00Z"

export function mockGetCheckPage(
  options: {
    query?: string
    issueType?: CheckIssueType | "all"
    libraryId?: string
    groupBy?: CheckGroupBy
    groupKey?: string
    limit?: number
    cursor?: string
  } = {},
): CheckPageResponse {
  const paged = pageMock(mockIssues, {
    limit: options.limit,
    cursor: options.cursor,
    predicate: buildCheckPredicate(options),
  })
  return { ...paged, checked_at: MOCK_CHECKED_AT }
}

export function mockGetCheckFacets(
  options: { query?: string; libraryId?: string } = {},
): CheckFacetsResponse {
  const rows = mockIssues.filter(buildCheckPredicate(options))
  const facets = facetsMock(rows, { issue_type: (issue) => issue.issue_type })
  return { ...facets, checked_at: MOCK_CHECKED_AT }
}

export function mockGetCheckGroups(options: {
  groupBy: CheckGroupBy
  query?: string
  issueType?: CheckIssueType | "all"
  libraryId?: string
  limit?: number
  cursor?: string
}): CheckGroupsResponse {
  const rows = mockIssues.filter(buildCheckPredicate(options))
  const groups = new Map<
    string,
    { label: string; count: number; rootCounts: Map<string, number> }
  >()
  for (const issue of rows) {
    const entry = checkGroupEntry(issue, options.groupBy)
    let group = groups.get(entry.key)
    if (!group) {
      group = { label: entry.label, count: 0, rootCounts: new Map() }
      groups.set(entry.key, group)
    }
    group.count += 1
    const pathRoot = commonCheckPathRootValue(issue.path)
    if (pathRoot !== null) {
      group.rootCounts.set(pathRoot, (group.rootCounts.get(pathRoot) ?? 0) + 1)
    }
  }
  const allItems: CheckGroupCount[] = Array.from(groups.entries())
    .map(([key, group]): CheckGroupCount => ({
      key,
      label: group.label,
      count: group.count,
      common_path_root: commonCheckPathRoot(group.rootCounts),
    }))
    .sort((a, b) => b.count - a.count || compareSqliteBinaryText(a.key, b.key))
  const paged = pageMock(allItems, { limit: options.limit, cursor: options.cursor })
  return { group_by: options.groupBy, items: paged.items, page: paged.page, errors: [] }
}

export function mockRunCheck(libraryId?: string): CheckRunResponse {
  const rows = libraryId ? mockIssues.filter((issue) => issue.library_id === libraryId) : mockIssues
  return { checked_at: MOCK_CHECKED_AT, total: rows.length, errors: [] }
}

// --- History / run events -------------------------------------------------------

export function mockGetHistoryPage(
  options: {
    status?: RunStatus | "all"
    libraryId?: string
    planId?: string
    limit?: number
    cursor?: string
  } = {},
): PagedResponse<RunSummary> {
  return pageMock(mockRuns, {
    limit: options.limit,
    cursor: options.cursor,
    predicate: buildRunPredicate(options),
  })
}

export function mockGetHistoryFacets(options: { libraryId?: string } = {}): FacetsResponse {
  const rows = options.libraryId
    ? mockRuns.filter((run) => run.library_id === options.libraryId)
    : mockRuns
  return facetsMock(rows, { status: (run) => run.status })
}

export function mockGetRunEventsPage(
  runId: string,
  options: { status?: FileEventStatus | "all"; limit?: number; cursor?: string } = {},
): PagedResponse<FileEvent> {
  const rows = mockFileEvents[runId] ?? []
  return pageMock(rows, {
    limit: options.limit,
    cursor: options.cursor,
    predicate: buildFileEventPredicate(options),
  })
}

export function mockGetRunEventFacets(runId: string): FacetsResponse {
  const rows = mockFileEvents[runId] ?? []
  return facetsMock(rows, { status: (event) => event.status })
}

export function mockGetRunEventGroups(
  runId: string,
  options: { limit?: number; cursor?: string } = {},
): GroupsResponse {
  const rows = mockFileEvents[runId] ?? []
  return groupsMock("target_directory", rows, (event) => targetDirectoryOf(event.target_path), {
    limit: options.limit,
    cursor: options.cursor,
  })
}
