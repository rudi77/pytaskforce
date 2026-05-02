import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import dts from "vite-plugin-dts";
import path from "node:path";

/**
 * Library-mode build for `@taskforce/ui-shell`.
 *
 * Externalizes every peer dependency so the consumer (e.g. the
 * pytaskforce host UI or the enterprise UI plugin) supplies a single
 * copy at runtime. The output is plain ESM so modern bundlers can
 * tree-shake it.
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
        "zustand",
        "zustand/react/shallow",
        /^@radix-ui\//,
        "class-variance-authority",
        "clsx",
        "tailwind-merge",
      ],
    },
  },
});
