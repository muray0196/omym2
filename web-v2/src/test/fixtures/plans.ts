/**
 * Summary: Defines deterministic typed Plan inspection fixtures for the M2 read-only slice.
 * Why: Makes MSW fixtures drift with generated API envelopes instead of hand-maintained schemas.
 */
import type {
  ApiEnvelopePaginatedDataPlanActionResource,
  ApiEnvelopePaginatedDataPlanSummary,
  ApiEnvelopePlanActionFacetsData,
  ApiEnvelopePlanActionGroupsData,
  ApiEnvelopePlanDetailData,
} from "../../api/generated";

export const READY_PLAN_ID = "01912345-6789-7abc-8def-012345678901";
export const BLOCKED_PLAN_ID = "01912345-6789-7abc-8def-012345678902";
export const HISTORIC_PLAN_ID = "01912345-6789-7abc-8def-012345678903";
export const FIXTURE_LIBRARY_ID = "01912345-6789-7abc-8def-0123456789ab";
export const OPAQUE_PLAN_CURSOR = "fixture-plan-cursor-next";
export const OPAQUE_ACTION_CURSOR = "fixture-action-cursor-next";
export const OPAQUE_GROUP_CURSOR = "fixture-group-cursor-next";

const readyPlanSummary = {
  counts: {
    applied: { move: 0, refresh_metadata: 0, skip: 0 },
    blocked: { move: 1, refresh_metadata: 0, skip: 0 },
    failed: { move: 0, refresh_metadata: 0, skip: 0 },
    planned: { move: 1, refresh_metadata: 1, skip: 1 },
  },
  total: 4,
} as const;

const blockedOnlySummary = {
  counts: {
    applied: { move: 0, refresh_metadata: 0, skip: 0 },
    blocked: { move: 2, refresh_metadata: 0, skip: 0 },
    failed: { move: 0, refresh_metadata: 0, skip: 0 },
    planned: { move: 0, refresh_metadata: 0, skip: 0 },
  },
  total: 2,
} as const;

export const readyPlanMixedActions = {
  created_at: "2026-07-13T00:00:00Z",
  library_id: FIXTURE_LIBRARY_ID,
  plan_id: READY_PLAN_ID,
  plan_type: "refresh",
  status: "ready",
  summary: readyPlanSummary,
} as const;

export const blockedOnlyPlan = {
  created_at: "2026-07-12T00:00:00Z",
  library_id: FIXTURE_LIBRARY_ID,
  plan_id: BLOCKED_PLAN_ID,
  plan_type: "organize",
  status: "ready",
  summary: blockedOnlySummary,
} as const;

export const planListFirstPage = {
  data: {
    items: [readyPlanMixedActions, blockedOnlyPlan],
    page: {
      limit: 100,
      next_cursor: OPAQUE_PLAN_CURSOR,
      total: 3,
    },
  },
  errors: [],
} satisfies ApiEnvelopePaginatedDataPlanSummary;

export const planListSecondPage = {
  data: {
    items: [
      {
        created_at: "2026-07-11T00:00:00Z",
        library_id: FIXTURE_LIBRARY_ID,
        plan_id: HISTORIC_PLAN_ID,
        plan_type: "add",
        status: "applied",
        summary: {
          counts: {
            applied: { move: 1, refresh_metadata: 0, skip: 0 },
            blocked: { move: 0, refresh_metadata: 0, skip: 0 },
            failed: { move: 0, refresh_metadata: 0, skip: 0 },
            planned: { move: 0, refresh_metadata: 0, skip: 0 },
          },
          total: 1,
        },
      },
    ],
    page: {
      limit: 100,
      next_cursor: null,
      total: 3,
    },
  },
  errors: [],
} satisfies ApiEnvelopePaginatedDataPlanSummary;

export const exactReadyPlanPage = {
  data: {
    items: [readyPlanMixedActions],
    page: {
      limit: 100,
      next_cursor: null,
      total: 1,
    },
  },
  errors: [],
} satisfies ApiEnvelopePaginatedDataPlanSummary;

export const readyPlanDetail = {
  data: {
    active_operation_id: null,
    capabilities: {
      can_apply: true,
      can_cancel: true,
      can_recreate: true,
      disabled_reasons: [],
    },
    plan: {
      config_hash: "fixture-config-hash",
      created_at: readyPlanMixedActions.created_at,
      library_id: readyPlanMixedActions.library_id,
      library_root_at_plan: "/music/library",
      plan_id: readyPlanMixedActions.plan_id,
      plan_type: readyPlanMixedActions.plan_type,
      status: readyPlanMixedActions.status,
    },
    summary: readyPlanSummary,
  },
  errors: [],
} satisfies ApiEnvelopePlanDetailData;

