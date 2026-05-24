import { useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import {
  Add20Regular,
  ArrowLeft20Regular,
  Chat16Regular,
  ChevronDown16Regular,
  ChevronRight16Regular,
  Delete20Regular,
  FolderOpen20Regular,
} from "@fluentui/react-icons";
import { Button } from "@fluentui/react-components";

import { EmptyState } from "@/components/EmptyState";
import { ApiError } from "@/api/client";
import {
  useArchivedConversations,
  useConversations,
  useCreateConversation,
  useDeleteConversation,
  useProject,
  type ConversationInfo,
  type ConversationSummary,
} from "@/api/queries";
import { toast } from "@/components/ui/toast";
import { formatRelativeTime } from "@/lib/utils";

/**
 * Detail view for a single project: shows every conversation linked to
 * the project (active + archived) with resume + delete affordances.
 *
 * Without this page the user can only see the four most recent active
 * conversations from the project tile on /projects, with no way to
 * inspect or clean up older history. The data already exists in the
 * backend; this page surfaces it.
 */
export default function ProjectDetailPage() {
  const { projectId = "" } = useParams<{ projectId: string }>();
  const navigate = useNavigate();

  const project = useProject(projectId);
  const active = useConversations(projectId);
  // Archived conversations are kept under a fold so a long history
  // doesn't push the active list (the thing you almost always want
  // first) off-screen.
  const archived = useArchivedConversations(50, projectId);
  const createConversation = useCreateConversation();
  const deleteConversation = useDeleteConversation();
  const [archivedOpen, setArchivedOpen] = useState(false);

  const startNewConversation = async () => {
    try {
      const conv = await createConversation.mutateAsync({
        channel: "rest",
        project_id: projectId,
      });
      navigate(`/chat/${encodeURIComponent(conv.conversation_id)}`);
    } catch (err) {
      toast.error(
        "Conversation konnte nicht gestartet werden",
        err instanceof ApiError ? err.message : (err as Error).message,
      );
    }
  };

  const onDelete = async (conversationId: string, topic: string | null) => {
    if (
      !confirm(
        `Conversation${topic ? ` "${topic}"` : ""} endgültig löschen?\n\n` +
          "Der Verlauf wird unwiderruflich entfernt.",
      )
    ) {
      return;
    }
    try {
      await deleteConversation.mutateAsync({ id: conversationId });
      toast.success("Conversation gelöscht");
    } catch (err) {
      toast.error(
        "Konnte Conversation nicht löschen",
        err instanceof ApiError ? err.message : (err as Error).message,
      );
    }
  };

  if (project.isError) {
    return (
      <div className="mx-auto w-full max-w-4xl p-6">
        <BackLink />
        <EmptyState
          title="Projekt konnte nicht geladen werden"
          description={
            project.error instanceof ApiError
              ? project.error.message
              : "Backend antwortet nicht."
          }
          className="mt-6 max-w-md"
        />
      </div>
    );
  }

  const activeList = active.data ?? [];
  const archivedList = archived.data ?? [];

  return (
    <div className="mx-auto flex h-full min-h-0 w-full max-w-4xl flex-col gap-6 p-6">
      <BackLink />

      <header className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <FolderOpen20Regular />
          </span>
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-semibold tracking-tight">
              {project.data?.name ?? "Loading…"}
            </h1>
            {project.data ? (
              <p
                className="truncate font-mono text-xs text-muted-foreground"
                title={project.data.path}
              >
                {project.data.path}
              </p>
            ) : null}
          </div>
        </div>
        <Button
          appearance="primary"
          icon={<Add20Regular />}
          onClick={startNewConversation}
          disabled={createConversation.isPending}
        >
          New conversation
        </Button>
      </header>

      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-medium text-muted-foreground">
          Active conversations
          {active.isSuccess ? (
            <span className="ml-1.5 text-xs text-muted-foreground/70">
              ({activeList.length})
            </span>
          ) : null}
        </h2>

        {active.isLoading ? (
          <ListSkeleton />
        ) : active.isError ? (
          <EmptyState
            title="Conversations konnten nicht geladen werden"
            description={
              active.error instanceof ApiError
                ? active.error.message
                : "Backend antwortet nicht."
            }
            className="max-w-md"
          />
        ) : activeList.length === 0 ? (
          <EmptyState
            title="Noch keine aktiven Conversations"
            description={'Starte mit „New conversation".'}
            className="max-w-md"
          />
        ) : (
          <ul className="flex flex-col gap-1">
            {activeList.map((c) => (
              <li key={c.conversation_id}>
                <ActiveRow
                  conversation={c}
                  onOpen={() =>
                    navigate(`/chat/${encodeURIComponent(c.conversation_id)}`)
                  }
                  onDelete={() => onDelete(c.conversation_id, c.topic)}
                  deleting={deleteConversation.isPending}
                />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="flex flex-col gap-2">
        <button
          type="button"
          onClick={() => setArchivedOpen((v) => !v)}
          className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground"
          aria-expanded={archivedOpen}
        >
          {archivedOpen ? <ChevronDown16Regular /> : <ChevronRight16Regular />}
          Archived
          {archived.isSuccess ? (
            <span className="text-xs text-muted-foreground/70">
              ({archivedList.length})
            </span>
          ) : null}
        </button>

        {archivedOpen ? (
          archived.isLoading ? (
            <ListSkeleton />
          ) : archived.isError ? (
            <EmptyState
              title="Archivierte Conversations konnten nicht geladen werden"
              description={
                archived.error instanceof ApiError
                  ? archived.error.message
                  : "Backend antwortet nicht."
              }
              className="max-w-md"
            />
          ) : archivedList.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              Keine archivierten Conversations für dieses Projekt.
            </p>
          ) : (
            <ul className="flex flex-col gap-1">
              {archivedList.map((c) => (
                <li key={c.conversation_id}>
                  <ArchivedRow
                    conversation={c}
                    onOpen={() =>
                      navigate(`/chat/${encodeURIComponent(c.conversation_id)}`)
                    }
                    onDelete={() => onDelete(c.conversation_id, c.topic || null)}
                    deleting={deleteConversation.isPending}
                  />
                </li>
              ))}
            </ul>
          )
        ) : null}
      </section>
    </div>
  );
}

function BackLink() {
  return (
    <Link
      to="/projects"
      className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft20Regular />
      Back to projects
    </Link>
  );
}

function ActiveRow({
  conversation,
  onOpen,
  onDelete,
  deleting,
}: {
  conversation: ConversationInfo;
  onOpen: () => void;
  onDelete: () => void;
  deleting: boolean;
}) {
  return (
    <div className="group flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 hover:border-primary/40">
      <button
        type="button"
        onClick={onOpen}
        className="flex min-w-0 flex-1 items-center gap-2 text-left"
        title="Continue this conversation"
      >
        <Chat16Regular className="shrink-0 text-muted-foreground" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm">
            {conversation.topic ||
              `Conversation ${conversation.conversation_id.slice(0, 8)}`}
          </p>
          <p className="text-[11px] text-muted-foreground">
            {conversation.message_count} message
            {conversation.message_count === 1 ? "" : "s"} ·{" "}
            {formatRelativeTime(conversation.last_activity)} · {conversation.channel}
          </p>
        </div>
      </button>
      <button
        type="button"
        onClick={onDelete}
        disabled={deleting}
        aria-label="Delete conversation"
        title="Delete conversation"
        className="shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-50"
      >
        <Delete20Regular />
      </button>
    </div>
  );
}

function ArchivedRow({
  conversation,
  onOpen,
  onDelete,
  deleting,
}: {
  conversation: ConversationSummary;
  onOpen: () => void;
  onDelete: () => void;
  deleting: boolean;
}) {
  return (
    <div className="group flex items-center gap-2 rounded-md border border-border/60 bg-muted/30 px-3 py-2 hover:border-primary/30">
      <button
        type="button"
        onClick={onOpen}
        className="flex min-w-0 flex-1 items-center gap-2 text-left"
        title="View archived conversation"
      >
        <Chat16Regular className="shrink-0 text-muted-foreground" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm text-muted-foreground">
            {conversation.topic ||
              `Conversation ${conversation.conversation_id.slice(0, 8)}`}
          </p>
          <p className="text-[11px] text-muted-foreground/80">
            {conversation.message_count} message
            {conversation.message_count === 1 ? "" : "s"} · archived{" "}
            {formatRelativeTime(conversation.archived_at)}
          </p>
        </div>
      </button>
      <button
        type="button"
        onClick={onDelete}
        disabled={deleting}
        aria-label="Delete conversation"
        title="Delete conversation"
        className="shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-50"
      >
        <Delete20Regular />
      </button>
    </div>
  );
}

function ListSkeleton() {
  return (
    <div className="flex flex-col gap-1">
      <div className="h-12 animate-pulse rounded-md bg-card/60" />
      <div className="h-12 animate-pulse rounded-md bg-card/60" />
    </div>
  );
}
