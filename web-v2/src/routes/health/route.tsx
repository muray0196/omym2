/**
 * Summary: Defines the lazy Health route boundary.
 * Why: Keeps persisted Check presentation separate from filesystem execution.
 */
import { PlaceholderRoute } from "../placeholder-route";
import { routeCopy } from "../route-copy";

export function Component() {
  return <PlaceholderRoute {...routeCopy.health} />;
}
