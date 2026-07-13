/**
 * Summary: Defines the lazy Plan detail inspection route.
 * Why: Keeps recorded action review outside the initial application bundle.
 */
import { PlanDetail } from "../../features/plans/plan-detail";

export function Component() {
  return <PlanDetail />;
}
