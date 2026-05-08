import { useEffect, useMemo, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Activity,
  Beaker,
  Bot,
  LayoutDashboard,
  LogOut,
  MessageSquare,
  Network,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  Sparkles,
  Workflow,
  Moon,
  Sun,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/app/theme-provider";
import { HealthIndicator } from "@/components/HealthIndicator";
import { useSettings } from "@/lib/settings";
import { capabilitiesSatisfied, usePluginRegistry } from "@/plugins/registry";
import type { PluginNavItem } from "@/plugins/types";
import { useCurrentPermissions } from "@/lib/permissions";

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  end?: boolean;
  section?: "main" | "admin";
  order?: number;
}

const BUILTIN_NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true, section: "main", order: 0 },
  { to: "/agents", label: "Agents", icon: Bot, section: "main", order: 10 },
  { to: "/chat", label: "Chat", icon: MessageSquare, section: "main", order: 20 },
  { to: "/monitoring", label: "Monitoring", icon: Activity, section: "main", order: 30 },
  { to: "/capabilities", label: "Capabilities", icon: Sparkles, section: "main", order: 40 },
  { to: "/acp", label: "ACP Peers", icon: Network, section: "main", order: 50 },
  { to: "/workflows", label: "Workflows", icon: Workflow, section: "main", order: 55 },
  { to: "/evals", label: "Evals", icon: Beaker, section: "main", order: 60 },
];

const BUILTIN_PAGE_TITLES: Record<string, string> = {
  "/": "Dashboard",
  "/agents": "Agents",
  "/chat": "Chat",
  "/monitoring": "Monitoring",
  "/acp": "ACP Peers",
  "/workflows": "Workflows",
  "/capabilities": "Capabilities",
  "/evals": "Evals",
  "/settings": "Settings",
};

const COLLAPSED_KEY = "taskforce.sidebar.collapsed";

// Each built-in admin path requires one of these permissions. The admin
// section is rendered only when the current user has at least one of
// them. When permissions are not enforced (single-tenant build, no
// enterprise auth) `can()` returns true and the section stays visible.
const ADMIN_PATH_PERMISSIONS: Record<string, string> = {
  "/admin/tenants": "tenant:manage",
  "/admin/users": "user:manage",
  "/admin/audit": "audit:read",
  "/admin/catalog": "agent:create",
  "/admin/approvals": "tenant:manage",
  "/admin/mcp": "system:config",
};

function ThemeToggle() {
  const { theme, toggle } = useTheme();
  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={toggle}
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
      title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
    >
      {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </Button>
  );
}

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
  mainItems: NavItem[];
  adminItems: NavItem[];
}

function NavSection({
  items,
  collapsed,
  label,
}: {
  items: NavItem[];
  collapsed: boolean;
  label?: string;
}) {
  if (items.length === 0) return null;
  return (
    <div className="space-y-0.5">
      {!collapsed && label ? (
        <div className="px-3 pt-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/70">
          {label}
        </div>
      ) : null}
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          title={collapsed ? item.label : undefined}
          className={({ isActive }) =>
            cn(
              "flex items-center gap-3 rounded-md text-sm font-medium transition-colors",
              collapsed ? "justify-center p-2" : "px-3 py-2",
              isActive
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
            )
          }
        >
          <item.icon className="h-4 w-4 shrink-0" />
          {collapsed ? null : <span>{item.label}</span>}
        </NavLink>
      ))}
    </div>
  );
}

