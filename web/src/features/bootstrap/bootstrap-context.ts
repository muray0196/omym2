/**
 * Summary: Exposes typed Bootstrap state to later feature routes.
 * Why: Keeps generated initial-state data separate from its presentation component.
 */
import { createContext } from "react";

import type { BootstrapData } from "../../api/generated";

export const BootstrapContext = createContext<BootstrapData | null>(null);
