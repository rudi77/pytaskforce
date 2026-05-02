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
import { CapabilityGuard } from "@/plugins/CapabilityGuard";
import { RequireRole } from "@/plugins/RequireRole";
import { registry as defaultRegistry } from "@/plugins/registry";
import type { PluginRegistry, PluginRoute } from "@/plugins/types";

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
const SettingsPage = lazy(() => import("@/pages/SettingsPage"));
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
  if (typeof element === "function") {
    return createElement(element as ComponentType);
  }
  return element as ReactNode;
}

function pluginRouteToRouteObject(route: PluginRoute): RouteObject {
  const required = route.requires ?? [];
  const roles = route.requireRoles ?? [];

  let body: ReactNode = renderPluginElement(route.element);
  if (roles.length > 0) {
    body = <RequireRole roles={roles}>{body}</RequireRole>;
  }
  if (required.length > 0) {
    body = <CapabilityGuard requires={required}>{body}</CapabilityGuard>;
  }

  return {
    path: route.path.replace(/^\//, ""),
    element: withSuspense(body),
  };
}

/**
 * Build the React-Router router. Plugin routes are appended to the
 * AppShell layout so they share its sidebar / header chrome. Routes
 * are statically registered at build time — capability gating happens
 * at render time inside `<CapabilityGuard>`.
 */
export function buildRouter(registry: PluginRegistry = defaultRegistry) {
  const pluginRoutes: RouteObject[] = registry
    .list()
    .flatMap((plugin) => plugin.routes.map(pluginRouteToRouteObject));

  return createBrowserRouter([
    {
      path: "/",
      element: <AppShell />,
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

/** Default router built against the global plugin registry. */
export const router = buildRouter();
