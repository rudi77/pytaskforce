import { useEffect, useMemo, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Add16Regular,
  Add20Regular,
  Archive16Regular,
  Beaker16Regular,
  Board16Regular,
  Bot16Regular,
  Chat16Regular,
  ChevronDown16Regular,
  Clock16Regular,
  Delete16Regular,
  Edit16Regular,
  Flow16Regular,
  FolderOpen16Regular,
  MoreHorizontal16Regular,
  Navigation20Regular,
  PanelLeftContract16Regular,
  PanelLeftExpand16Regular,
  Person16Regular,
  PlugConnected16Regular,
  Pulse20Regular,
  SignOut20Regular,
  Sparkle16Regular,
  Sparkle20Regular,
  Wand16Regular,
  WeatherMoon16Regular,
  WeatherSunny16Regular,
} from "@fluentui/react-icons";
import {
  Button,
  Drawer,
  DrawerBody,
  DrawerHeader,
  DrawerHeaderTitle,
  Menu,
  MenuItem,
  MenuList,
  MenuPopover,
  MenuTrigger,
  SearchBox,
} from "@fluentui/react-components";

import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { Button as UIButton } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useTheme } from "@/app/theme-provider";
import { HealthIndicator } from "@/components/HealthIndicator";
import { useSettings } from "@/lib/settings";
import { capabilitiesSatisfied, usePluginRegistry } from "@/plugins/registry";
import type { PluginNavItem } from "@/plugins/types";
import { useCurrentPermissions } from "@/lib/permissions";
import {
  useArchivedConversations,
  useConversations,
  useCreateConversation,
  useDeleteConversation,
  useRenameConversation,
  type ConversationInfo,
} from "@/api/queries";
import { toast } from "@/components/ui/toast";
import { formatRelativeTime } from "@/lib/utils";
import {
  CommandPalette,
  type PaletteNavTarget,
} from "@/features/command-palette/CommandPalette";

interface NavItem {
  to: string;
  label: string;
  /** Component-as-icon. FluentUI icon components accept React.SVGProps —
   *  the legacy shadcn signature ({ className?: string }) is a subset of
   *  that, so plugin-supplied lucide icons keep rendering unchanged. */
  icon: React.ComponentType<{ className?: string }>;
  end?: boolean;
  section?: "main" | "admin";
  order?: number;
}

// Cowork-style primary navigation: a small, hand-picked set of verbs the
// user reaches for most. The rest of the surfaces (Agents, Monitoring,
// ACP, Evals, Dashboard) get demoted to a collapsible "Workspace"
// section underneath. This keeps the sidebar uncluttered like Cowork's.
const PRIMARY_NAV_ITEMS: NavItem[] = [
  { to: "/chat", label: "Chat", icon: Chat16Regular, order: 0 },
  { to: "/projects", label: "Projects", icon: FolderOpen16Regular, order: 10 },
  { to: "/workflows", label: "Scheduled", icon: Clock16Regular, order: 20 },
  { to: "/monitoring", label: "Live artifacts", icon: Pulse20Regular, order: 30 },
  { to: "/settings", label: "Customize", icon: Wand16Regular, order: 40 },
];

// Secondary surfaces — kept reachable but folded into a small group so they
// don't compete with the primary verbs.
const WORKSPACE_NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Dashboard", icon: Board16Regular, end: true, order: 0 },
  { to: "/agents", label: "Agents", icon: Bot16Regular, order: 10 },
  { to: "/capabilities", label: "Capabilities", icon: Sparkle16Regular, order: 20 },
  { to: "/acp", label: "ACP Peers", icon: PlugConnected16Regular, order: 30 },
  { to: "/workflows", label: "Workflows", icon: Flow16Regular, order: 40 },
  { to: "/evals", label: "Evals", icon: Beaker16Regular, order: 50 },
];

const BUILTIN_PAGE_TITLES: Record<string, string> = {
  "/": "Dashboard",
  "/agents": "Agents",
  "/chat": "Chat",
  "/projects": "Projects",
  "/monitoring": "Monitoring",
  "/acp": "ACP Peers",
  "/workflows": "Workflows",
  "/capabilities": "Capabilities",
  "/evals": "Evals",
  "/settings": "Settings",
};

const COLLAPSED_KEY = "taskforce.sidebar.collapsed";
const WORKSPACE_OPEN_KEY = "taskforce.sidebar.workspaceOpen";

