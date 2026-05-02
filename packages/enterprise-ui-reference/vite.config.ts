import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import dts from "vite-plugin-dts";
import path from "node:path";

/**
 * Library-mode build for `@taskforce/enterprise-ui`.
 *
 * Externalizes every shared peer (React, react-router-dom,
 * @taskforce/ui-shell, lucide, react-query) so the host bundle keeps
 * a single copy of each. The output is plain ESM that the host's
 * Vite/Rollup tree-shakes per route via the `lazy(() => import(...))`
 * statements in `plugin.ts`.
 */
export default defineConfig({
  plugins: [
    react(),
    dts({
      entryRoot: "src",
      outDir: "dist",
      include: ["src/**/*.ts", "src/**/*.tsx"],
      insertTypesEntry: true,
    }),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    lib: {
      entry: path.resolve(__dirname, "src/index.ts"),
      formats: ["es"],
      fileName: () => "index.js",
    },
    rollupOptions: {
      external: [
        "react",
        "react/jsx-runtime",
        "react-dom",
        "react-router-dom",
        "@tanstack/react-query",
        "lucide-react",
        "@taskforce/ui-shell",
      ],
    },
  },
});
