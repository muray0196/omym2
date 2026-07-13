/**
 * Summary: Provides a stable polite announcement region for asynchronous updates.
 * Why: Ensures later operation progress can be conveyed without moving focus.
 */
import { useCallback, useRef, useState, type ReactNode } from "react";

import { LiveAnnouncementContext } from "./live-announcement-context";
import { VisuallyHidden } from "./visually-hidden";

export function LiveRegion({ children }: { children: ReactNode }) {
  return (
    <VisuallyHidden>
      <span aria-atomic="true" aria-live="polite">
        {children}
      </span>
    </VisuallyHidden>
  );
}

type Announcement = {
  message: string;
  sequence: number;
};

export function LiveAnnouncementProvider({
  children,
}: {
  children: ReactNode;
}) {
  const sequenceRef = useRef(0);
  const [announcement, setAnnouncement] = useState<Announcement | null>(null);
  const announce = useCallback((message: string) => {
    sequenceRef.current += 1;
    setAnnouncement({ message, sequence: sequenceRef.current });
  }, []);

  return (
    <LiveAnnouncementContext.Provider value={announce}>
      {children}
      <LiveRegion>
        {announcement === null ? null : (
          <span key={announcement.sequence}>{announcement.message}</span>
        )}
      </LiveRegion>
    </LiveAnnouncementContext.Provider>
  );
}