function Sidebar({ collapsed, onToggle, mainItems, adminItems }: SidebarProps) {
  const navigate = useNavigate();
  const setApiToken = useSettings((s) => s.setApiToken);
  const handleLogout = () => {
    setApiToken("");
    navigate("/login", { replace: true });
  };
  return (
    <aside
      className={cn(
        "hidden md:flex shrink-0 flex-col border-r border-border bg-card/40 transition-[width] duration-150",
        collapsed ? "w-14" : "w-60",
      )}
    >
      <div
        className={cn(
          "flex h-14 items-center gap-2 border-b border-border",
          collapsed ? "justify-center px-2" : "px-4",
        )}
      >
        <Sparkles className="h-5 w-5 shrink-0 text-primary" />
        {collapsed ? null : (
          <span className="text-base font-semibold tracking-tight">Taskforce</span>
        )}
      </div>
      <nav className={cn("flex-1 space-y-1", collapsed ? "p-1.5" : "p-3")}>
        <NavSection items={mainItems} collapsed={collapsed} />
        <NavSection items={adminItems} collapsed={collapsed} label="Admin" />
      </nav>
      <div className={cn("border-t border-border", collapsed ? "p-1.5" : "p-3")}>
        <NavLink
          to="/settings"
          title={collapsed ? "Settings" : undefined}
          className={({ isActive }) =>
            cn(
              "flex items-center gap-3 rounded-md text-sm font-medium transition-colors",
              collapsed ? "justify-center p-2" : "px-3 py-2",
              isActive
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
            )
          }
        >
          <Settings className="h-4 w-4 shrink-0" />
          {collapsed ? null : <span>Settings</span>}
        </NavLink>
        <button
          type="button"
          onClick={handleLogout}
          title={collapsed ? "Sign out" : undefined}
          className={cn(
            "mt-1 flex w-full items-center gap-3 rounded-md text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground",
            collapsed ? "justify-center p-2" : "px-3 py-2",
          )}
        >
          <LogOut className="h-4 w-4 shrink-0" />
          {collapsed ? null : <span>Sign out</span>}
        </button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={onToggle}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={cn("mt-2 w-full", collapsed ? "h-8" : "h-7 justify-start gap-2 px-3")}
        >
          {collapsed ? (
            <PanelLeftOpen className="h-4 w-4" />
          ) : (
            <>
              <PanelLeftClose className="h-4 w-4" />
              <span className="text-xs font-medium">Collapse</span>
            </>
          )}
        </Button>
      </div>
    </aside>
  );
}

function getPageTitle(pathname: string, pageTitles: Record<string, string>): string {
  if (pageTitles[pathname]) return pageTitles[pathname];
  const segment = "/" + pathname.split("/").filter(Boolean)[0];
  return pageTitles[segment] ?? "Taskforce";
}

function pluginNavItemToNavItem(
  item: PluginNavItem,
  pluginCapabilities: readonly string[],
  active: ReadonlySet<string>,
): NavItem | null {
  // `requires` is the per-item override; when omitted we fall back to
  // the owning plugin's full capability list so an item is hidden as
  // soon as ANY of the plugin's caps becomes inactive.
  const requires = item.requires ?? pluginCapabilities;
  if (!capabilitiesSatisfied(requires, active)) return null;
  return {
    to: item.to,
    label: item.label,
    icon: item.icon,
    end: item.end,
    section: item.section ?? "admin",
    order: item.order,
  };
}

export function AppShell() {
  const { pathname } = useLocation();
  const { plugins, activeCapabilities } = usePluginRegistry();
  const permissions = useCurrentPermissions();
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem(COLLAPSED_KEY) === "1";
  });

  const { mainItems, adminItems, pageTitles } = useMemo(() => {
    const collected: NavItem[] = [...BUILTIN_NAV_ITEMS];
    for (const plugin of plugins) {
      for (const navItem of plugin.navItems) {
        const resolved = pluginNavItemToNavItem(
          navItem,
          plugin.capabilities,
          activeCapabilities,
        );
        if (resolved) collected.push(resolved);
      }
    }

    const sortByOrder = (a: NavItem, b: NavItem) =>
      (a.order ?? Number.MAX_SAFE_INTEGER) - (b.order ?? Number.MAX_SAFE_INTEGER);

    const mainItems = collected
      .filter((it) => (it.section ?? "main") === "main")
      .sort(sortByOrder);
    const adminItems = collected
      .filter((it) => it.section === "admin")
      .filter((it) => {
        const required = ADMIN_PATH_PERMISSIONS[it.to];
        return required ? permissions.can(required) : true;
      })
      .sort(sortByOrder);

    const pageTitles: Record<string, string> = { ...BUILTIN_PAGE_TITLES };
    for (const item of [...mainItems, ...adminItems]) {
      pageTitles[item.to] = item.label;
    }

    return { mainItems, adminItems, pageTitles };
  }, [plugins, activeCapabilities, permissions]);

  const title = getPageTitle(pathname, pageTitles);

  useEffect(() => {
    window.localStorage.setItem(COLLAPSED_KEY, collapsed ? "1" : "0");
  }, [collapsed]);

  return (
    <div className="flex h-full">
      <Sidebar
        collapsed={collapsed}
        onToggle={() => setCollapsed((c) => !c)}
        mainItems={mainItems}
        adminItems={adminItems}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-border bg-background/80 px-6 backdrop-blur">
          <h1 className="text-base font-semibold tracking-tight">{title}</h1>
          <div className="flex items-center gap-2">
            <HealthIndicator />
            <ThemeToggle />
          </div>
        </header>
        <main className="min-h-0 flex-1 overflow-auto scrollbar-thin">
          <div className="mx-auto w-full max-w-[1600px] p-6">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
