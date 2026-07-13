/**
 * Summary: Mounts the bundled React application and its local fonts.
 * Why: Provides one CSP-safe browser entry point with no remote runtime assets.
 */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./app/app";
import "./styles/fonts.css";
import "./styles/tokens.css";
import "./styles/reset.css";
import "./styles/globals.css";

const rootElement = document.querySelector<HTMLElement>("#root");

if (rootElement === null) {
  throw new Error("OMYM2 could not find its application root.");
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
