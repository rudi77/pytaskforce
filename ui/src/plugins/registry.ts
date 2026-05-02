/**
 * Zustand-backed plugin registry.
 *
 * Two consumers:
 *  - The AppShell sidebar reads `list()` + `isCapabilityActive(flag)` to
 *    decide which plugin nav items to render.
 *  - The router factory reads `list()` once at startup to produce the
 *    set of dynamic routes; capability changes are picked up at render
 *    time by `<CapabilityGuard>`.
 *
 * Plugins call `register()` once at module load (typically from
 * `bootstrapPlugins()` in `loader.ts`). Calling `register()` with the
 * same `id` twice replaces the previous registration — supports HMR.
 */
import { create } from "zustand";
import { useShallow } from "zustand/react/shallow";

import type { PluginRegistry, UIPlugin } from "./types";

interface RegistryState {
  plugins: Record<string, UIPlugin>;
  activeCapabilities: Set<string>;
  register: (plugin: UIPlugin) => void;
  setActiveCapabilities: (flags: string[]) => void;
  reset: () => void;
}

const usePluginStore = create<RegistryState>((set) => ({
  plugins: {},
  activeCapabilities: new Set<string>(),
  register: (plugin) =>
    set((state) => ({
      plugins: { ...state.plugins, [plugin.id]: plugin },
    })),
  setActiveCapabilities: (flags) =>
    set(() => ({ activeCapabilities: new Set(flags) })),
  reset: () =>
    set(() => ({ plugins: {}, activeCapabilities: new Set<string>() })),
}));

/** Imperative façade exposed to non-React callers (loader, router factory). */
export const registry: PluginRegistry = {
  register(plugin) {
    usePluginStore.getState().register(plugin);
  },
  list() {
    return Object.values(usePluginStore.getState().plugins);
  },
  setActiveCapabilities(flags) {
    usePluginStore.getState().setActiveCapabilities(flags);
  },
  getActiveCapabilities() {
    return Array.from(usePluginStore.getState().activeCapabilities);
  },
  isCapabilityActive(flag) {
    return usePluginStore.getState().activeCapabilities.has(flag);
  },
  reset() {
    usePluginStore.getState().reset();
  },
};

/**
 * Determine whether a list of required capability flags is satisfied by
 * the currently active set. Empty / undefined `requires` is always
 * satisfied (used as fallback to a plugin's `capabilities` array by
 * the AppShell).
 */
export function capabilitiesSatisfied(
  requires: readonly string[] | undefined,
  active: ReadonlySet<string>,
): boolean {
  if (!requires || requires.length === 0) return true;
  return requires.every((flag) => active.has(flag));
}

/** Reactive hook for components that want to re-render on registry changes. */
export function usePluginRegistry() {
  return usePluginStore(
    useShallow((state) => ({
      plugins: Object.values(state.plugins),
      activeCapabilities: state.activeCapabilities,
    })),
  );
}

/** Reactive hook returning a single capability's active state. */
export function useIsCapabilityActive(flag: string): boolean {
  return usePluginStore((state) => state.activeCapabilities.has(flag));
}

/** Test-only hook to access the underlying store (e.g. in vitest). */
export const __pluginStoreForTests = usePluginStore;
