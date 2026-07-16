/**
 * Summary: Tests adaptive Operation polling and connectivity presentation.
 * Why: Keeps retained work observable without resending its mutation.
 */
import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { useState } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ApiEnvelopeOperationResource } from "../../api/generated";
import { createQueryClient } from "../../app/query-client";
import { queuedOperation } from "../../test/fixtures/operations";
import { server } from "../../test/server";
import { LiveAnnouncementProvider } from "../../ui/primitives/live-region";
import {
  operationStatusIcon,
  operationStatusLabel,
  operationStatusTone,
} from "./operation-catalog";
import { OperationStatus } from "./operation-status";

afterEach(() => vi.useRealTimers());

describe("OperationStatus", () => {
  it("maps known statuses to explicit presentation values", () => {
    expect(operationStatusLabel("succeeded")).toBe("Completed");
    expect(operationStatusTone("succeeded")).toBe("success");
    expect(operationStatusIcon("succeeded")).toBe("check");
  });

  it("renders known Operation kind and result-kind evidence", () => {
    const { container } = render(
      <QueryClientProvider client={createQueryClient()}>
        <OperationStatus
          initialOperation={completedOperation.data}
          policy={pollingPolicy}
          resultAction={() => <span>Terminal destination</span>}
        />
      </QueryClientProvider>,
    );

    const kind = container.querySelector('[data-operation-kind="add_plan"]');
    expect(kind).toHaveTextContent("Create Add Plan");
    expect(kind).toHaveTextContent(
      "Scans a selected source and records proposed additions for review.",
    );
    expect(kind?.querySelector("svg")).not.toBeNull();

    const result = container.querySelector(
      '[data-operation-result-kind="plan_created"]',
    );
    expect(result).toHaveTextContent("Plan created");
    expect(result).toHaveTextContent(
      "A persisted Plan is available for inspection and review.",
    );
    expect(result).toHaveTextContent("Terminal destination");
    expect(result?.querySelector("svg")).not.toBeNull();
  });

  it("backs off unchanged status and recovers after connectivity loss", async () => {
    vi.useFakeTimers();
    let polls = 0;
    server.use(
      http.get("*/api/operations/:operationId", () => {
        polls += 1;
        if (polls === 1) return HttpResponse.error();
        if (polls === 2) return HttpResponse.json(activeOperation);
        return HttpResponse.json(completedOperation);
      }),
    );
    const queued = queuedOperation().data;
    render(
      <QueryClientProvider client={createQueryClient()}>
        <OperationStatus
          initialOperation={queued}
          policy={pollingPolicy}
          resultAction={() => <span>Terminal destination</span>}
        />
      </QueryClientProvider>,
    );

    await act(() => vi.advanceTimersByTimeAsync(pollingPolicy.initial_ms));
    expect(screen.getAllByText(/Connection lost/i)).not.toHaveLength(0);
    expect(polls).toBe(1);

    await act(() =>
      vi.advanceTimersByTimeAsync(
        pollingPolicy.initial_ms * pollingPolicy.backoff_factor,
      ),
    );
    expect(polls).toBe(2);
    expect(screen.queryByText(/Connection lost/i)).not.toBeInTheDocument();
    expect(screen.getAllByText("Running")).not.toHaveLength(0);

    await act(() => vi.advanceTimersByTimeAsync(pollingPolicy.initial_ms));
    expect(polls).toBe(3);
    expect(screen.getByText("Terminal destination")).toBeVisible();
  });

  it("presents terminal error remediation without executing its command", () => {
    render(
      <MemoryRouter>
        <QueryClientProvider client={createQueryClient()}>
          <OperationStatus
            initialOperation={interruptedOperation.data}
            policy={pollingPolicy}
            resultAction={() => null}
          />
        </QueryClientProvider>
      </MemoryRouter>,
    );

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Inspect the interrupted Run.",
    );
    expect(screen.getByText("omym2 history")).toBeVisible();
    expect(screen.getByRole("link", { name: "Open Run" })).toHaveAttribute(
      "href",
      "/history/fixture-run",
    );
  });

  it("keeps the completion announcement after the operation route unmounts", async () => {
    function NavigatingOperation() {
      const [operationVisible, setOperationVisible] = useState(true);
      return (
        <LiveAnnouncementProvider>
          {operationVisible ? (
            <OperationStatus
              initialOperation={completedOperation.data}
              onSucceeded={() => setOperationVisible(false)}
              policy={pollingPolicy}
              resultAction={() => null}
            />
          ) : (
            <p>Destination route</p>
          )}
        </LiveAnnouncementProvider>
      );
    }

    render(
      <QueryClientProvider client={createQueryClient()}>
        <NavigatingOperation />
      </QueryClientProvider>,
    );

    await waitFor(() =>
      expect(screen.getByText("Destination route")).toBeVisible(),
    );
    expect(
      screen.getByText("Plan created. Opening Plan review."),
    ).toBeInTheDocument();
  });
});

const pollingPolicy = {
  initial_ms: 10,
  backoff_factor: 2,
  max_ms: 40,
} as const;

const activeOperation = {
  data: {
    completed_at: null,
    error: null,
    kind: "add_plan",
    library_id: "018f0000-0000-7000-8000-000000000001",
    operation_id: "018f0000-0000-7000-8000-000000000020",
    plan_id: null,
    requested_at: "2026-07-13T00:00:00Z",
    result: null,
    run_id: null,
    started_at: "2026-07-13T00:00:01Z",
    status: "running",
  },
  errors: [],
} satisfies ApiEnvelopeOperationResource;

const completedOperation = {
  data: {
    ...activeOperation.data,
    completed_at: "2026-07-13T00:00:02Z",
    result: {
      kind: "plan_created",
      plan_id: "018f0000-0000-7000-8000-000000000021",
    },
    status: "succeeded",
  },
  errors: [],
} satisfies ApiEnvelopeOperationResource;

const interruptedOperation = {
  data: {
    ...activeOperation.data,
    completed_at: "2026-07-13T00:00:02Z",
    error: {
      code: "operation_interrupted",
      message: "Inspect the interrupted Run.",
      remediation: {
        command: "omym2 history",
        label: "Open Run",
        route: "/history/fixture-run",
      },
      retryable: false,
    },
    result: null,
    status: "interrupted",
  },
  errors: [],
} satisfies ApiEnvelopeOperationResource;
