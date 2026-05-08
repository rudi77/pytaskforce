/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

const BACKEND = process.env.TASKFORCE_API_URL ?? "http://127.0.0.1:8070";

const HOST_VERSION = (() => {
  try {
    const raw = JSON.parse(
      fs.readFileSync(path.resolve(__dirname, "package.json"), "utf-8"),
    ) as { version?: string };
    return raw.version ?? "0.0.0";
  } catch {
    return "0.0.0";
  }
})();

/**
 * UI plugin packages that are loaded via dynamic `import()` in
 * `src/plugins/loader.ts`. When the operator has not installed one of
 * these (the typical case — they are optional dependencies), Rollup
 * cannot resolve the bare specifier and the build would fail. We
 * detect installation at config time and externalize the missing
 * packages so the import remains a no-op the runtime catch block can
 * silently swallow.
 *
 * Detection probes via:
 *   1. `require.resolve(name, { paths })` — handles standard CJS, npm
 *      workspaces, pnpm hoisting, and yarn berry pnp layouts. This
 *      respects Node's `exports` field for any package shipping
 *      `main`/`module`.
 *   2. Fallback: probe `<basedir>/node_modules/<name>/package.json`
 *      directly, because `require.resolve` does NOT honor the
 *      `exports` field for ESM-only packages without a `main` field
 *      (Node refuses to resolve such packages from a CJS context).
 *
 * NOTE: This runs at vite config-load time. Operators who install an
 * optional plugin AFTER `vite dev` is already running must restart
 * the dev server.
 */
const OPTIONAL_PLUGIN_PACKAGES = ["@taskforce/enterprise-ui"];

const PLUGIN_RESOLUTION_PATHS = [
  __dirname,
  path.resolve(__dirname, ".."),
  path.resolve(__dirname, "..", ".."),
];

const requireFromHere = createRequire(import.meta.url);

function isPluginPackageInstalled(name: string): boolean {
  // Step 1: try Node's resolver against several candidate base dirs.
  try {
    requireFromHere.resolve(name, { paths: PLUGIN_RESOLUTION_PATHS });
    return true;
  } catch {
    /* fall through */
  }
  // Step 2: ESM-only packages without `main` / with `exports` only —
  // probe the package.json directly under each candidate node_modules.
  for (const base of PLUGIN_RESOLUTION_PATHS) {
    const pkgJson = path.resolve(base, "node_modules", name, "package.json");
    if (fs.existsSync(pkgJson)) return true;
  }
  return false;
}

const missingOptionalPlugins = OPTIONAL_PLUGIN_PACKAGES.filter(
  (name) => !isPluginPackageInstalled(name),
);

export default defineConfig({
  plugins: [react()],
  define: {
    __TASKFORCE_UI_VERSION__: JSON.stringify(HOST_VERSION),
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
    preserveSymlinks: false,
  },
  server: {
    port: 5173,
    strictPort: false,
    headers: {
      "Cache-Control": "no-store",
    },
    proxy: {
      "/api": { target: BACKEND, changeOrigin: true },
      "/health": { target: BACKEND, changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    rollupOptions: {
      external: missingOptionalPlugins,
    },
  },
  optimizeDeps: {
    exclude: OPTIONAL_PLUGIN_PACKAGES,
  },
  test: {
    // jsdom is required for React component tests (testing-library/react,
    // CapabilityGuard, RequireRole, AppBootstrap rendering). Pure-logic
    // tests (registry.test.ts, skew.test.ts) work in any environment.
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/__tests__/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
