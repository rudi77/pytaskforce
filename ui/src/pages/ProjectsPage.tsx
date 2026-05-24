import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Add16Regular,
  Add20Regular,
  Chat16Regular,
  Delete16Regular,
  FolderOpen20Regular,
  MoreHorizontal20Regular,
  Search20Regular,
  TextSortAscending20Regular,
} from "@fluentui/react-icons";
import { Button, Input } from "@fluentui/react-components";

import { EmptyState } from "@/components/EmptyState";
import { ApiError } from "@/api/client";
import {
  useConversations,
  useCreateConversation,
  useDeleteProject,
  useHealth,
  useProjects,
  type ConversationInfo,
  type Project,
} from "@/api/queries";
import { toast } from "@/components/ui/toast";
import { formatRelativeTime } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { NewProjectModal } from "@/features/projects/NewProjectModal";

/**
 * Cowork-style Projects page.
 *
 * A project is a directory on disk that holds CLAUDE.md, skills/ and
 * any free-form context the agent needs for that body of work.
 * Clicking a project starts a new conversation linked to the project
 * so the agent's working_dir is rooted at the project's path.
 */

type SortKey = "recent" | "name";

export default function ProjectsPage() {
  const navigate = useNavigate();
  const projects = useProjects();
  const conversations = useConversations();
  const health = useHealth();
  const createConversation = useCreateConversation();
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("recent");
  const [modalOpen, setModalOpen] = useState(false);

  // Index conversations by project_id once so each tile renders without
  // scanning the full list. Active conversations only — archived ones
  // are kept out to avoid noise on a freshly opened project page.
  const conversationsByProject = useMemo(() => {
    const map = new Map<string, ConversationInfo[]>();
    for (const c of conversations.data ?? []) {
      if (!c.project_id) continue;
      const bucket = map.get(c.project_id) ?? [];
      bucket.push(c);
      map.set(c.project_id, bucket);
    }
    // Newest first inside each bucket.
    for (const list of map.values()) {
      list.sort((a, b) => (a.last_activity < b.last_activity ? 1 : -1));
    }
    return map;
  }, [conversations.data]);

  const visible = useMemo(() => {
    const list = projects.data ?? [];
    const filtered = query
      ? list.filter((p) =>
          [p.name, p.path]
            .join("\n")
            .toLowerCase()
            .includes(query.toLowerCase()),
        )
      : [...list];
    if (sort === "name") {
      filtered.sort((a, b) => a.name.localeCompare(b.name));
    } else {
      filtered.sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
    }
    return filtered;
  }, [projects.data, query, sort]);

  const startConversationFor = async (project: Project) => {
    try {
      const conv = await createConversation.mutateAsync({
        channel: "rest",
        project_id: project.project_id,
      });
      navigate(`/chat/${encodeURIComponent(conv.conversation_id)}`);
    } catch (err) {
      toast.error(
        "Conversation konnte nicht gestartet werden",
        err instanceof ApiError ? err.message : (err as Error).message,
      );
    }
  };

  /**
   * Default action when clicking a project's title/folder area.
   *
   * If the project already has an active conversation, jump straight
   * into the most recent one — the obvious "resume my work" affordance.
   * Only create a fresh chat when there is nothing to resume; otherwise
   * every click would silently fork a new conversation and the user's
   * earlier work would scroll off-screen in the sidebar Recents list.
   * Explicit "New conversation" is exposed on the tile itself.
   */
  const openProject = (project: Project) => {
    const existing = conversationsByProject.get(project.project_id) ?? [];
    if (existing.length > 0) {
      navigate(`/chat/${encodeURIComponent(existing[0].conversation_id)}`);
      return;
    }
    void startConversationFor(project);
  };

  return (
    <div className="mx-auto flex h-full min-h-0 w-full max-w-6xl flex-col gap-6 p-6">
      <header className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight">Projects</h1>
        <div className="flex items-center gap-2">
          <Button
            appearance="subtle"
            size="small"
            icon={<TextSortAscending20Regular />}
            onClick={() => setSort((s) => (s === "recent" ? "name" : "recent"))}
            title={`Sort by ${sort === "recent" ? "name" : "recent"}`}
          >
            {sort === "recent" ? "Recent" : "Name"}
          </Button>
          <Input
            contentBefore={<Search20Regular />}
            value={query}
            onChange={(_, data) => setQuery(data.value)}
            placeholder="Search…"
            className="w-48"
          />
          <Button
            appearance="primary"
            icon={<Add20Regular />}
            onClick={() => setModalOpen(true)}
          >
            New project
          </Button>
        </div>
      </header>

      <DefaultWorkspaceHint healthData={health.data} />

      <section className="min-h-0 flex-1">
        {projects.isLoading ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <CardSkeleton />
            <CardSkeleton />
            <CardSkeleton />
          </div>
        ) : projects.isError ? (
          <EmptyState
            title="Projects konnten nicht geladen werden"
            description={
              projects.error instanceof ApiError
                ? projects.error.message
                : "Backend antwortet nicht."
            }
            className="max-w-md"
          />
        ) : visible.length === 0 ? (
          <EmptyState
            title={query ? "Keine Treffer" : "Noch keine Projekte"}
            description={
              query
                ? "Versuch's mit einem anderen Suchbegriff."
                : "Lege ein neues Projekt an — entweder von Grund auf neu oder mit einem vorhandenen Ordner."
            }
            action={
              query ? undefined : (
                <Button
                  appearance="primary"
                  icon={<Add20Regular />}
                  onClick={() => setModalOpen(true)}
                >
                  New project
                </Button>
              )
            }
            className="max-w-md"
          />
        ) : (
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {visible.map((project) => (
              <li key={project.project_id}>
                <ProjectTile
                  project={project}
                  conversations={
                    conversationsByProject.get(project.project_id) ?? []
                  }
                  onOpen={() => openProject(project)}
                  onNewConversation={() => startConversationFor(project)}
                  onOpenConversation={(id) =>
                    navigate(`/chat/${encodeURIComponent(id)}`)
                  }
                />
              </li>
            ))}
          </ul>
        )}
      </section>

      <NewProjectModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        onCreated={(project) => {
          toast.success("Projekt erstellt", project.path);
          startConversationFor(project);
        }}
      />
    </div>
  );
}

