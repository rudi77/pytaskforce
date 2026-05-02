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
import type { PluginContext, PluginRegistry, UIPlugin } from "./types";

interface OptionalPluginModule {
  register?: (registry: PluginRegistry) => void;
  default?: { register?: (registry: PluginRegistry) => void };
}

const pluginContext: PluginContext = {
  isCapabilityActive: (flag) => registry.isCapabilityActive(flag),
};

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
    load: () => import("@taskforce/enterprise-ui"),
  },
];

/**
 * Load all optional plugin packages and let them register themselves.
 *
 * For each successfully imported package the loader:
 *   1. Calls `register(registry)` synchronously.
 *   2. Awaits each newly-registered plugin's optional `init(ctx)` so
 *      plugins can perform async startup (e.g. priming queries) before
 *      the router renders any of their pages.
 *
 * `register()` itself must be synchronous — its job is purely to add
 * the plugin's `UIPlugin` value to the registry. Anything async
 * belongs in `init`.
 */
export async function bootstrapPlugins(): Promise<void> {
  await Promise.all(
    OPTIONAL_PLUGINS.map(async (entry) => {
      let beforeIds: ReadonlySet<string>;
      try {
        beforeIds = new Set(registry.list().map((p) => p.id));
        const mod = await entry.load();
        const register = mod.register ?? mod.default?.register;
        if (typeof register === "function") {
          register(registry);
        } else if (import.meta.env.DEV) {
          console.warn(
            `[plugins] '${entry.id}' loaded but exports no register() function`,
          );
          return;
        }
      } catch {
        // Package not installed or failed to import — expected when the
        // operator has not opted into this feature. Stay quiet.
        return;
      }

      const justRegistered: UIPlugin[] = registry
        .list()
        .filter((p) => !beforeIds.has(p.id));
      await Promise.all(
        justRegistered.map(async (plugin) => {
          if (!plugin.init) return;
          try {
            await plugin.init(pluginContext);
          } catch (error) {
            // Init failures must not block other plugins.
            console.error(`[plugins] '${plugin.id}' init() failed:`, error);
          }
        }),
      );
    }),
  );
}
