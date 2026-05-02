/**
 * Definition of the Taskforce Enterprise UI plugin.
 *
 * The host pytaskforce/ui dynamically imports `@taskforce/enterprise-ui`
 * at startup and calls `register(registry)` from `index.ts` to add
 * this plugin's nav items + routes to the management shell. Every
 * route is gated by a capability flag — the host's `<CapabilityGuard>`
 * hides the route unless the matching flag is reported as active by
 * the backend's `GET /api/v1/ui/manifest` endpoint.
 *
 * RBAC is enforced inside each route via `requireRoles`. The host's
 * `<RequireRole>` component renders a forbidden page when the
 * current user lacks any of the listed roles.
 */
import { createElement, lazy, type ReactNode } from "react";
import {
  Building2,
  GitPullRequestArrow,
  ListChecks,
  ScrollText,
  Users,
} from "lucide-react";
import type { UIPlugin } from "@taskforce/ui-shell";

import { EnterpriseAuthBoundary } from "./components/EnterpriseAuthBoundary";

// Capability flags — must match the strings the backend
// `EnterprisePlugin.get_ui_manifest()` returns under "capabilities".
export const CAPS = {
  TENANTS: "admin.tenants",
  USERS: "admin.users",
  AUDIT: "admin.audit",
  CATALOG: "agents.catalog",
  APPROVALS: "agents.approvals",
} as const;

export const enterpriseUIPlugin: UIPlugin = {
  id: "enterprise",
  displayName: "Taskforce Enterprise",
  version: "0.1.0",
  capabilities: [
    CAPS.TENANTS,
    CAPS.USERS,
    CAPS.AUDIT,
    CAPS.CATALOG,
    CAPS.APPROVALS,
  ],
  // Mount the enterprise auth boundary OUTSIDE the host's
  // <CapabilityGuard> + <RequireRole> chain so the role guard sees
  // real claims fetched from /api/v1/admin/me. Without this wrapper
  // the host falls back to permissive RBAC (a console.warn is
  // emitted) and admin pages would render for every authenticated
  // user.
  wrap: (children: ReactNode): ReactNode =>
    createElement(EnterpriseAuthBoundary, null, children),
  navItems: [
    {
      to: "/admin/tenants",
      label: "Tenants",
      icon: Building2,
      section: "admin",
      requires: [CAPS.TENANTS],
      order: 10,
    },
    {
      to: "/admin/users",
      label: "Users & Roles",
      icon: Users,
      section: "admin",
      requires: [CAPS.USERS],
      order: 20,
    },
    {
      to: "/admin/audit",
      label: "Audit Log",
      icon: ScrollText,
      section: "admin",
      requires: [CAPS.AUDIT],
      order: 30,
    },
    {
      to: "/admin/catalog",
      label: "Agent Catalog",
      icon: ListChecks,
      section: "admin",
      requires: [CAPS.CATALOG],
      order: 40,
    },
    {
      to: "/admin/approvals",
      label: "Approvals",
      icon: GitPullRequestArrow,
      section: "admin",
      requires: [CAPS.APPROVALS],
      order: 50,
    },
  ],
  routes: [
    {
      path: "admin/tenants",
      element: lazy(() => import("./pages/TenantsPage")),
      requires: [CAPS.TENANTS],
      requireRoles: ["admin"],
    },
    {
      path: "admin/users",
      element: lazy(() => import("./pages/UsersRolesPage")),
      requires: [CAPS.USERS],
      requireRoles: ["admin"],
    },
    {
      path: "admin/audit",
      element: lazy(() => import("./pages/AuditLogPage")),
      requires: [CAPS.AUDIT],
      requireRoles: ["admin", "auditor"],
    },
    {
      path: "admin/catalog",
      element: lazy(() => import("./pages/AgentCatalogPage")),
      requires: [CAPS.CATALOG],
      requireRoles: ["admin", "agent_owner"],
    },
    {
      path: "admin/approvals",
      element: lazy(() => import("./pages/ApprovalsPage")),
      requires: [CAPS.APPROVALS],
      requireRoles: ["admin", "approver"],
    },
  ],
};
