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
}

export default nextConfig
