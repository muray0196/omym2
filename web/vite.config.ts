/**
 * Summary: Configures the bundled Vite production and development builds.
 * Why: Keeps the bundled SPA same-origin in development and CSP-safe in production.
 */
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  base: "/",
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
      },
    },
  },
  build: {
    assetsInlineLimit: 0,
    assetsDir: "assets",
    sourcemap: false,
  },
});
