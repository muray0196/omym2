/*
Summary: Declares Vite frontend asset imports.
Why: Lets TypeScript accept CSS entry imports during production builds.
*/

/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_OMYM2_API_MODE?: string;
}

declare module "*.css";
