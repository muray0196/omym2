/**
 * Summary: Defines deterministic durable Operation fixtures.
 * Why: Keeps mutation and polling tests synchronized with generated types.
 */
import type {
  ApiEnvelopeOperationRef,
  ApiEnvelopeOperationResource,
  OperationKind,
} from "../../api/generated";

export const OPERATION_ID = "018f0000-0000-7000-8000-000000000020";
export const CREATED_PLAN_ID = "018f0000-0000-7000-8000-000000000021";
export const COMPLETED_RUN_ID = "018f0000-0000-7000-8000-000000000023";

export function queuedOperation(kind: OperationKind = "add_plan") {
  return {
    data: {
      kind,
      operation_id: OPERATION_ID,
      poll_after_ms: 17,
      status: "queued",
      status_url: `/api/operations/${OPERATION_ID}`,
    },
    errors: [],
  } satisfies ApiEnvelopeOperationRef;
}

export function completedPlanOperation(kind: OperationKind = "add_plan") {
  return {
    data: {
      completed_at: "2026-07-13T00:00:02Z",
      error: null,
      kind,
      library_id: "018f0000-0000-7000-8000-000000000001",
      operation_id: OPERATION_ID,
      plan_id: CREATED_PLAN_ID,
      progress: {
        completed_units: 3,
        message: "Plan persisted.",
        stage_code: "future_planning_stage",
        total_units: 3,
      },
      requested_at: "2026-07-13T00:00:00Z",
      result: { kind: "plan_created", plan_id: CREATED_PLAN_ID },
      run_id: null,
      started_at: "2026-07-13T00:00:01Z",
      status: "succeeded",
    },
    errors: [],
  } satisfies ApiEnvelopeOperationResource;
}

export const completedCheckOperation = {
  data: {
    completed_at: "2026-07-13T00:00:02Z",
    error: null,
    kind: "check",
    library_id: "018f0000-0000-7000-8000-000000000001",
    operation_id: OPERATION_ID,
    plan_id: null,
    progress: {
      completed_units: 5,
      message: "Findings saved.",
      stage_code: "persisting_findings",
      total_units: 5,
    },
    requested_at: "2026-07-13T00:00:00Z",
    result: {
      check_run_ids: ["018f0000-0000-7000-8000-000000000022"],
      issue_count: 2,
      kind: "check_completed",
    },
    run_id: null,
    started_at: "2026-07-13T00:00:01Z",
    status: "succeeded",
  },
  errors: [],
} satisfies ApiEnvelopeOperationResource;

export const completedRunOperation = {
  data: {
    completed_at: "2026-07-13T00:00:02Z",
    error: null,
    kind: "apply_plan",
    library_id: "018f0000-0000-7000-8000-000000000001",
    operation_id: OPERATION_ID,
    plan_id: CREATED_PLAN_ID,
    progress: {
      completed_units: 3,
      message: "Run evidence persisted.",
      stage_code: "apply_recorded_actions",
      total_units: 3,
    },
    requested_at: "2026-07-13T00:00:00Z",
    result: { kind: "run_completed", run_id: COMPLETED_RUN_ID },
    run_id: COMPLETED_RUN_ID,
    started_at: "2026-07-13T00:00:01Z",
    status: "succeeded",
  },
  errors: [],
} satisfies ApiEnvelopeOperationResource;
