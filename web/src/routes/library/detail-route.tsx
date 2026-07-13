/**
 * Summary: Defines the lazy persisted Track detail route boundary.
 * Why: Keeps metadata and hash inspection outside the initial app-shell bundle.
 */
import { TrackDetail } from "../../features/library/track-detail";

export function Component() {
  return <TrackDetail />;
}
