/**
 * Summary: Marks route headings as deterministic navigation focus targets.
 * Why: Gives keyboard and screen-reader users clear context after route changes.
 */
import { useEffect, useRef, type ReactNode } from "react";

export function RouteHeading({ children }: { children: ReactNode }) {
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  return (
    <h1 data-route-heading ref={headingRef} tabIndex={-1}>
      {children}
    </h1>
  );
}
