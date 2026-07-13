/**
 * Summary: Tests adaptive Operation polling and connectivity presentation.
 * Why: Keeps retained work observable without resending its mutation.
 */
import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ApiEnvelopeOperationResource } from "../../api/generated";
import { createQueryClient } from "../../app/query-client";
import { queuedOperation } from "../../test/fixtures/operations";
import { server } from "../../test/server";
import { OperationStatus } from "./operation-status";

afterEach(() => vi.useRealTimers());

describe("OperationStatus", () => {
  it("backs off unchanged progress and recovers after connectivity loss", async () => {
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
    expect(screen.getByText(/Working: server stage/)).toBeVisible();
    expect(screen.getByText("future_scan_stage")).toBeVisible();

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
    progress: {
      completed_units: 1,
      message: null,
      stage_code: "future_scan_stage",
      total_units: 3,
    },
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
    progress: {
      ...activeOperation.data.progress,
      completed_units: 3,
    },
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
    progress: {
      completed_units: null,
      message: null,
      stage_code: null,
      total_units: null,
    },
    result: null,
    status: "interrupted",
  },
  errors: [],
} satisfies ApiEnvelopeOperationResource;
