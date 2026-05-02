/**
 * Optional plugin bootstrap.
 *
 * Tries to dynamically import every known optional plugin package and
 * call its exported `register(registry)` function. Packages that are
 * not installed (or fail to load for any reason) are silently skipped
 * — their absence is the expected case when the operator has not opted
 * into the corresponding feature.
 *
 * This file is the single place that knows about specific plugin
 * package names. To add a new plugin, append it to `OPTIONAL_PLUGINS`.
 */
import { registry } from "./registry";
import type { PluginRegistry } from "./types";

interface OptionalPluginModule {
  register?: (registry: PluginRegistry) => void;
  default?: { register?: (registry: PluginRegistry) => void };
}

interface OptionalPluginEntry {
  /** Human-readable plugin id, only used for diagnostic logs. */
  id: string;
  /** Dynamic-import callback. Wrapped in `() => import(...)` so Vite
   * statically resolves the module specifier at build time but the
   * actual import only fires at runtime. */
  load: () => Promise<OptionalPluginModule>;
}

/**
 * Plugin packages this UI knows how to load. Each entry corresponds to
 * an `optionalDependencies` entry in `package.json`. When the package
 * is not installed, `pnpm` / `npm` skips it and Vite's bundler emits a
 * runtime error which the try/catch below silently swallows.
 */
const OPTIONAL_PLUGINS: OptionalPluginEntry[] = [
  {
    id: "enterprise",
    // @ts-expect-error - package is optional, may not be installed
    load: () => import("@taskforce/enterprise-ui"),
  },
];

/** Load all optional plugin packages and let them register themselves. */
export async function bootstrapPlugins(): Promise<void> {
  await Promise.all(
    OPTIONAL_PLUGINS.map(async (entry) => {
      try {
        const mod = await entry.load();
        const register = mod.register ?? mod.default?.register;
        if (typeof register === "function") {
          register(registry);
        } else if (import.meta.env.DEV) {
          console.warn(
            `[plugins] '${entry.id}' loaded but exports no register() function`,
          );
        }
      } catch {
        // Package not installed or failed to import — expected when the
        // operator has not opted into this feature. Stay quiet.
      }
    }),
  );
}
