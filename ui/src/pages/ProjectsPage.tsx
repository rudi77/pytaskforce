import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowDownAZ,
  FolderOpen,
  MoreHorizontal,
  Plus,
  Search,
  Trash2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/EmptyState";
import { ApiError } from "@/api/client";
import {
  useCreateConversation,
  useDeleteProject,
  useHealth,
  useProjects,
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
  const health = useHealth();
  const createConversation = useCreateConversation();
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("recent");
  const [modalOpen, setModalOpen] = useState(false);

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
          <Button onClick={() => setModalOpen(true)}>
            <Plus className="h-4 w-4" />
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
                <Button onClick={() => setModalOpen(true)}>
                  <Plus className="h-4 w-4" />
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
                  onOpen={() => startConversationFor(project)}
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

function ProjectTile({
  project,
  onOpen,
}: {
  project: Project;
  onOpen: () => void;
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
      >
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <FolderOpen className="h-4 w-4" />
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
      <div className="flex w-full items-center justify-between">
        <p className="text-xs text-muted-foreground">
          {formatRelativeTime(project.created_at)}
        </p>
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
            <MoreHorizontal className="h-4 w-4" />
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
                <Trash2 className="h-3.5 w-3.5" />
                Aus Liste entfernen
              </button>
            </div>
          ) : null}
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
