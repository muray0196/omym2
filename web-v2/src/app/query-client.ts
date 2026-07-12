/**
 * Summary: Owns the single TanStack Query cache for browser server state.
 * Why: Deduplicates reads and prevents unsafe automatic mutation retries.
 */
import { QueryClient } from "@tanstack/react-query";

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        refetchOnWindowFocus: false,
        retry: false,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

export const queryClient = createQueryClient();
