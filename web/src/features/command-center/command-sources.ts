/**
 * Summary: Builds ordered Command Center actions, records, and navigation results.
 * Why: Makes the keyboard palette useful for current persisted state without inferring mutations.
 */
import type {
  PlanSummary,
  RunHeader,
  TrackResource,
} from "../../api/generated";
import { navigationItems } from "../../app/shell/shell-copy";
import { runStatusLabel } from "../history/history-catalog";
import { planStatusLabel } from "../plans/plan-catalog";

export type CommandKind =
  "recommended" | "command" | "plan" | "run" | "track" | "navigation";

export type CommandItem = {
  id: string;
  kind: CommandKind;
  label: string;
  searchText: string;
  to: string;
};

const recommendedCommands: readonly CommandItem[] = [
  {
    id: "recommended:add",
    kind: "recommended",
    label: "Add music",
    searchText: "add music import create plan recommended",
    to: "/plans/new/add",
  },
];

const purposeCommands: readonly CommandItem[] = [
  {
    id: "command:create-plan",
    kind: "command",
    label: "Create a Plan",
    searchText: "create plan add organize refresh command",
    to: "/plans",
  },
  {
    id: "command:inspect-health",
    kind: "command",
    label: "Inspect Health",
    searchText: "inspect health check issues command",
    to: "/health",
  },
];

export const navigationCommands: readonly CommandItem[] = navigationItems.map(
  (item) => ({
    id: `navigation:${item.to}`,
    kind: "navigation",
    label: item.label,
    searchText: `${item.label} navigate open`,
    to: item.to,
  }),
);

export function buildCommands({
  plans = [],
  runs = [],
  tracks = [],
}: {
  plans?: PlanSummary[];
  runs?: RunHeader[];
  tracks?: TrackResource[];
} = {}): readonly CommandItem[] {
  return [
    ...recommendedCommands,
    ...purposeCommands,
    ...plans.map((plan) => ({
      id: `plan:${plan.plan_id}`,
      kind: "plan" as const,
      label: `Plan ${shortId(plan.plan_id)} · ${planStatusLabel(plan.status)}`,
      searchText: `${plan.plan_id} ${plan.library_id} ${plan.plan_type} ${plan.status} plan`,
      to: `/plans/${plan.plan_id}`,
    })),
    ...runs.map((run) => ({
      id: `run:${run.run_id}`,
      kind: "run" as const,
      label: `Run ${shortId(run.run_id)} · ${runStatusLabel(run.status)}`,
      searchText: `${run.run_id} ${run.plan_id} ${run.library_id} ${run.status} run history`,
      to: `/history/${run.run_id}`,
    })),
    ...tracks.map((track) => ({
      id: `track:${track.track_id}`,
      kind: "track" as const,
      label: track.metadata.title ?? track.current_path,
      searchText: `${track.track_id} ${track.current_path} ${track.metadata.title ?? ""} ${track.metadata.artist ?? ""} track library`,
      to: `/library/${track.track_id}`,
    })),
    ...navigationCommands,
  ];
}

export function filterCommands(
  query: string,
  commands: readonly CommandItem[] = buildCommands(),
): readonly CommandItem[] {
  const normalizedQuery = query.trim().toLowerCase();
  if (normalizedQuery.length === 0) {
    return commands;
  }

  return commands.filter((item) =>
    item.searchText.toLowerCase().includes(normalizedQuery),
  );
}

function shortId(value: string) {
  return value.slice(0, 8);
}