// Cap shown so a long-running project with dozens of chats doesn't push
// the action row off-screen. Anything beyond is rolled into a "+N more"
// hint that scrolls the user to the sidebar Recents view (the canonical
// full list lives there).
const TILE_MAX_CONVERSATIONS = 4;

function ProjectTile({
  project,
  conversations,
  onOpen,
  onNewConversation,
  onOpenConversation,
}: {
  project: Project;
  conversations: ConversationInfo[];
  onOpen: () => void;
  onNewConversation: () => void;
  onOpenConversation: (conversationId: string) => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const deleteProject = useDeleteProject();

  const onDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (
      !confirm(
        `'${project.name}' aus der Liste entfernen?\n\nDas Verzeichnis auf der Platte bleibt erhalten.`,
      )
    ) {
      setMenuOpen(false);
      return;
    }
    try {
      await deleteProject.mutateAsync(project.project_id);
      toast.success("Projekt entfernt", project.name);
    } catch (err) {
      toast.error(
        "Konnte Projekt nicht entfernen",
        err instanceof ApiError ? err.message : (err as Error).message,
      );
    }
    setMenuOpen(false);
  };

  const visibleConversations = conversations.slice(0, TILE_MAX_CONVERSATIONS);
  const hiddenCount = conversations.length - visibleConversations.length;

  return (
    <div
      className={cn(
        "group relative flex h-full w-full flex-col items-start gap-3 rounded-xl border border-border bg-card px-4 py-4 text-left transition-colors",
        "hover:border-primary/40 hover:bg-accent/40",
      )}
    >
      <button
        type="button"
        onClick={onOpen}
        className="flex w-full items-center gap-2 text-left"
        title={
          conversations.length > 0
            ? `Open last conversation (${conversations.length} total)`
            : "Start a new conversation"
        }
      >
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <FolderOpen20Regular />
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold text-foreground">
            {project.name}
          </h3>
          <p className="truncate font-mono text-[11px] text-muted-foreground" title={project.path}>
            {project.path}
          </p>
        </div>
      </button>

      {/* Conversation list — only renders when the project actually has
       *  past chats, so a freshly created project doesn't show an empty
       *  "Conversations" block. */}
      {visibleConversations.length > 0 ? (
        <ul className="flex w-full flex-col gap-0.5">
          {visibleConversations.map((c) => (
            <li key={c.conversation_id}>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onOpenConversation(c.conversation_id);
                }}
                className="flex w-full items-center gap-2 truncate rounded-md px-2 py-1 text-left text-xs text-muted-foreground hover:bg-accent/60 hover:text-foreground"
                title={c.topic || c.conversation_id}
              >
                <Chat16Regular />
                <span className="min-w-0 flex-1 truncate">
                  {c.topic || `Conversation ${c.conversation_id.slice(0, 8)}`}
                </span>
                <span className="shrink-0 text-[10px] text-muted-foreground/70">
                  {formatRelativeTime(c.last_activity)}
                </span>
              </button>
            </li>
          ))}
          {hiddenCount > 0 ? (
            <li className="px-2 pt-0.5">
              <Link
                to={`/projects/${encodeURIComponent(project.project_id)}`}
                onClick={(e) => e.stopPropagation()}
                className="text-[10px] text-muted-foreground/80 hover:text-foreground hover:underline"
              >
                +{hiddenCount} more — View all
              </Link>
            </li>
          ) : null}
        </ul>
      ) : null}

      <div className="flex w-full items-center justify-between">
        <p className="text-xs text-muted-foreground">
          {formatRelativeTime(project.created_at)}
        </p>
        <div className="flex items-center gap-1">
          <Link
            to={`/projects/${encodeURIComponent(project.project_id)}`}
            onClick={(e) => e.stopPropagation()}
            className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-[11px] text-muted-foreground hover:bg-accent/60 hover:text-foreground"
            title="View all conversations in this project"
          >
            <Chat16Regular />
            View all
          </Link>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onNewConversation();
            }}
            className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-[11px] text-muted-foreground hover:bg-accent/60 hover:text-foreground"
            title="Start a new conversation in this project"
          >
            <Add16Regular />
            New
          </button>
          {/* Custom mini-menu kept raw — Fluent Menu would change focus
           *  semantics for one disposable action; not worth the rewrite. */}
          <div className="relative">
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setMenuOpen((v) => !v);
              }}
              aria-label="Menu"
              className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <MoreHorizontal20Regular />
            </button>
            {menuOpen ? (
              <div
                onClick={(e) => e.stopPropagation()}
                className="absolute right-0 z-10 mt-1 min-w-40 rounded-md border border-border bg-popover p-1 shadow-md"
              >
                <button
                  type="button"
                  onClick={onDelete}
                  disabled={deleteProject.isPending}
                  className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-xs text-destructive hover:bg-destructive/10"
                >
                  <Delete16Regular />
                  Aus Liste entfernen
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

function DefaultWorkspaceHint({
  healthData,
}: {
  healthData: ReturnType<typeof useHealth>["data"];
}) {
  const checks = (healthData?.checks ?? {}) as Record<string, unknown>;
  const wd =
    (checks.working_dir as string | undefined) ??
    (checks.work_dir as string | undefined) ??
    null;
  if (!wd) return null;
  return (
    <p className="text-[11px] text-muted-foreground">
      Standard-Workspace (für Conversations ohne Projekt):{" "}
      <span className="font-mono">{wd}</span>
    </p>
  );
}

function CardSkeleton() {
  return (
    <div className="h-28 animate-pulse rounded-xl border border-border bg-card/60" />
  );
}
