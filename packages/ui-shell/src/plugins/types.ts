/**
 * Public contract for UI plugins. External packages (e.g. the optional
 * `@taskforce/enterprise-ui` package) implement this interface and call
 * `register(registry)` from their entry module to contribute nav items
 * and routes to the management shell.
 *
 * Visibility is gated at runtime by the backend manifest
 * (`GET /api/v1/ui/manifest`): a plugin's nav item / route is only
 * mounted when every capability flag in `requires` is reported as active.
 */
import type { ComponentType, ReactNode, SVGProps } from "react";

/**
 * Component that renders an icon. Accepts standard SVG props (className,
 * style, aria-*). Compatible with both lucide-react components and
 * @fluentui/react-icons components, so a plugin can ship either family
 * without changing the contract.
 */
export type PluginIcon = ComponentType<SVGProps<SVGSVGElement> & { className?: string }>;

/** A sidebar entry contributed by a plugin. */
export interface PluginNavItem {
  /** Absolute route path, e.g. `/admin/users`. */
  to: string;
  /** Display label rendered in the sidebar. */
  label: string;
  /** Icon component used for the leading glyph (lucide or Fluent). */
  icon: PluginIcon;
  /**
   * Sidebar bucket. Plugin items default to `"admin"` when omitted so
   * they are visually separated from the built-in main navigation.
   */
  section?: "main" | "admin";
  /**
   * Capability flags that ALL must be present in the active manifest
   * for this nav item to be rendered. Defaults to the plugin's own
   * `capabilities` array when omitted.
   */
  requires?: string[];
  /** Forwarded to React-Router `<NavLink end={...}>` for exact matching. */
  end?: boolean;
  /** Sort order within the section; falls back to insertion order. */
  order?: number;
}

/** A page contributed by a plugin. */
export interface PluginRoute {
  /** Path relative to the AppShell root, e.g. `"admin/users"`. */
  path: string;
  /** Either a rendered ReactNode or a component type that takes no props. */
  element: ReactNode | ComponentType;
  /** Optional title shown in the AppShell header. */
  title?: string;
  /**
   * Capability flags that ALL must be present for the route to render
   * its element. When missing the route renders the global NotFound page.
   */
  requires?: string[];
  /**
   * Optional RBAC roles. The route only renders when the current user
   * holds at least one of these. The shell provides a `<RequireRole>`
   * helper but does not enforce these flags itself — the plugin must
   * wrap its element accordingly.
   */
  requireRoles?: string[];
  /**
   * When ``true``, the host mounts this route at the *top level* —
   * outside the ``RequireAuth`` boundary AND outside the plugin's
   * ``wrap()`` (since auth-dependent providers can't run before the
   * user has logged in). Use this for pre-auth pages like signup or
   * password-reset. Default is ``false`` (private route inside
   * AppShell).
   */
  public?: boolean;
}

/** Bag of host services passed into a plugin's optional `init` callback. */
export interface PluginContext {
  /** Whether a given capability flag is currently reported as active. */
  isCapabilityActive(flag: string): boolean;
}

/** A plugin contribution. Each external package exports exactly one. */
export interface UIPlugin {
  /** Stable plugin id, e.g. `"enterprise"`. Must match the backend manifest. */
  id: string;
  /** Human-readable plugin name, used in diagnostics. */
  displayName: string;
  /** Plugin version (semver), for skew warnings. */
  version: string;
  /**
   * All capability flags this plugin can contribute. Treated as the
   * default `requires` list when individual nav items / routes do not
   * declare their own.
   */
  capabilities: string[];
  /** Sidebar entries this plugin contributes. */
  navItems: PluginNavItem[];
  /** Pages this plugin contributes. */
  routes: PluginRoute[];
  /**
   * Optional wrapper applied around every contributed route — OUTSIDE
   * `<CapabilityGuard>` and `<RequireRole>`. This is the canonical
   * place to mount auth providers (e.g. `<UserRolesProvider>`) so the
   * RBAC guard sees real claims. The wrapper is invoked once per
   * route-mount; a typical implementation will use a single React
   * Query call (deduplicated by query key) so the request fires once
   * across all routes.
   */
  wrap?(children: ReactNode): ReactNode;
  /**
   * Optional one-time bootstrap callback invoked by the host's
   * `bootstrapPlugins()` after `register()` succeeds. Use it for
   * async startup work (priming caches, warming OAuth tokens, …).
   */
  init?(ctx: PluginContext): void | Promise<void>;
}

/**
 * Mutable registry consumed by the AppShell and router. The host owns
 * the implementation; plugins only see the `register` method.
 */
export interface PluginRegistry {
  register(plugin: UIPlugin): void;
  list(): UIPlugin[];
  setActiveCapabilities(flags: string[]): void;
  getActiveCapabilities(): string[];
  isCapabilityActive(flag: string): boolean;
  reset(): void;
}
