/**
 * The plugin contract types are owned by `@taskforce/ui-shell` so the
 * host UI and any external plugin (`@taskforce/enterprise-ui`, ...)
 * speak exactly the same shape. This module re-exports them so
 * existing host-side imports (`@/plugins/types`) keep working.
 */
export type {
  PluginContext,
  PluginNavItem,
  PluginRegistry,
  PluginRoute,
  UIPlugin,
} from "@taskforce/ui-shell";