export const exactBlockedPlanPage = {
  data: {
    items: [blockedOnlyPlan],
    page: {
      limit: 100,
      next_cursor: null,
      total: 1,
    },
  },
  errors: [],
} satisfies ApiEnvelopePaginatedDataPlanSummary;

export const emptyPlanPage = {
  data: {
    items: [],
    page: {
      limit: 100,
      next_cursor: null,
      total: 0,
    },
  },
  errors: [],
} satisfies ApiEnvelopePaginatedDataPlanSummary;

export const readyPlanActionsFirstPage = {
  data: {
    items: [
      {
        action_id: "01912345-6789-7abc-8def-012345678911",
        action_type: "move",
        content_hash_at_plan: "fixture-content-hash-a",
        library_id: FIXTURE_LIBRARY_ID,
        metadata_hash_at_plan: "fixture-metadata-hash-a",
        plan_id: READY_PLAN_ID,
        reason: null,
        sort_order: 0,
        source_path: "Incoming/Artist/Arrival.flac",
        status: "planned",
        target_path: "Artist/Album/01 Arrival.flac",
        track_id: null,
      },
      {
        action_id: "01912345-6789-7abc-8def-012345678912",
        action_type: "skip",
        content_hash_at_plan: "fixture-content-hash-b",
        library_id: FIXTURE_LIBRARY_ID,
        metadata_hash_at_plan: "fixture-metadata-hash-b",
        plan_id: READY_PLAN_ID,
        reason: "duplicate_hash",
        sort_order: 1,
        source_path: "Incoming/Artist/Duplicate.flac",
        status: "planned",
        target_path: null,
        track_id: "01912345-6789-7abc-8def-012345678921",
      },
    ],
    page: {
      limit: 100,
      next_cursor: OPAQUE_ACTION_CURSOR,
      total: 4,
    },
  },
  errors: [],
} satisfies ApiEnvelopePaginatedDataPlanActionResource;

export const readyPlanActionsSecondPage = {
  data: {
    items: [
      {
        action_id: "01912345-6789-7abc-8def-012345678913",
        action_type: "refresh_metadata",
        content_hash_at_plan: null,
        library_id: FIXTURE_LIBRARY_ID,
        metadata_hash_at_plan: "fixture-metadata-hash-c",
        plan_id: READY_PLAN_ID,
        reason: null,
        sort_order: 2,
        source_path: "Artist/Album/02 Metadata.flac",
        status: "planned",
        target_path: "Artist/Album/02 Metadata.flac",
        track_id: "01912345-6789-7abc-8def-012345678922",
      },
      {
        action_id: "01912345-6789-7abc-8def-012345678914",
        action_type: "move",
        content_hash_at_plan: "fixture-content-hash-d",
        library_id: FIXTURE_LIBRARY_ID,
        metadata_hash_at_plan: "fixture-metadata-hash-d",
        plan_id: READY_PLAN_ID,
        reason: "target_exists",
        sort_order: 3,
        source_path: "Incoming/Artist/Blocked.flac",
        status: "blocked",
        target_path: "Artist/Album/03 Blocked.flac",
        track_id: null,
      },
    ],
    page: {
      limit: 100,
      next_cursor: null,
      total: 4,
    },
  },
  errors: [],
} satisfies ApiEnvelopePaginatedDataPlanActionResource;

export const readyPlanFacets = {
  data: {
    facets: {
      action_type: [
        { count: 2, value: "move" },
        { count: 1, value: "skip" },
        { count: 1, value: "refresh_metadata" },
      ],
      reason: [
        { count: 1, value: "duplicate_hash" },
        { count: 1, value: "target_exists" },
      ],
      status: [
        { count: 3, value: "planned" },
        { count: 1, value: "blocked" },
      ],
    },
    target_collisions: 1,
    total: 4,
  },
  errors: [],
} satisfies ApiEnvelopePlanActionFacetsData;

export const readyPlanGroupsFirstPage = {
  data: {
    group_by: "status",
    items: [
      {
        blocked_count: 0,
        count: 3,
        key: "fixture-group-planned",
        label: "Planned",
        top_reason: "duplicate_hash",
      },
      {
        blocked_count: 1,
        count: 1,
        key: "fixture-group-blocked",
        label: "Blocked",
        top_reason: "target_exists",
      },
    ],
    page: {
      limit: 100,
      next_cursor: OPAQUE_GROUP_CURSOR,
      total: 3,
    },
  },
  errors: [],
} satisfies ApiEnvelopePlanActionGroupsData;

export const readyPlanGroupsSecondPage = {
  data: {
    group_by: "status",
    items: [
      {
        blocked_count: 0,
        count: 0,
        key: "fixture-group-applied",
        label: "Applied",
        top_reason: null,
      },
    ],
    page: {
      limit: 100,
      next_cursor: null,
      total: 3,
    },
  },
  errors: [],
} satisfies ApiEnvelopePlanActionGroupsData;
