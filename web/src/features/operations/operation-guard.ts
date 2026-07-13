/**
 * Summary: Tracks whether one locally accepted durable Operation remains nonterminal.
 * Why: Prevents a second start from replacing the polling state of accepted work.
 */
import { useCallback, useState } from "react";

import { isActiveOperation } from "./operation-polling";
import type { OperationStartResult } from "./operation-start";

export function useAcceptedOperationGuard() {
  const [hasActiveOperation, setHasActiveOperation] = useState(false);
  const recordAcceptedOperation = useCallback(
    (operation: OperationStartResult) => {
      setHasActiveOperation(isActiveOperation(operation));
    },
    [],
  );
  const recordTerminalOperation = useCallback(() => {
    setHasActiveOperation(false);
  }, []);

  return {
    hasActiveOperation,
    recordAcceptedOperation,
    recordTerminalOperation,
  };
}
