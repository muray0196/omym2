/**
 * Summary: Defines the lazy Add planning route boundary.
 * Why: Keeps unavailable planning mutations out of the M1 foundation.
 */
import { PlaceholderRoute } from "../placeholder-route";
import { routeCopy } from "../route-copy";

export function Component() {
  return <PlaceholderRoute {...routeCopy.addPlan} />;
}
