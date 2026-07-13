/**
 * Summary: Defines the lazy Plans inspection list route.
 * Why: Keeps the read-only Plan catalog outside the initial application bundle.
 */
import { PlanList } from "../../features/plans/plan-list";

export function Component() {
  return <PlanList />;
}
