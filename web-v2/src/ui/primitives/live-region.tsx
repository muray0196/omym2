/**
 * Summary: Provides a stable polite announcement region for asynchronous updates.
 * Why: Ensures later operation progress can be conveyed without moving focus.
 */
import type { ReactNode } from "react";

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
