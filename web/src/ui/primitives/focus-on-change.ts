/**
 * Summary: Focuses an element ref whenever a given trigger value changes.
 * Why: Keeps mutation-failure summaries immediately discoverable without duplicating the ref/effect pair.
 */
import { useEffect, useRef } from "react";

export function useFocusOnChange<Element extends HTMLElement>(
  trigger: unknown,
) {
  const ref = useRef<Element>(null);

  useEffect(() => {
    ref.current?.focus();
  }, [trigger]);

  return ref;
}
