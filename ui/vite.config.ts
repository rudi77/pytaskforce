/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import fs from "node:fs";
import path from "node:path";

const BACKEND = process.env.TASKFORCE_API_URL ?? "http://127.0.0.1:8070";

/**
 * UI plugin packages that are loaded via dynamic `import()` in
 * `src/plugins/loader.ts`. When the operator has not installed one of
 * these (the typical case — they are optional dependencies), Rollup
 * cannot resolve the bare specifier and the build would fail. We
 * detect installation at config time and externalize the missing
 * packages so the import remains a no-op the runtime catch block can
 * silently swallow.
 *
 * We probe by checking the package.json directly, because
 * `require.resolve` does not honor the `exports` field for ESM-only
 * packages and would mis-classify them as missing.
 */
const OPTIONAL_PLUGIN_PACKAGES = ["@taskforce/enterprise-ui"];

const missingOptionalPlugins = OPTIONAL_PLUGIN_PACKAGES.filter((name) => {
  const pkgJsonPath = path.resolve(__dirname, "node_modules", name, "package.json");
  return !fs.existsSync(pkgJsonPath);
});

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
    preserveSymlinks: false,
  },
  server: {
    port: 5173,
    strictPort: false,
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
    environment: "node",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
