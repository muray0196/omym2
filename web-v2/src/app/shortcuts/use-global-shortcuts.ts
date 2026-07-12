/**
 * Summary: Installs the application-wide keyboard contract through one listener.
 * Why: Avoids duplicate subscriptions and suppresses unsafe editable-target shortcuts.
 */
import { useEffect, useRef } from "react";

import { isEditableTarget } from "./editable-target";

type GlobalShortcutHandlers = {
  onCommandCenter: () => void;
  onReady: () => void;
  onShortcutHelp: () => void;
};

export function useGlobalShortcuts(handlers: GlobalShortcutHandlers) {
  const handlersRef = useRef(handlers);

  useEffect(() => {
    handlersRef.current = handlers;
  }, [handlers]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const key = event.key.toLowerCase();

      if ((event.metaKey || event.ctrlKey) && key === "k") {
        event.preventDefault();
        handlersRef.current.onCommandCenter();
        return;
      }

      if (
        isEditableTarget(event.target) ||
        event.metaKey ||
        event.ctrlKey ||
        event.altKey
      ) {
        return;
      }

      if (event.key === "?") {
        event.preventDefault();
        handlersRef.current.onShortcutHelp();
        return;
      }

      if (event.key === "/") {
        const search =
          document.querySelector<HTMLElement>("[data-list-search]");
        if (search !== null) {
          event.preventDefault();
          search.focus();
        }
      }
    }

    window.addEventListener("keydown", onKeyDown);
    handlersRef.current.onReady();
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
}
