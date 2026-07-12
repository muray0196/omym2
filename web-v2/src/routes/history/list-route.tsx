/**
 * Summary: Defines the lazy History list route boundary.
 * Why: Reserves Run browsing for typed persisted evidence in M2.
 */
import { PlaceholderRoute } from "../placeholder-route";
import { routeCopy } from "../route-copy";

export function Component() {
  return <PlaceholderRoute {...routeCopy.history} />;
}
