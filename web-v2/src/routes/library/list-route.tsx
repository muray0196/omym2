/**
 * Summary: Defines the lazy Library browsing route boundary.
 * Why: Freezes navigation without bypassing the future typed track API.
 */
import { PlaceholderRoute } from "../placeholder-route";
import { routeCopy } from "../route-copy";

export function Component() {
  return <PlaceholderRoute {...routeCopy.library} />;
}
