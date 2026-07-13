/**
 * Summary: Defines the lazy Organize planning route boundary.
 * Why: Keeps unavailable planning mutations out of the M2 inspection console.
 */
import { PlaceholderRoute } from "../placeholder-route";
import { routeCopy } from "../route-copy";

export function Component() {
  return <PlaceholderRoute {...routeCopy.organizePlan} />;
}
