import {
  createBrowserRouter,
  Navigate,
  type RouteObject,
} from "react-router-dom";
import {
  createElement,
  isValidElement,
  lazy,
  Suspense,
  type ComponentType,
  type ReactNode,
} from "react";
import { AppShell } from "@/app/AppShell";
import { RequireAuth } from "@/app/RequireAuth";
import { CapabilityGuard } from "@/plugins/CapabilityGuard";
import { RequireRole } from "@/plugins/RequireRole";
import { registry as defaultRegistry } from "@/plugins/registry";
import type { PluginRegistry, PluginRoute, UIPlugin } from "@/plugins/types";

const Dashboard = lazy(() => import("@/pages/DashboardPage"));
const AgentsList = lazy(() => import("@/pages/AgentsListPage"));
const AgentEditor = lazy(() => import("@/pages/AgentEditorPage"));
const AgentCompare = lazy(() => import("@/pages/AgentComparePage"));
const ChatPage = lazy(() => import("@/pages/ChatPage"));
const MonitoringPage = lazy(() => import("@/pages/MonitoringPage"));
const RunDetailPage = lazy(() => import("@/pages/RunDetailPage"));
const AcpPage = lazy(() => import("@/pages/AcpPage"));
const CapabilitiesPage = lazy(() => import("@/pages/CapabilitiesPage"));
const EvalsPage = lazy(() => import("@/pages/EvalsPage"));
const WorkflowsPage = lazy(() => import("@/pages/WorkflowsPage"));
const SettingsPage = lazy(() => import("@/pages/SettingsPage"));
const LoginPage = lazy(() => import("@/pages/LoginPage"));
const NotFoundPage = lazy(() => import("@/pages/NotFoundPage"));

function PageFallback() {
  return (
    <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
      Loading…
    </div>
  );
}

function withSuspense(node: React.ReactNode) {
  return <Suspense fallback={<PageFallback />}>{node}</Suspense>;
}

/** Render a `PluginRoute.element` whether it was passed as a node or a component. */
function renderPluginElement(element: PluginRoute["element"]): ReactNode {
  if (isValidElement(element)) return element;
  // Components (function/class) AND lazy/memo/forwardRef wrappers are non-element
  // values that must be instantiated via createElement, not rendered as children.
  return createElement(element as ComponentType);
}

/**
 * Strip leading and trailing slashes so plugin authors can write
 * either `"admin/users"` or `"/admin/users/"` without breaking
 * react-router matching.
 */
function normalizeRoutePath(raw: string): string {
  return raw.replace(/^\/+/, "").replace(/\/+$/, "");
}

function pluginRouteToRouteObject(plugin: UIPlugin, route: PluginRoute): RouteObject {
  const required = route.requires ?? [];
  const roles = route.requireRoles ?? [];

  let body: ReactNode = renderPluginElement(route.element);
  if (roles.length > 0) {
    body = <RequireRole roles={roles}>{body}</RequireRole>;
  }
  if (required.length > 0) {
    body = <CapabilityGuard requires={required}>{body}</CapabilityGuard>;
  }
  // Plugin-supplied wrapper sits outside the guards so any provider
  // it mounts (e.g. UserRolesProvider) is visible to RequireRole.
  if (plugin.wrap) {
    body = plugin.wrap(body);
  }

  return {
    path: normalizeRoutePath(route.path),
    element: withSuspense(body),
  };
}

/**
 * Build a top-level (pre-auth) route from a public plugin route.
 *
 * Public routes skip the plugin's ``wrap()`` because the wrap
 * typically depends on the authenticated user (e.g. fetches
 * /admin/me) which is unavailable before login. Capability and role
 * guards are also skipped — public routes are by definition
 * unconditional.
 */
function pluginPublicRouteToRouteObject(
  _plugin: UIPlugin,
  route: PluginRoute,
): RouteObject {
  const body = renderPluginElement(route.element);
  return {
    path: "/" + normalizeRoutePath(route.path),
    element: withSuspense(body),
  };
}

/**
 * Build the React-Router router. Plugin routes are appended to the
 * AppShell layout so they share its sidebar / header chrome.
 *
 * Plugin routes are read from the registry once at build time; later
 * `registry.register()` calls do NOT add new routes to an existing
 * router. The host calls `buildRouter()` exactly once after
 * `bootstrapPlugins()` resolves (see `src/main.tsx`). For HMR,
 * Vite's full-reload on `main.tsx` rebuilds the whole router.
 */
export function buildRouter(registry: PluginRegistry = defaultRegistry) {
  const allPluginRoutes = registry
    .list()
    .flatMap((plugin) =>
      plugin.routes.map((r) => ({ plugin, route: r })),
    );

  // Routes flagged ``public: true`` are mounted at top level (next to
  // /login) so they are reachable before the user is authenticated.
  const publicPluginRoutes: RouteObject[] = allPluginRoutes
    .filter(({ route }) => route.public === true)
    .map(({ plugin, route }) => pluginPublicRouteToRouteObject(plugin, route));

  const pluginRoutes: RouteObject[] = allPluginRoutes
    .filter(({ route }) => route.public !== true)
    .map(({ plugin, route }) => pluginRouteToRouteObject(plugin, route));

  return createBrowserRouter([
    { path: "/login", element: withSuspense(<LoginPage />) },
    ...publicPluginRoutes,
    {
      path: "/",
      element: (
        <RequireAuth>
          <AppShell />
        </RequireAuth>
      ),
      children: [
        { index: true, element: withSuspense(<Dashboard />) },
        { path: "agents", element: withSuspense(<AgentsList />) },
        { path: "agents/compare", element: withSuspense(<AgentCompare />) },
        { path: "agents/new", element: withSuspense(<AgentEditor mode="create" />) },
        { path: "agents/:agentId", element: withSuspense(<AgentEditor mode="edit" />) },
        { path: "chat", element: withSuspense(<ChatPage />) },
        { path: "chat/:conversationId", element: withSuspense(<ChatPage />) },
        { path: "monitoring", element: withSuspense(<MonitoringPage />) },
        { path: "monitoring/runs/:sessionId", element: withSuspense(<RunDetailPage />) },
        { path: "acp", element: withSuspense(<AcpPage />) },
        { path: "workflows", element: withSuspense(<WorkflowsPage />) },
        { path: "capabilities", element: withSuspense(<CapabilitiesPage />) },
        { path: "tools", element: <Navigate to="/capabilities" replace /> },
        { path: "skills", element: <Navigate to="/capabilities" replace /> },
        { path: "evals", element: withSuspense(<EvalsPage />) },
        { path: "settings", element: withSuspense(<SettingsPage />) },
        ...pluginRoutes,
        { path: "*", element: withSuspense(<NotFoundPage />) },
      ],
    },
    { path: "/index.html", element: <Navigate to="/" replace /> },
  ]);
}
