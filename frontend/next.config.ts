import type { NextConfig } from 'next';
import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';

// Pin the tracing root to this app to avoid Next picking up an unrelated
// parent lockfile as the workspace root.
const projectRoot = dirname(fileURLToPath(import.meta.url));

// Set when nothing else fronts the API on this origin — a Vercel-style deploy
// where the app and the backend live on different hosts. Behind the production
// reverse proxy it stays unset, because the proxy already routes /api.
const backendOrigin = process.env.BACKEND_ORIGIN;

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Emit a self-contained server bundle so the runtime image carries no
  // node_modules tree. Entry point: .next/standalone/server.js.
  output: 'standalone',
  outputFileTracingRoot: projectRoot,
  experimental: {
    // Next 16 turns the Turbopack filesystem cache on by default for `next dev`.
    // Turbopack memory-maps and compacts those .sst segments on startup and on
    // every compile. On this source tree (~170 files) the cache bought nothing
    // and grew to 2.9 GB, which exhausted Windows section resources mid-compile
    // (`os error 1450` — ERROR_NO_SYSTEM_RESOURCES) and took the host down with
    // it. Cold starts here are cheap; the cache is not worth the memory.
    turbopackFileSystemCacheForDev: false,
  },
  async rewrites() {
    if (!backendOrigin) return [];
    return [{ source: '/api/:path*', destination: `${backendOrigin}/api/:path*` }];
  },
};

export default nextConfig;
