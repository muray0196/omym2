/**
 * Summary: Marks route headings as deterministic navigation focus targets.
 * Why: Gives keyboard and screen-reader users clear context after route changes.
 */
import { useEffect, useRef, type ReactNode } from "react";
import { useLocation } from "react-router-dom";

export function RouteHeading({ children }: { children: ReactNode }) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const { pathname } = useLocation();
  const routeTitle =
    typeof children === "string" || typeof children === "number"
      ? String(children)
      : null;

  useEffect(() => {
    headingRef.current?.focus();
  }, [pathname]);

  useEffect(() => {
    document.title = routeTitle === null ? "OMYM2" : `${routeTitle} · OMYM2`;
  }, [routeTitle]);

  return (
    <h1 data-route-heading ref={headingRef} tabIndex={-1}>
      {children}
    </h1>
  );
}
