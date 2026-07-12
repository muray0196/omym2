/**
 * Summary: Defines the lazy Plan review route boundary.
 * Why: Reserves backend-authoritative capability presentation for later integration.
 */
import { PlaceholderRoute } from "../placeholder-route";
import { routeCopy } from "../route-copy";

export function Component() {
  return <PlaceholderRoute {...routeCopy.planDetail} />;
}
