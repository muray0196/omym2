/**
 * Summary: Defines clean-room Command Center navigation results.
 * Why: Establishes stable ordering without fabricating unavailable backend entities.
 */
import { navigationItems } from "../../app/shell/shell-copy";

export type CommandItem = {
  id: string;
  kind: "navigation";
  label: string;
  searchText: string;
  to: string;
};

export const navigationCommands: readonly CommandItem[] = navigationItems.map(
  (item) => ({
    id: `navigation:${item.to}`,
    kind: "navigation",
    label: item.label,
    searchText: `${item.label} navigate open`,
    to: item.to,
  }),
);

export function filterCommands(query: string): readonly CommandItem[] {
  const normalizedQuery = query.trim().toLowerCase();
  if (normalizedQuery.length === 0) {
    return navigationCommands;
  }

  return navigationCommands.filter((item) =>
    item.searchText.toLowerCase().includes(normalizedQuery),
  );
}
