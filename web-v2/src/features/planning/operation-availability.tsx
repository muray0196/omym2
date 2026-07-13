/**
 * Summary: Presents backend-owned planning availability and disabled reasons.
 * Why: Prevents route forms from inferring mutation permission from entity status.
 */
import type { BootstrapData } from "../../api/generated";
import { planningCopy } from "./planning-copy";
import styles from "./planning.module.css";

export function OperationAvailability({
  bootstrap,
}: {
  bootstrap: BootstrapData | null;
}) {
  if (bootstrap?.runtime_capabilities.can_start_operations) return null;

  const diagnostics = bootstrap?.runtime_capabilities.disabled_reasons ?? [];
  return (
    <div className={styles.diagnostics} role="status">
      <strong>
        {bootstrap === null ? planningCopy.noBootstrap : planningCopy.disabled}
      </strong>
      {diagnostics.length > 0 ? (
        <ul>
          {diagnostics.map((diagnostic) => (
            <li key={`${diagnostic.code}:${diagnostic.field ?? ""}`}>
              {diagnostic.message}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
