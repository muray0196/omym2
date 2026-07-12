/**
 * Summary: Defines the lazy Plans list route boundary.
 * Why: Freezes the route without inventing inspection data before M2.
 */
import { PlaceholderRoute } from "../placeholder-route";
import { routeCopy } from "../route-copy";

export function Component() {
  return <PlaceholderRoute {...routeCopy.plans} />;
}
