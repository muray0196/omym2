/**
 * Summary: Cancels a ready Plan with the sole contract-approved CSRF retry.
 * Why: Keeps synchronous cancellation safe without retrying conflicts, transport failures, or server failures.
 */
import type { QueryClient } from "@tanstack/react-query";

import { cancelPlan, type PlanDetailData } from "../../api/generated";
import { bootstrapQuery } from "../bootstrap/bootstrap-query";
import {
  ApiMutationError,
  OperationTransportError,
  OperationUnexpectedDataError,
} from "../operations/operation-start";

export async function cancelPlanSafely({
  csrfToken,
  planId,
  queryClient,
}: {
  csrfToken: string;
  planId: string;
  queryClient: QueryClient;
}): Promise<PlanDetailData> {
  const firstResponse = await sendCancellation(planId, csrfToken);
  if (!isCsrfInvalid(firstResponse)) {
    return planDetailOrThrow(firstResponse);
  }

  await queryClient.invalidateQueries({
    queryKey: bootstrapQuery.queryKey,
    refetchType: "none",
  });
  const refreshedBootstrap = await queryClient.fetchQuery(bootstrapQuery);
  const refreshedToken = refreshedBootstrap.data?.csrf_token;
  if (refreshedToken === undefined) {
    throw new OperationUnexpectedDataError();
  }

  return planDetailOrThrow(await sendCancellation(planId, refreshedToken));
}

function sendCancellation(planId: string, csrfToken: string) {
  return cancelPlan<false>({
    baseUrl: globalThis.location.origin,
    headers: { "X-OMYM2-CSRF-Token": csrfToken },
    path: { plan_id: planId },
  });
}

type CancelPlanResponse = Awaited<ReturnType<typeof sendCancellation>>;

function isCsrfInvalid(response: CancelPlanResponse) {
  return (
    response.response?.status === 403 &&
    response.error?.errors.some((error) => error.code === "csrf_invalid") ===
      true
  );
}

function planDetailOrThrow(response: CancelPlanResponse): PlanDetailData {
  if (response.error !== undefined) {
    if (response.response === undefined) {
      throw new OperationTransportError();
    }
    throw new ApiMutationError(
      response.error,
      response.response.status,
      "Plan cancellation returned a typed API failure.",
    );
  }
  const detail = response.data?.data;
  if (detail === null || detail === undefined) {
    throw new OperationUnexpectedDataError();
  }
  return detail;
}
