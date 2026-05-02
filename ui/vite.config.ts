/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { createRequire } from "node:module";

const BACKEND = process.env.TASKFORCE_API_URL ?? "http://127.0.0.1:8070";

const requireFromHere = createRequire(import.meta.url);

/**
 * UI plugin packages that are loaded via dynamic `import()` in
 * `src/plugins/loader.ts`. When the operator has not installed one of
 * these (the typical case — they are optional dependencies), Rollup
 * cannot resolve the bare specifier and the build would fail. We
 * detect installation at config time and externalize the missing
 * packages so the import remains a no-op the runtime catch block can
 * silently swallow.
 */
const OPTIONAL_PLUGIN_PACKAGES = ["@taskforce/enterprise-ui"];

const missingOptionalPlugins = OPTIONAL_PLUGIN_PACKAGES.filter((name) => {
  try {
    requireFromHere.resolve(name);
    return false;
  } catch {
    return true;
  }
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
