/**
 * Summary: Detects whether a keyboard event originated in an editable control.
 * Why: Prevents single-character shortcuts from disrupting typing or assistive technology.
 */
export function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }

  return (
    target.isContentEditable ||
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement
  );
}
