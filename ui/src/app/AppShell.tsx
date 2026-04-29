import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  Activity,
  Bot,
  LayoutDashboard,
  MessageSquare,
  Network,
  Settings,
  Sparkles,
  Wrench,
  Moon,
  Sun,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/app/theme-provider";
import { HealthIndicator } from "@/components/HealthIndicator";

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  end?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/agents", label: "Agents", icon: Bot },
  { to: "/chat", label: "Chat", icon: MessageSquare },
  { to: "/monitoring", label: "Monitoring", icon: Activity },
  { to: "/acp", label: "ACP Peers", icon: Network },
  { to: "/tools", label: "Tools", icon: Wrench },
];

const PAGE_TITLES: Record<string, string> = {
  "/": "Dashboard",
  "/agents": "Agents",
  "/chat": "Chat",
  "/monitoring": "Monitoring",
  "/acp": "ACP Peers",
  "/tools": "Tool Catalog",
  "/settings": "Settings",
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

function Sidebar() {
  return (
    <aside className="hidden md:flex w-60 shrink-0 flex-col border-r border-border bg-card/40">
      <div className="flex h-14 items-center gap-2 border-b border-border px-4">
        <Sparkles className="h-5 w-5 text-primary" />
        <span className="text-base font-semibold tracking-tight">Taskforce</span>
      </div>
      <nav className="flex-1 space-y-0.5 p-3">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
              )
            }
          >
            <item.icon className="h-4 w-4" />
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="border-t border-border p-3">
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              isActive
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
            )
          }
        >
          <Settings className="h-4 w-4" />
          <span>Settings</span>
        </NavLink>
      </div>
    </aside>
  );
}

function getPageTitle(pathname: string): string {
  if (PAGE_TITLES[pathname]) return PAGE_TITLES[pathname];
  const segment = "/" + pathname.split("/").filter(Boolean)[0];
  return PAGE_TITLES[segment] ?? "Taskforce";
}

export function AppShell() {
  const { pathname } = useLocation();
  const title = getPageTitle(pathname);
  return (
    <div className="flex h-full">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-border bg-background/80 px-6 backdrop-blur">
          <h1 className="text-base font-semibold tracking-tight">{title}</h1>
          <div className="flex items-center gap-2">
            <HealthIndicator />
            <ThemeToggle />
          </div>
        </header>
        <main className="min-h-0 flex-1 overflow-auto scrollbar-thin">
          <div className="mx-auto max-w-7xl p-6">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
