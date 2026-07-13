/**
 * Summary: Centralizes product-default-language copy for the application shell.
 * Why: Keeps navigation and shortcut wording consistent without adding localization machinery.
 */
import type { IconName } from "../../ui/icon";

export const shellCopy = {
  productName: "OMYM2",
  productDescription: "Local music operations",
  navigationLabel: "Primary navigation",
  openNavigation: "Open navigation",
  navigationTitle: "Navigation",
  closeNavigation: "Close navigation",
  commandCenter: "Command Center",
  commandShortcut: "Ctrl or Command plus K",
  shortcutHelp: "Keyboard shortcuts",
  shortcutHelpDescription: "Every shortcut has an equivalent visible control.",
  closeShortcutHelp: "Close keyboard shortcuts",
  skipToContent: "Skip to content",
  loadingCommandCenter: "Loading Command Center",
  footer: "Local only · Offline first · No telemetry",
  shortcuts: [
    ["Ctrl/Command + K", "Open Command Center"],
    ["↑ / ↓", "Move list selection"],
    ["Enter", "Open selected detail"],
    ["Ctrl/Command + Enter", "Invoke the current primary action"],
    ["Escape", "Close the top dialog or return to the list"],
    ["/", "Focus list search"],
    ["?", "Open keyboard shortcuts"],
  ],
} as const;

export const navigationItems = [
  { icon: "overview", label: "Overview", to: "/" },
  { icon: "plans", label: "Plans", to: "/plans" },
  { icon: "library", label: "Library", to: "/library" },
  { icon: "health", label: "Health", to: "/health" },
  { icon: "history", label: "History", to: "/history" },
  { icon: "settings", label: "Settings", to: "/settings" },
] as const satisfies readonly {
  icon: IconName;
  label: string;
  to: string;
}[];
