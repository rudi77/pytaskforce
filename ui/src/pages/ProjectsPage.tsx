import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowDownAZ,
  FolderOpen,
  Plus,
  Search,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/EmptyState";
import {
  useConversations,
  useCreateConversation,
  useHealth,
  type ConversationInfo,
} from "@/api/queries";
import { formatRelativeTime } from "@/lib/utils";
import { cn } from "@/lib/utils";

/**
 * Cowork-style Projects grid.
 *
 * Until the framework gets a real per-project working directory (Phase 2 of
 * the Cowork roadmap, see ``docs/cowork-comparison.md``), a "project" is
 * derived from the conversation channel — REST chat sessions, Telegram
 * threads, Teams, etc. Each card opens the most-recent conversation for
 * that channel. The page also surfaces the resolved workspace (from
 * ``/health.checks.working_dir`` when present) as the implicit "default
 * project" so the user always sees at least one card.
 */

interface ProjectCard {
  id: string;
  title: string;
  subtitle: string;
  lastActivity: string;
  conversationCount: number;
  primaryConversation: ConversationInfo;
}

function buildProjects(conversations: ConversationInfo[]): ProjectCard[] {
  const byKey = new Map<string, ConversationInfo[]>();
  for (const c of conversations) {
    const key = c.channel || "rest";
    const bucket = byKey.get(key) ?? [];
    bucket.push(c);
    byKey.set(key, bucket);
  }

  const projects: ProjectCard[] = [];
  for (const [key, list] of byKey.entries()) {
    list.sort((a, b) => (a.last_activity < b.last_activity ? 1 : -1));
    const head = list[0];
    projects.push({
      id: key,
      title: titleForChannel(key),
      subtitle: subtitleFor(list),
      lastActivity: head.last_activity,
      conversationCount: list.length,
      primaryConversation: head,
    });
  }
  projects.sort((a, b) => (a.lastActivity < b.lastActivity ? 1 : -1));
  return projects;
}

function titleForChannel(channel: string): string {
  switch (channel) {
    case "rest":
      return "Web Chat";
    case "telegram":
      return "Telegram";
    case "teams":
      return "Microsoft Teams";
    case "slack":
      return "Slack";
    case "":
      return "Workspace";
    default:
      return channel.charAt(0).toUpperCase() + channel.slice(1);
  }
}

function subtitleFor(list: ConversationInfo[]): string {
  if (list.length === 1) return "1 conversation";
  return `${list.length} conversations`;
}

type SortKey = "recent" | "name";

export default function ProjectsPage() {
  const navigate = useNavigate();
  const conversations = useConversations();
  const health = useHealth();
  const create = useCreateConversation();
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("recent");

  const projects = useMemo(() => {
    const built = buildProjects(conversations.data ?? []);
    const filtered = query
      ? built.filter((p) =>
          p.title.toLowerCase().includes(query.toLowerCase()),
        )
      : built;
    if (sort === "name") {
      filtered.sort((a, b) => a.title.localeCompare(b.title));
    }
    return filtered;
  }, [conversations.data, query, sort]);

  // Implicit workspace card from /health — surfaced even when no
  // conversations exist yet, so the user always sees their working
  // directory.
  const workspaceCard = useMemo(() => {
    const checks = (health.data?.checks ?? {}) as Record<string, unknown>;
    const wd =
      (checks.working_dir as string | undefined) ??
      (checks.work_dir as string | undefined) ??
      null;
    if (!wd && !health.data?.default_profile) return null;
    return {
      title: wd ?? health.data?.default_profile ?? "Workspace",
      path: wd,
      profile: health.data?.default_profile,
    };
  }, [health.data]);

  const onCreate = async () => {
    try {
      const conv = await create.mutateAsync({ channel: "rest" });
      navigate(`/chat/${encodeURIComponent(conv.conversation_id)}`);
    } catch {
      // Toast handled by the mutation defaults; user can retry.
    }
  };

  return (
    <div className="mx-auto flex h-full min-h-0 w-full max-w-6xl flex-col gap-6 p-6">
      <header className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight">Projects</h1>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setSort((s) => (s === "recent" ? "name" : "recent"))}
            className="inline-flex h-9 items-center gap-1.5 rounded-md border border-input bg-background px-2.5 text-xs text-muted-foreground hover:text-foreground"
            title={`Sort by ${sort === "recent" ? "name" : "recent"}`}
          >
            <ArrowDownAZ className="h-4 w-4" />
            {sort === "recent" ? "Recent" : "Name"}
          </button>
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search…"
              className="h-9 w-48 pl-8"
            />
          </div>
          <Button onClick={onCreate} disabled={create.isPending}>
            <Plus className="h-4 w-4" />
            New project
          </Button>
        </div>
      </header>

      {workspaceCard ? (
        <section>
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
            Workspace
          </p>
          <WorkspaceTile
            title={workspaceCard.title}
            path={workspaceCard.path}
            profile={workspaceCard.profile}
            onOpen={() => navigate("/chat")}
          />
        </section>
      ) : null}

      <section className="min-h-0 flex-1">
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
          Recent
        </p>
        {conversations.isLoading ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <CardSkeleton />
            <CardSkeleton />
            <CardSkeleton />
          </div>
        ) : projects.length === 0 ? (
          <EmptyState
            title="No projects yet"
            description="Projects appear here once you start a conversation. Click ‘New project’ to get going."
            action={
              <Button onClick={onCreate} disabled={create.isPending}>
                <Plus className="h-4 w-4" />
                New project
              </Button>
            }
            className="max-w-md"
          />
        ) : (
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {projects.map((p) => (
              <li key={p.id}>
                <ProjectTile
                  project={p}
                  onOpen={() =>
                    navigate(
                      `/chat/${encodeURIComponent(p.primaryConversation.conversation_id)}`,
                    )
                  }
                />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function ProjectTile({
  project,
  onOpen,
}: {
  project: ProjectCard;
  onOpen: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className={cn(
        "group flex h-full w-full flex-col items-start gap-3 rounded-xl border border-border bg-card px-4 py-4 text-left transition-colors",
        "hover:border-primary/40 hover:bg-accent/40",
      )}
    >
      <div className="flex w-full items-center gap-2">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <FolderOpen className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold text-foreground">
            {project.title}
          </h3>
          <p className="truncate text-xs text-muted-foreground">
            {project.subtitle}
          </p>
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        {formatRelativeTime(project.lastActivity)}
      </p>
    </button>
  );
}

function WorkspaceTile({
  title,
  path,
  profile,
  onOpen,
}: {
  title: string;
  path?: string | null;
  profile?: string | null;
  onOpen: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className={cn(
        "group flex w-full max-w-md flex-col items-start gap-2 rounded-xl border border-border bg-card px-4 py-4 text-left transition-colors",
        "hover:border-primary/40 hover:bg-accent/40",
      )}
    >
      <div className="flex w-full items-center gap-2">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <FolderOpen className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold text-foreground">
            {title}
          </h3>
          {profile ? (
            <p className="truncate text-xs text-muted-foreground">
              Default profile: {profile}
            </p>
          ) : null}
        </div>
      </div>
      {path ? (
        <p className="truncate text-[11px] text-muted-foreground" title={path}>
          {path}
        </p>
      ) : null}
    </button>
  );
}

function CardSkeleton() {
  return (
    <div className="h-24 animate-pulse rounded-xl border border-border bg-card/60" />
  );
}
