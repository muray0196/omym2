/*
Summary: Configures the packaged Next static export.
Why: Keeps the generated Python-package web assets reproducible in CI.
*/

import { dirname } from "node:path"
import { fileURLToPath } from "node:url"

const webRoot = dirname(fileURLToPath(import.meta.url))

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  images: {
    unoptimized: true,
  },
  turbopack: {
    root: webRoot,
  },
  // Next's default build ID is random, which makes committed static exports
  // change even when the UI did not.
  generateBuildId: async () => "omym2-static",
}

export default nextConfig
