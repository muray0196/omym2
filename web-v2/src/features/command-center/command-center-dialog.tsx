/**
 * Summary: Implements the lazy keyboard-first Command Center dialog.
 * Why: Makes navigation searchable while preserving focus and editable-target behavior.
 */
import {
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type RefObject,
} from "react";
import { useNavigate } from "react-router-dom";

import { Icon } from "../../ui/icon";
import { Dialog } from "../../ui/primitives/dialog";
import { commandCenterCopy } from "./command-center-copy";
import { filterCommands } from "./command-sources";
import styles from "./command-center.module.css";

type CommandCenterDialogProps = {
  onRequestClose: () => void;
  open: boolean;
  returnFocusRef: RefObject<HTMLElement | null>;
};

export function CommandCenterDialog({
  open,
  onRequestClose,
  returnFocusRef,
}: CommandCenterDialogProps) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listId = useId();
  const navigate = useNavigate();
  const results = filterCommands(query);
  const activeItem = results[activeIndex] ?? results[0];

  function openItem(index: number) {
    const item = results[index];
    if (item === undefined) {
      return;
    }
    returnFocusRef.current = null;
    onRequestClose();
    void navigate(item.to);
  }

  function onInputKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (results.length === 0) {
      return;
    }

    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((current) => (current + 1) % results.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex(
        (current) => (current - 1 + results.length) % results.length,
      );
    } else if (event.key === "Enter") {
      event.preventDefault();
      openItem(activeIndex);
    }
  }

  return (
    <Dialog
      closeLabel={commandCenterCopy.close}
      initialFocusRef={inputRef}
      label={commandCenterCopy.title}
      onRequestClose={onRequestClose}
      open={open}
      returnFocusRef={returnFocusRef}
    >
      <div className={styles.searchRow}>
        <Icon name="search" />
        <input
          aria-activedescendant={
            activeItem === undefined ? undefined : `${listId}-${activeItem.id}`
          }
          aria-controls={listId}
          aria-expanded="true"
          aria-label={commandCenterCopy.searchLabel}
          autoComplete="off"
          className={styles.search}
          name="command-search"
          onChange={(event) => {
            setQuery(event.currentTarget.value);
            setActiveIndex(0);
          }}
          onKeyDown={onInputKeyDown}
          placeholder={commandCenterCopy.searchPlaceholder}
          ref={inputRef}
          role="combobox"
          type="search"
          value={query}
        />
      </div>
      <p className={styles.instruction}>{commandCenterCopy.instruction}</p>
      {results.length === 0 ? (
        <p className={styles.empty}>{commandCenterCopy.empty}</p>
      ) : (
        <p className={styles.groupLabel}>{commandCenterCopy.navigationGroup}</p>
      )}
      <div
        aria-label={commandCenterCopy.resultsLabel}
        className={styles.results}
        id={listId}
        role="listbox"
      >
        {results.map((item, index) => (
          <button
            aria-selected={index === activeIndex}
            className={styles.option}
            id={`${listId}-${item.id}`}
            key={item.id}
            onClick={() => openItem(index)}
            onMouseEnter={() => setActiveIndex(index)}
            role="option"
            tabIndex={-1}
            type="button"
          >
            <span>{item.label}</span>
            <Icon name="arrow-right" />
          </button>
        ))}
      </div>
    </Dialog>
  );
}
