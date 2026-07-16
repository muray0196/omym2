/**
 * Summary: Verifies complete Operation kind and result-kind presentation catalogs.
 * Why: Keeps every bundled value explicit and exhaustively typed.
 */
import { describe, expect, it } from "vitest";

import type { OperationKind, OperationStatus } from "../../api/generated";
import {
  operationKindPresentation,
  operationResultKindPresentation,
  operationStatusPresentation,
  type OperationCatalogPresentation,
  type OperationResultKind,
} from "./operation-catalog";

const EXPECTED_KIND_PRESENTATIONS = {
  add_plan: {
    icon: "info",
    label: "Create Add Plan",
    meaning:
      "Scans a selected source and records proposed additions for review.",
    tone: "info",
  },
  organize_plan: {
    icon: "info",
    label: "Create Organize Plan",
    meaning:
      "Scans a Library root and records registration or organization work for review.",
    tone: "info",
  },
  refresh_plan: {
    icon: "info",
    label: "Create Refresh Plan",
    meaning:
      "Reads current file evidence and records proposed metadata refresh work for review.",
    tone: "info",
  },
  check: {
    icon: "info",
    label: "Run Check",
    meaning:
      "Inspects Library consistency and records persisted Health findings.",
    tone: "info",
  },
  apply_plan: {
    icon: "info",
    label: "Apply Plan",
    meaning:
      "Applies the recorded actions of an accepted Plan and records Run evidence.",
    tone: "info",
  },
  undo_plan: {
    icon: "info",
    label: "Create Undo Plan",
    meaning: "Creates an Undo Plan from an eligible Run for review.",
    tone: "info",
  },
} as const satisfies Record<OperationKind, OperationCatalogPresentation>;

const EXPECTED_RESULT_PRESENTATIONS = {
  plan_created: {
    icon: "check",
    label: "Plan created",
    meaning: "A persisted Plan is available for inspection and review.",
    tone: "success",
  },
  registered_without_plan: {
    icon: "check",
    label: "Registered without a Plan",
    meaning:
      "The Library registration was persisted without proposed file changes.",
    tone: "success",
  },
  check_completed: {
    icon: "check",
    label: "Check completed",
    meaning: "Persisted Health findings are available for inspection.",
    tone: "success",
  },
  run_completed: {
    icon: "check",
    label: "Run completed",
    meaning: "Recorded Run evidence is available in History.",
    tone: "success",
  },
} as const satisfies Record<OperationResultKind, OperationCatalogPresentation>;

const EXPECTED_STATUS_PRESENTATIONS = {
  queued: {
    icon: "info",
    label: "Queued",
    meaning: "The durable Operation was accepted and is waiting to run.",
    tone: "info",
  },
  running: {
    icon: "info",
    label: "Running",
    meaning: "The durable Operation is processing work.",
    tone: "info",
  },
  succeeded: {
    icon: "check",
    label: "Completed",
    meaning: "The durable Operation completed with a persisted result.",
    tone: "success",
  },
  failed: {
    icon: "warning",
    label: "Failed",
    meaning: "The durable Operation reached a terminal failed state.",
    tone: "danger",
  },
  interrupted: {
    icon: "warning",
    label: "Interrupted",
    meaning: "The worker stopped before completion could be confirmed.",
    tone: "warning",
  },
} as const satisfies Record<OperationStatus, OperationCatalogPresentation>;

describe("Operation catalog", () => {
  it.each(
    Object.entries(EXPECTED_KIND_PRESENTATIONS) as [
      OperationKind,
      OperationCatalogPresentation,
    ][],
  )("maps the known %s Operation kind", (value, expected) => {
    expect(operationKindPresentation(value)).toEqual(expected);
  });

  it.each(
    Object.entries(EXPECTED_RESULT_PRESENTATIONS) as [
      OperationResultKind,
      OperationCatalogPresentation,
    ][],
  )("maps the known %s Operation result kind", (value, expected) => {
    expect(operationResultKindPresentation(value)).toEqual(expected);
  });

  it.each(
    Object.entries(EXPECTED_STATUS_PRESENTATIONS) as [
      OperationStatus,
      OperationCatalogPresentation,
    ][],
  )("maps the known %s Operation status", (value, expected) => {
    expect(operationStatusPresentation(value)).toEqual(expected);
  });
});
