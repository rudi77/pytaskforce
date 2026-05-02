/**
 * Ambient type declarations for optional UI plugin packages.
 *
 * These declarations let `ui/src/plugins/loader.ts` reference the
 * dynamic-import targets at the type level even when the matching
 * npm package is not installed. At runtime, missing packages are
 * caught by the loader's try/catch and silently skipped.
 */
declare module "@taskforce/enterprise-ui" {
  import type { PluginRegistry } from "@taskforce/ui-shell";

  export function register(registry: PluginRegistry): void;
  const _default: { register: (registry: PluginRegistry) => void };
  export default _default;
}
