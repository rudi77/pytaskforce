import {
  createBrowserRouter,
  Navigate,
  type RouteObject,
  useRouteError,
} from "react-router-dom";
import {
  createElement,
  isValidElement,
  lazy,
  Suspense,
  useState,
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
const ProjectsPage = lazy(() => import("@/pages/ProjectsPage"));
const ProjectDetailPage = lazy(() => import("@/pages/ProjectDetailPage"));
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

function getRouteErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  return "The page could not be loaded.";
}

// Dynamic-import 404s come from a Vite chunk-hash mismatch — the open tab is
// referencing chunk URLs from a previous dev session that no longer exist
// (e.g. after `dev.ps1` wiped node_modules/.vite, after `git pull`, or after
// any pnpm install that re-optimized deps). A hard reload pulls a fresh
// index.html and picks up the current chunk hashes. We attempt this at most
// once per short window to avoid an infinite reload loop if the import is
// genuinely broken.
//
// Two-layer guard:
//   1. `dynamicImportReloadAttemptedInThisPageLoad` (module-scope) — survives
//      React unmount/remount cycles within the same page load. The error
//      boundary remounts during the route-transition recovery; without this
//      flag, the second mount would see the already-stamped sessionStorage
//      key and fall through to the manual UI, even though we *did* trigger
//      a reload from the first mount. Reset implicitly when the module
//      re-initializes after `location.reload()`.
//   2. `DYNAMIC_IMPORT_RELOAD_KEY` in sessionStorage — survives the reload
//      itself, so if the page comes back up and the import still fails (e.g.
//      a genuinely broken page), the boundary shows the manual UI instead of
//      looping reload → fail → reload.
const DYNAMIC_IMPORT_RELOAD_KEY = "tf:dynamic-import-reload-attempt";
const DYNAMIC_IMPORT_RELOAD_WINDOW_MS = 10_000;
let dynamicImportReloadAttemptedInThisPageLoad = false;

/** Test-only seam to reset the in-memory guard between cases. */
export function __resetDynamicImportReloadGuard() {
  dynamicImportReloadAttemptedInThisPageLoad = false;
}

function tryScheduleAutoReload(): boolean {
  if (dynamicImportReloadAttemptedInThisPageLoad) return false;
  try {
    const raw = window.sessionStorage.getItem(DYNAMIC_IMPORT_RELOAD_KEY);
    if (raw) {
      const ts = Number.parseInt(raw, 10);
      if (Number.isFinite(ts) && Date.now() - ts < DYNAMIC_IMPORT_RELOAD_WINDOW_MS) {
        // Already retried in a previous page load — the import is genuinely
        // broken; show the manual UI instead of looping.
        return false;
      }
    }
    window.sessionStorage.setItem(DYNAMIC_IMPORT_RELOAD_KEY, String(Date.now()));
    dynamicImportReloadAttemptedInThisPageLoad = true;
    // Schedule the reload as a microtask so the placeholder paints first
    // and we don't depend on React's useEffect commit — react-router's
    // error-recovery sometimes remounts the boundary before the effect
    // from the first mount fires, which would otherwise swallow the
    // reload call.
    queueMicrotask(() => {
      window.location.reload();
    });
    return true;
  } catch {
    return false;
  }
}

function RouteErrorBoundary() {
  const error = useRouteError();
  const message = getRouteErrorMessage(error);
  const isDynamicImportError = message.includes("Failed to fetch dynamically imported module");
  // Lazy initializer — evaluates exactly once per mount, so the
  // sessionStorage side-effect doesn't repeat across re-renders.
  const [willAutoReload] = useState(() =>
    isDynamicImportError && tryScheduleAutoReload(),
  );

  if (willAutoReload) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-6 text-sm text-muted-foreground">
        Reloading…
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="w-full max-w-lg rounded-lg border border-border bg-card p-6 shadow-sm">
        <p className="text-sm font-medium uppercase tracking-wide text-muted-foreground">
          Page error
        </p>
        <h1 className="mt-2 text-2xl font-semibold text-foreground">
          {isDynamicImportError ? "Page update required" : "Something went wrong"}
        </h1>
        <p className="mt-3 text-sm text-muted-foreground">
          {isDynamicImportError
            ? "The page module could not be loaded. This usually happens after the development server or app bundle changed."
            : message}
        </p>
        <div className="mt-5 flex flex-wrap gap-3">
          <button
            type="button"
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            onClick={() => window.location.reload()}
          >
            Reload page
          </button>
          <button
            type="button"
            className="rounded-md border border-input bg-background px-4 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground"
            onClick={() => window.history.back()}
          >
            Go back
          </button>
        </div>
      </div>
    </div>
  );
}

const routeErrorElement = <RouteErrorBoundary />;

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
    errorElement: routeErrorElement,
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
    errorElement: routeErrorElement,
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
    { path: "/login", element: withSuspense(<LoginPage />), errorElement: routeErrorElement },
    ...publicPluginRoutes,
    {
      path: "/",
      element: (
        <RequireAuth>
          <AppShell />
        </RequireAuth>
      ),
      errorElement: routeErrorElement,
      children: [
        { index: true, element: withSuspense(<Dashboard />), errorElement: routeErrorElement },
        { path: "agents", element: withSuspense(<AgentsList />), errorElement: routeErrorElement },
        { path: "agents/compare", element: withSuspense(<AgentCompare />), errorElement: routeErrorElement },
        { path: "agents/new", element: withSuspense(<AgentEditor mode="create" />), errorElement: routeErrorElement },
        { path: "agents/:agentId", element: withSuspense(<AgentEditor mode="edit" />), errorElement: routeErrorElement },
        { path: "chat", element: withSuspense(<ChatPage />), errorElement: routeErrorElement },
        { path: "chat/:conversationId", element: withSuspense(<ChatPage />), errorElement: routeErrorElement },
        { path: "projects", element: withSuspense(<ProjectsPage />), errorElement: routeErrorElement },
        { path: "projects/:projectId", element: withSuspense(<ProjectDetailPage />), errorElement: routeErrorElement },
        { path: "monitoring", element: withSuspense(<MonitoringPage />), errorElement: routeErrorElement },
        { path: "monitoring/runs/:sessionId", element: withSuspense(<RunDetailPage />), errorElement: routeErrorElement },
        { path: "acp", element: withSuspense(<AcpPage />), errorElement: routeErrorElement },
        { path: "workflows", element: withSuspense(<WorkflowsPage />), errorElement: routeErrorElement },
        { path: "capabilities", element: withSuspense(<CapabilitiesPage />), errorElement: routeErrorElement },
        { path: "tools", element: <Navigate to="/capabilities" replace /> },
        { path: "skills", element: <Navigate to="/capabilities" replace /> },
        { path: "evals", element: withSuspense(<EvalsPage />), errorElement: routeErrorElement },
        { path: "settings", element: withSuspense(<SettingsPage />), errorElement: routeErrorElement },
        ...pluginRoutes,
        { path: "*", element: withSuspense(<NotFoundPage />), errorElement: routeErrorElement },
      ],
    },
    { path: "/index.html", element: <Navigate to="/" replace />, errorElement: routeErrorElement },
  ]);
}