// Each built-in admin path requires one of these permissions. The admin
// section is rendered only when the current user has at least one of them.
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
  const label = `Switch to ${theme === "dark" ? "light" : "dark"} theme`;
  return (
    <Button
      appearance="subtle"
      icon={theme === "dark" ? <WeatherSunny16Regular /> : <WeatherMoon16Regular />}
      onClick={toggle}
      aria-label={label}
      title={label}
    />
  );
}

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------

interface SidebarProps {
  collapsed: boolean;
  /** When omitted, the collapse toggle is hidden — used inside the
   *  mobile Drawer, where the drawer's own close affordance already exists. */
  onToggle?: () => void;
  primaryItems: NavItem[];
  workspaceItems: NavItem[];
  adminItems: NavItem[];
}

function SidebarNavRow({
  item,
  collapsed,
  onNavigate,
}: {
  item: NavItem;
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  return (
    <NavLink
      to={item.to}
      end={item.end}
      title={collapsed ? item.label : undefined}
      onClick={onNavigate}
      className={({ isActive }) =>
        cn(
          "group flex items-center gap-2.5 rounded-md text-sm font-medium transition-colors",
          collapsed ? "justify-center p-2" : "px-2.5 py-1.5",
          isActive
            ? "bg-accent text-foreground"
            : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
        )
      }
    >
      <item.icon />
      {collapsed ? null : <span className="truncate">{item.label}</span>}
    </NavLink>
  );
}

function PrimaryNav({
  items,
  collapsed,
  onNavigate,
}: {
  items: NavItem[];
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  return (
    <div className="space-y-0.5">
      {items.map((item) => (
        <SidebarNavRow
          key={item.to}
          item={item}
          collapsed={collapsed}
          onNavigate={onNavigate}
        />
      ))}
    </div>
  );
}

function NewTaskButton({
  collapsed,
  onNavigate,
}: {
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  const navigate = useNavigate();
  const create = useCreateConversation();
  const onClick = async () => {
    onNavigate?.();
    try {
      const conv = await create.mutateAsync({ channel: "rest" });
      navigate(`/chat/${encodeURIComponent(conv.conversation_id)}`);
    } catch {
      // The create flow can fail (e.g. unauthenticated); the chat-empty
      // state will handle it next when the user lands there manually.
      navigate("/chat");
    }
  };

  if (collapsed) {
    return (
      <Button
        appearance="primary"
        icon={<Add20Regular />}
        onClick={onClick}
        disabled={create.isPending}
        aria-label="New task"
        title="New task"
        className="mx-auto"
      />
    );
  }
  return (
    <Button
      appearance="primary"
      icon={<Add16Regular />}
      onClick={onClick}
      disabled={create.isPending}
      size="small"
      className="w-full justify-start"
    >
      New task
    </Button>
  );
}

// Time buckets for the history list. Rendered in this order; empty
// buckets are skipped.
const HISTORY_BUCKETS = [
  "Today",
  "Yesterday",
  "Previous 7 days",
  "Older",
] as const;
type HistoryBucket = (typeof HISTORY_BUCKETS)[number];

function bucketOf(iso: string): HistoryBucket {
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return "Older";
  const now = new Date();
  const startOfToday = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  ).getTime();
  const DAY = 86_400_000;
  if (t >= startOfToday) return "Today";
  if (t >= startOfToday - DAY) return "Yesterday";
  if (t >= startOfToday - 7 * DAY) return "Previous 7 days";
  return "Older";
}

function RecentsSection({
  collapsed,
  activeId,
  onNavigate,
}: {
  collapsed: boolean;
  activeId: string | undefined;
  onNavigate?: () => void;
}) {
  const conversations = useConversations();
  const archived = useArchivedConversations(10);
  const [query, setQuery] = useState("");

  if (collapsed) return null;

  const q = query.trim().toLowerCase();
  const all = conversations.data ?? [];
  const filtered = q
    ? all.filter((c) =>
        (c.topic || c.channel || c.conversation_id).toLowerCase().includes(q),
      )
    : all;
  // Newest first, then split into time buckets for scannability.
  const sorted = [...filtered].sort(
    (a, b) =>
      new Date(b.last_activity).getTime() - new Date(a.last_activity).getTime(),
  );
  const groups = new Map<HistoryBucket, ConversationInfo[]>();
  for (const c of sorted) {
    const b = bucketOf(c.last_activity);
    const list = groups.get(b);
    if (list) list.push(c);
    else groups.set(b, [c]);
  }

  return (
    <div className="mt-4 flex min-h-0 flex-1 flex-col">
      <div className="px-1 pb-2">
        <SearchBox
          size="small"
          placeholder="Search conversations"
          value={query}
          onChange={(_, data) => setQuery(data.value)}
          className="w-full"
        />
      </div>
      <div className="min-h-0 flex-1 overflow-auto scrollbar-thin">
        {conversations.isLoading ? (
          <div className="space-y-1 px-1">
            <Skeleton className="h-9" />
            <Skeleton className="h-9" />
            <Skeleton className="h-9" />
          </div>
        ) : sorted.length > 0 ? (
          HISTORY_BUCKETS.filter((b) => groups.has(b)).map((bucket) => (
            <div key={bucket} className="mb-2">
              <p className="px-2.5 pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                {bucket}
              </p>
              <ul className="space-y-0.5">
                {groups.get(bucket)!.map((c) => (
                  <li key={c.conversation_id}>
                    <RecentItem
                      conversation={c}
                      active={c.conversation_id === activeId}
                      onNavigate={onNavigate}
                    />
                  </li>
                ))}
              </ul>
            </div>
          ))
        ) : (
          <p className="px-2.5 text-xs text-muted-foreground">
            {q ? "No matching conversations." : "No conversations yet."}
          </p>
        )}

        {archived.data && archived.data.length > 0 ? (
          <details className="mt-3 px-1">
            <summary className="cursor-pointer list-none rounded-md px-1.5 py-1 text-[11px] text-muted-foreground hover:bg-accent/40 hover:text-foreground">
              <span className="inline-flex items-center gap-1.5">
                <Archive16Regular />
                Archived ({archived.data.length})
              </span>
            </summary>
            <ul className="mt-1 space-y-0.5">
              {archived.data.map((c) => (
                <li key={c.conversation_id}>
                  <RecentItem
                    conversation={{
                      conversation_id: c.conversation_id,
                      topic: c.topic,
                      channel: "",
                      message_count: c.message_count,
                      last_activity: c.archived_at,
                      started_at: c.started_at,
                      project_id: c.project_id ?? null,
                    }}
                    active={false}
                    muted
                    onNavigate={onNavigate}
                  />
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </div>
    </div>
  );
}

function RecentItem({
  conversation: c,
  active,
  muted,
  onNavigate,
}: {
  conversation: ConversationInfo;
  active: boolean;
  muted?: boolean;
  onNavigate?: () => void;
}) {
  const navigate = useNavigate();
  const rename = useRenameConversation();
  const del = useDeleteConversation();
  const title = c.topic || c.channel || c.conversation_id;
  const [renameOpen, setRenameOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [draft, setDraft] = useState(c.topic ?? "");

  const submitRename = async () => {
    const trimmed = draft.trim();
    if (!trimmed) {
      toast.error("Rename failed", "Title must not be empty.");
      return;
    }
    setRenameOpen(false);
    if (trimmed === c.topic) return; // no-op
    try {
      await rename.mutateAsync({ id: c.conversation_id, title: trimmed });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not rename.";
      toast.error("Rename failed", message);
    }
  };

  const submitDelete = async () => {
    setDeleteOpen(false);
    try {
      await del.mutateAsync({ id: c.conversation_id });
      if (active) {
        // The conversation we were viewing just vanished — bounce to
        // the chat root so the page doesn't render a 404.
        navigate("/chat");
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not delete.";
      toast.error("Delete failed", message);
    }
  };

  return (
    <div
      className={cn(
        "group relative flex items-center rounded-md transition-colors",
        active
          ? "bg-accent text-foreground"
          : muted
            ? "text-muted-foreground/70 hover:bg-accent/40 hover:text-foreground"
            : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
      )}
    >
      <Link
        to={`/chat/${encodeURIComponent(c.conversation_id)}`}
        onClick={onNavigate}
        className="block min-w-0 flex-1 px-2.5 py-1.5"
        title={`${title} · ${formatRelativeTime(c.last_activity)}`}
      >
        <div className="truncate text-sm leading-snug">{title}</div>
        <div className="truncate text-[11px] text-muted-foreground/80">
          {formatRelativeTime(c.last_activity)}
        </div>
      </Link>
      {/* Overflow menu. On pointer devices (md+) it hover/focus-reveals to
       *  keep rows lean; on touch (mobile Drawer, no hover) it stays
       *  visible so Rename/Delete remain reachable. Both open Fluent
       *  dialogs (no window.prompt). */}
      <div className="shrink-0 pr-1 opacity-100 transition-opacity md:opacity-0 md:group-hover:opacity-100 md:focus-within:opacity-100">
        <Menu>
          <MenuTrigger disableButtonEnhancement>
            <button
              type="button"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
              }}
              className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
              aria-label="Conversation actions"
              title="Actions"
            >
              <MoreHorizontal16Regular />
            </button>
          </MenuTrigger>
          <MenuPopover>
            <MenuList>
              <MenuItem
                icon={<Edit16Regular />}
                onClick={() => {
                  setDraft(c.topic ?? "");
                  setRenameOpen(true);
                }}
              >
                Rename
              </MenuItem>
              <MenuItem
                icon={<Delete16Regular />}
                onClick={() => setDeleteOpen(true)}
                className="text-destructive"
              >
                Delete
              </MenuItem>
            </MenuList>
          </MenuPopover>
        </Menu>
      </div>

      <Dialog open={renameOpen} onOpenChange={setRenameOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Rename conversation</DialogTitle>
          </DialogHeader>
          <Input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Conversation title"
            onKeyDown={(e) => {
              if (e.key === "Enter") void submitRename();
            }}
            autoFocus
          />
          <DialogFooter>
            <UIButton variant="ghost" onClick={() => setRenameOpen(false)}>
              Cancel
            </UIButton>
            <UIButton onClick={() => void submitRename()} disabled={rename.isPending}>
              Save
            </UIButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete conversation</DialogTitle>
            <DialogDescription>
              “{title}” will be permanently deleted. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <UIButton variant="ghost" onClick={() => setDeleteOpen(false)}>
              Cancel
            </UIButton>
            <UIButton
              variant="destructive"
              onClick={() => void submitDelete()}
              disabled={del.isPending}
              className="!bg-destructive !text-destructive-foreground hover:!bg-destructive/90"
            >
              Delete
            </UIButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function WorkspaceSection({
  items,
  collapsed,
  onNavigate,
}: {
  items: NavItem[];
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  const [open, setOpen] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem(WORKSPACE_OPEN_KEY) === "1";
  });

  useEffect(() => {
    window.localStorage.setItem(WORKSPACE_OPEN_KEY, open ? "1" : "0");
  }, [open]);

  if (items.length === 0) return null;

  if (collapsed) {
    return (
      <div className="space-y-0.5">
        {items.map((item) => (
          <SidebarNavRow
            key={item.to}
            item={item}
            collapsed
            onNavigate={onNavigate}
          />
        ))}
      </div>
    );
  }

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between rounded-md px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70 hover:text-foreground"
        aria-expanded={open}
      >
        <span>Workspace</span>
        <ChevronDown16Regular
          className={cn("transition-transform", !open && "-rotate-90")}
          aria-hidden
        />
      </button>
      {open ? (
        <div className="mt-1 space-y-0.5">
          {items.map((item) => (
            <SidebarNavRow
              key={item.to}
              item={item}
              collapsed={collapsed}
              onNavigate={onNavigate}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function AdminSection({
  items,
  collapsed,
  onNavigate,
}: {
  items: NavItem[];
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  if (items.length === 0) return null;
  return (
    <div className="mt-2">
      {!collapsed ? (
        <p className="px-2.5 pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
          Admin
        </p>
      ) : null}
      <div className="space-y-0.5">
        {items.map((item) => (
          <SidebarNavRow
            key={item.to}
            item={item}
            collapsed={collapsed}
            onNavigate={onNavigate}
          />
        ))}
      </div>
    </div>
  );
}

function UserFooter({ collapsed }: { collapsed: boolean }) {
  const navigate = useNavigate();
  const setApiToken = useSettings((s) => s.setApiToken);
  const handleLogout = () => {
    setApiToken("");
    navigate("/login", { replace: true });
  };

  if (collapsed) {
    return (
      <div className="flex flex-col items-center gap-1">
        <ThemeToggle />
        <Button
          appearance="subtle"
          icon={<SignOut20Regular />}
          onClick={handleLogout}
          aria-label="Sign out"
          title="Sign out"
        />
      </div>
    );
  }
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-2 px-1">
        <HealthIndicator />
        <ThemeToggle />
      </div>
      <div className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary">
          <Person16Regular />
        </span>
        <div className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
          Signed in
        </div>
        <Button
          appearance="subtle"
          icon={<SignOut20Regular />}
          onClick={handleLogout}
          aria-label="Sign out"
          title="Sign out"
        />
      </div>
    </div>
  );
}

/**
 * Sidebar body — shared between the desktop ``<aside>`` and the mobile
 * Drawer. The desktop variant supports a collapsed (icon-only) mode; the
 * mobile variant always renders fully expanded since the Drawer itself
 * provides the slim/expanded affordance.
 */
function SidebarBody({
  collapsed,
  onToggle,
  primaryItems,
  workspaceItems,
  adminItems,
  onNavigate,
  showCollapseToggle,
}: SidebarProps & {
  onNavigate?: () => void;
  showCollapseToggle: boolean;
}) {
  const { pathname } = useLocation();
  // Highlight the active conversation in the Recents list when we're on
  // /chat/:id. Reading the param out of the URL ourselves avoids
  // threading state from the chat page back up here.
  const activeConversationId = useMemo(() => {
    const match = pathname.match(/^\/chat\/([^/]+)/);
    return match ? decodeURIComponent(match[1]) : undefined;
  }, [pathname]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div
        className={cn(
          "flex h-14 items-center gap-2 border-b border-border",
          collapsed ? "justify-center px-2" : "px-3",
        )}
      >
        <Sparkle20Regular className="text-primary" />
        {collapsed ? null : (
          <span className="text-base font-semibold tracking-tight">Taskforce</span>
        )}
      </div>

      <div className={cn(collapsed ? "p-1.5" : "px-3 py-3")}>
        <NewTaskButton collapsed={collapsed} onNavigate={onNavigate} />
      </div>

      <nav
        className={cn(
          "flex min-h-0 flex-1 flex-col",
          collapsed ? "px-1.5 pb-2" : "px-2 pb-2",
        )}
      >
        <PrimaryNav
          items={primaryItems}
          collapsed={collapsed}
          onNavigate={onNavigate}
        />

        <RecentsSection
          collapsed={collapsed}
          activeId={activeConversationId}
          onNavigate={onNavigate}
        />

        <div className="mt-3 space-y-1">
          <WorkspaceSection
            items={workspaceItems}
            collapsed={collapsed}
            onNavigate={onNavigate}
          />
          <AdminSection
            items={adminItems}
            collapsed={collapsed}
            onNavigate={onNavigate}
          />
        </div>
      </nav>

      <div
        className={cn(
          "border-t border-border",
          collapsed ? "p-1.5" : "px-3 py-2",
        )}
      >
        <UserFooter collapsed={collapsed} />
        {showCollapseToggle && onToggle ? (
          <Button
            appearance="subtle"
            icon={
              collapsed ? (
                <PanelLeftExpand16Regular />
              ) : (
                <PanelLeftContract16Regular />
              )
            }
            onClick={onToggle}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className={cn("mt-2 w-full", !collapsed && "justify-start")}
            size="small"
          >
            {collapsed ? null : "Collapse"}
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function Sidebar(props: SidebarProps) {
  return (
    <aside
      className={cn(
        "hidden md:flex shrink-0 flex-col border-r border-border bg-card/40 transition-[width] duration-150",
        props.collapsed ? "w-14" : "w-64",
      )}
    >
      <SidebarBody {...props} showCollapseToggle />
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
  // Mobile sidebar drawer state — only used below the ``md`` breakpoint
  // where the inline aside is hidden. Closing the drawer on every
  // navigation is handled via the ``onNavigate`` callback threaded into
  // the sidebar body.
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  // Auto-close the mobile drawer whenever the route changes. Without
  // this, navigating from the drawer would leave it open behind the
  // new page.
  useEffect(() => {
    setMobileNavOpen(false);
  }, [pathname]);

  // Global Cmd/Ctrl-K toggles the command palette — the "find anything"
  // shortcut. Bound once at the shell so it works from any page.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const { primaryItems, workspaceItems, adminItems, pageTitles } = useMemo(() => {
    // Plugin nav items that don't explicitly target the admin section
    // get appended to the Workspace group — that keeps the primary
    // five-item nav stable.
    const collected: NavItem[] = [];
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

    const primaryItems = [...PRIMARY_NAV_ITEMS].sort(sortByOrder);
    const workspaceItems = [
      ...WORKSPACE_NAV_ITEMS,
      ...collected.filter((it) => (it.section ?? "main") === "main"),
    ].sort(sortByOrder);
    const adminItems = collected
      .filter((it) => it.section === "admin")
      .filter((it) => {
        const required = ADMIN_PATH_PERMISSIONS[it.to];
        return required ? permissions.can(required) : true;
      })
      .sort(sortByOrder);

    const pageTitles: Record<string, string> = { ...BUILTIN_PAGE_TITLES };
    for (const item of [...primaryItems, ...workspaceItems, ...adminItems]) {
      pageTitles[item.to] = item.label;
    }

    return { primaryItems, workspaceItems, adminItems, pageTitles };
  }, [plugins, activeCapabilities, permissions]);

  const title = getPageTitle(pathname, pageTitles);
  // Flat, de-duplicated nav targets for the command palette.
  const paletteNavTargets = useMemo<PaletteNavTarget[]>(() => {
    const seen = new Set<string>();
    const out: PaletteNavTarget[] = [];
    for (const item of [...primaryItems, ...workspaceItems, ...adminItems]) {
      if (seen.has(item.to)) continue;
      seen.add(item.to);
      out.push({ to: item.to, label: item.label });
    }
    return out;
  }, [primaryItems, workspaceItems, adminItems]);
  // On the Cowork-style pages (Chat, Projects) we hide the global header
  // — each page renders its own breadcrumb / title inline. Other pages
  // keep the lean top bar so users always know where they are.
  const hideHeader =
    pathname.startsWith("/chat") || pathname.startsWith("/projects");

  useEffect(() => {
    window.localStorage.setItem(COLLAPSED_KEY, collapsed ? "1" : "0");
  }, [collapsed]);

  return (
    <div className="flex h-full">
      <Sidebar
        collapsed={collapsed}
        onToggle={() => setCollapsed((c) => !c)}
        primaryItems={primaryItems}
        workspaceItems={workspaceItems}
        adminItems={adminItems}
      />

      {/* Mobile sidebar drawer (below md). FluentUI Drawer in overlay
       *  type renders modally; `open` is the single source of truth. */}
      <Drawer
        type="overlay"
        position="start"
        size="medium"
        open={mobileNavOpen}
        onOpenChange={(_, { open }) => setMobileNavOpen(open)}
      >
        <DrawerHeader className="sr-only">
          <DrawerHeaderTitle>Navigation</DrawerHeaderTitle>
        </DrawerHeader>
        <DrawerBody className="!p-0">
          <SidebarBody
            collapsed={false}
            primaryItems={primaryItems}
            workspaceItems={workspaceItems}
            adminItems={adminItems}
            showCollapseToggle={false}
            onNavigate={() => setMobileNavOpen(false)}
          />
        </DrawerBody>
      </Drawer>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile top bar — always visible below ``md`` so the
         *  hamburger is reachable on every page (chat included). */}
        <header className="flex h-12 shrink-0 items-center gap-2 border-b border-border bg-background/80 px-3 backdrop-blur md:hidden">
          <Button
            appearance="subtle"
            icon={<Navigation20Regular />}
            aria-label="Open navigation"
            onClick={() => setMobileNavOpen(true)}
          />
          <h1 className="truncate text-sm font-semibold tracking-tight">
            {title}
          </h1>
        </header>

        {hideHeader ? null : (
          // Desktop header (md+). Health indicator + theme toggle live
          // in the sidebar footer now — the top bar is reserved for the
          // page title to keep page chrome lean and Cowork-like.
          <header className="hidden h-14 shrink-0 items-center gap-4 border-b border-border bg-background/80 px-6 backdrop-blur md:flex">
            <h1 className="text-base font-semibold tracking-tight">{title}</h1>
          </header>
        )}

        <main className="relative min-h-0 flex-1 overflow-auto scrollbar-thin">
          {hideHeader ? (
            // Chat owns its layout entirely (full-bleed, no padding).
            <Outlet />
          ) : (
            <div className="mx-auto flex h-full min-h-0 w-full max-w-[1600px] flex-col p-6">
              <Outlet />
            </div>
          )}
        </main>
      </div>

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        navTargets={paletteNavTargets}
      />
    </div>
  );
}
