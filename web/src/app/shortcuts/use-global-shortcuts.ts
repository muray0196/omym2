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
      if (event.isComposing) {
        return;
      }

      const key = event.key.toLowerCase();

      if (
        (event.metaKey || event.ctrlKey) &&
        !event.altKey &&
        !event.shiftKey &&
        !event.repeat &&
        key === "k"
      ) {
        event.preventDefault();
        handlersRef.current.onCommandCenter();
        return;
      }

      if (
        (event.metaKey || event.ctrlKey) &&
        !event.altKey &&
        !event.shiftKey &&
        !event.repeat &&
        event.key === "Enter"
      ) {
        const primaryAction = currentPrimaryAction();
        if (primaryAction !== null) {
          event.preventDefault();
          primaryAction.click();
        }
        return;
      }

      if (
        (event.key === "ArrowDown" || event.key === "ArrowUp") &&
        !event.metaKey &&
        !event.ctrlKey &&
        !event.altKey &&
        !event.shiftKey
      ) {
        const editableTarget = isEditableTarget(event.target);
        const listSearchTarget =
          event.target instanceof HTMLElement &&
          event.target.matches("[data-list-search]");
        if (!editableTarget || listSearchTarget) {
          const items = selectableListItems();
          if (items.length > 0) {
            const currentIndex = items.findIndex(
              (item) => item === document.activeElement,
            );
            const nextIndex = nextListIndex(
              currentIndex,
              items.length,
              event.key === "ArrowDown",
            );
            event.preventDefault();
            items[nextIndex]?.focus();
            return;
          }
        }
      }

      if (
        isEditableTarget(event.target) ||
        event.metaKey ||
        event.ctrlKey ||
        event.altKey
      ) {
        return;
      }

      if (event.key === "Escape") {
        if (document.querySelector("dialog[open]") !== null) {
          return;
        }
        const back = document.querySelector<HTMLElement>("[data-detail-back]");
        if (back !== null) {
          event.preventDefault();
          back.click();
        }
        return;
      }

      if (event.key === "?") {
        event.preventDefault();
        handlersRef.current.onShortcutHelp();
        return;
      }

      if (event.key === "/") {
        const search =
          interactionScope().querySelector<HTMLElement>("[data-list-search]");
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

function currentPrimaryAction() {
  const openDialog = document.querySelector<HTMLDialogElement>("dialog[open]");
  const selector =
    '[data-primary-action]:not(:disabled):not([aria-disabled="true"])';
  if (openDialog !== null) {
    return openDialog.querySelector<HTMLElement>(selector);
  }
  const scope = interactionScope();
  return (
    Array.from(scope.querySelectorAll<HTMLElement>(selector)).find(
      (candidate) => candidate.closest("dialog") === null,
    ) ?? null
  );
}

function selectableListItems() {
  return Array.from(
    interactionScope().querySelectorAll<HTMLElement>(
      '[data-list-item]:not([aria-disabled="true"])',
    ),
  );
}

function interactionScope(): ParentNode {
  return (
    document.querySelector<HTMLDialogElement>("dialog[open]") ??
    document.querySelector("main") ??
    document
  );
}

function nextListIndex(
  currentIndex: number,
  itemCount: number,
  movingForward: boolean,
) {
  if (currentIndex === -1) {
    return movingForward ? 0 : itemCount - 1;
  }
  return movingForward
    ? (currentIndex + 1) % itemCount
    : (currentIndex - 1 + itemCount) % itemCount;
}
