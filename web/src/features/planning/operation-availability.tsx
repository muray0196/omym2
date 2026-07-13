/**
 * Summary: Presents backend-owned planning availability and disabled reasons.
 * Why: Prevents route forms from inferring mutation permission from entity status.
 */
import type { BootstrapData } from "../../api/generated";
import { planningCopy } from "./planning-copy";
import styles from "./planning.module.css";

type OperationStartCapability = "can_start_operations" | "can_start_organize";

export function OperationAvailability({
  bootstrap,
  capability = "can_start_operations",
}: {
  bootstrap: BootstrapData | null;
  capability?: OperationStartCapability;
}) {
  if (bootstrap?.runtime_capabilities[capability]) return null;

  const capabilityField = `runtime_capabilities.${capability}`;
  const diagnostics =
    bootstrap?.runtime_capabilities.disabled_reasons.filter(
      (diagnostic) => diagnostic.field === capabilityField,
    ) ?? [];
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
