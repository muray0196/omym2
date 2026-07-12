/**
 * Summary: Defines the lazy Run detail route boundary.
 * Why: Keeps Undo eligibility backend-authoritative and unavailable before its milestone.
 */
import { PlaceholderRoute } from "../placeholder-route";
import { routeCopy } from "../route-copy";

export function Component() {
  return <PlaceholderRoute {...routeCopy.runDetail} />;
}
