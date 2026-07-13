/**
 * Summary: Shares the shell-owned asynchronous announcement publisher.
 * Why: Lets transient operation routes publish into one persistent live region.
 */
import { createContext, useContext } from "react";

export const LiveAnnouncementContext = createContext<
  ((message: string) => void) | null
>(null);

export function useLiveAnnouncement() {
  return useContext(LiveAnnouncementContext);
}
