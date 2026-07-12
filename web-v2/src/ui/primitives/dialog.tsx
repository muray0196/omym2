/**
 * Summary: Wraps the native dialog element with explicit focus restoration.
 * Why: Centralizes modal semantics, Escape handling, and CSP-safe presentation.
 */
import {
  useEffect,
  useId,
  useRef,
  type ReactNode,
  type RefObject,
} from "react";

import { Icon } from "../icon";
import { Button } from "./button";
import styles from "./dialog.module.css";

type DialogProps = {
  children: ReactNode;
  closeLabel: string;
  initialFocusRef?: RefObject<HTMLElement | null>;
  label: string;
  onRequestClose: () => void;
  open: boolean;
  returnFocusRef: RefObject<HTMLElement | null>;
  variant?: "modal" | "drawer";
};

export function Dialog({
  children,
  closeLabel,
  initialFocusRef,
  label,
  onRequestClose,
  open,
  returnFocusRef,
  variant = "modal",
}: DialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const wasOpenRef = useRef(false);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog === null) {
      return;
    }

    if (open && !dialog.open) {
      dialog.showModal();
      initialFocusRef?.current?.focus();
      wasOpenRef.current = true;
      return;
    }

    if (!open && dialog.open) {
      dialog.close();
    }

    if (!open && wasOpenRef.current) {
      wasOpenRef.current = false;
      returnFocusRef.current?.focus();
    }
  }, [initialFocusRef, open, returnFocusRef]);

  return (
    <dialog
      aria-labelledby={titleId}
      className={`${styles.dialog} ${variant === "drawer" ? styles.drawer : ""}`}
      onCancel={(event) => {
        event.preventDefault();
        onRequestClose();
      }}
      onClose={onRequestClose}
      ref={dialogRef}
    >
      <section className={styles.surface}>
        <header className={styles.header}>
          <h2 className={styles.title} id={titleId}>
            {label}
          </h2>
          <Button
            aria-label={closeLabel}
            iconOnly
            onClick={onRequestClose}
            variant="quiet"
          >
            <Icon name="close" />
          </Button>
        </header>
        <div className={styles.body}>{children}</div>
      </section>
    </dialog>
  );
}
