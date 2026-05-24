import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Archive20Regular,
  Bot20Regular,
  ChevronDown16Regular,
  Eye20Regular,
  BranchFork20Regular,
  NumberSymbol20Regular,
  ChatAdd20Regular,
  ArrowMinimize20Regular,
  PanelRightContract20Regular,
  PanelRightExpand20Regular,
  Edit20Regular,
  Delete20Regular,
} from "@fluentui/react-icons";
import { toast } from "@/components/ui/toast";
import { useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/EmptyState";
import {
  queryKeys,
  useAgents,
  useArchiveConversation,
  useCompactConversation,
  useConversationMessages,
  useConversations,
  useCreateConversation,
  useDeleteConversation,
  useForkConversation,
  useHealth,
  useRenameConversation,
  type AgentSummary,
  type ChatMessage as ChatMessageT,
  type ConversationInfo,
  type FileMetadata,
} from "@/api/queries";
import { ApiError } from "@/api/client";
import { AskUserCard } from "@/features/chat/AskUserCard";
import { ChatComposer } from "@/features/chat/ChatComposer";
import { CoworkMessage } from "@/features/chat/CoworkMessageView";
import { RightPanel } from "@/features/chat/RightPanel";
import { useChatStream } from "@/features/chat/useChatStream";
import {
  CHAT_VIEW_MODES,
  useChatPreferences,
  type ChatViewMode,
} from "@/features/chat/useChatPreferences";
import { cn, pathBasename } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Agent selection helpers
// ---------------------------------------------------------------------------

interface AgentSelection {
  key: string;
  label: string;
  agentId?: string;
  profile?: string;
}

const AGENT_DEFAULT: AgentSelection = { key: "", label: "Default" };

function buildAgentOptions(agents: AgentSummary[] | undefined): AgentSelection[] {
  if (!agents) return [AGENT_DEFAULT];
  const custom: AgentSelection[] = [];
  const profiles: AgentSelection[] = [];
  const plugins: AgentSelection[] = [];
  for (const a of agents) {
    if (a.source === "custom") {
      custom.push({
        key: `custom:${a.agent_id}`,
        label: `${a.name}`,
        agentId: a.agent_id,
      });
    } else if (a.source === "plugin") {
      plugins.push({
        key: `plugin:${a.agent_id}`,
        label: `${a.name}`,
        agentId: a.agent_id,
      });
    } else if (a.source === "profile") {
      profiles.push({
        key: `profile:${a.profile}`,
        label: `${a.profile}`,
        profile: a.profile,
      });
    }
  }
  custom.sort((a, b) => a.label.localeCompare(b.label));
  plugins.sort((a, b) => a.label.localeCompare(b.label));
  profiles.sort((a, b) => a.label.localeCompare(b.label));
  return [AGENT_DEFAULT, ...custom, ...plugins, ...profiles];
}

const AGENT_STORAGE_PREFIX = "taskforce.chat.agent:";
const RIGHT_PANEL_KEY = "taskforce.chat.rightPanel";

function loadStoredAgentKey(conversationId: string | undefined): string {
  if (!conversationId) return "";
  try {
    return localStorage.getItem(AGENT_STORAGE_PREFIX + conversationId) ?? "";
  } catch {
    return "";
  }
}

function persistAgentKey(conversationId: string | undefined, key: string): void {
  if (!conversationId) return;
  try {
    if (key) localStorage.setItem(AGENT_STORAGE_PREFIX + conversationId, key);
    else localStorage.removeItem(AGENT_STORAGE_PREFIX + conversationId);
  } catch {
    /* storage unavailable */
  }
}

function loadRightPanelOpen(): boolean {
  if (typeof window === "undefined") return true;
  try {
    const storage = window.localStorage;
    if (typeof storage.getItem !== "function") return true;
    return storage.getItem(RIGHT_PANEL_KEY) !== "0";
  } catch {
    return true;
  }
}

function persistRightPanelOpen(open: boolean): void {
  if (typeof window === "undefined") return;
  try {
    const storage = window.localStorage;
    if (typeof storage.setItem !== "function") return;
    storage.setItem(RIGHT_PANEL_KEY, open ? "1" : "0");
  } catch {
    /* storage unavailable */
  }
}

// ---------------------------------------------------------------------------
// Breadcrumb header
// ---------------------------------------------------------------------------

interface ChatHeaderProps {
  activeConversation: ConversationInfo | undefined;
  conversationId: string | undefined;
  projectName: string | null;
  agentOptions: AgentSelection[];
  agentKey: string;
  onAgentChange: (key: string) => void;
  agentsLoading: boolean;
  isStreaming: boolean;
  onArchive: () => void;
  onFork: () => void;
  onCompact: () => void;
  onRename: () => void;
  onDelete: () => void;
  archivePending: boolean;
  forkPending: boolean;
  compactPending: boolean;
  renamePending: boolean;
  deletePending: boolean;
  viewMode: ChatViewMode;
  onViewModeChange: (mode: ChatViewMode) => void;
  rightPanelOpen: boolean;
  onRightPanelToggle: () => void;
}

function ChatHeader({
  activeConversation,
  conversationId,
  projectName,
  agentOptions,
  agentKey,
  onAgentChange,
  agentsLoading,
  isStreaming,
  onArchive,
  onFork,
  onCompact,
  onRename,
  onDelete,
  archivePending,
  forkPending,
  compactPending,
  renamePending,
  deletePending,
  viewMode,
  onViewModeChange,
  rightPanelOpen,
  onRightPanelToggle,
}: ChatHeaderProps) {
  const topic = activeConversation?.topic;
  const channel = activeConversation?.channel;
  const idShort = conversationId ? `${conversationId.slice(0, 8)}…` : null;
  const primary = topic || channel || (idShort ? "Untitled conversation" : "Chat");

  return (
    <div className="flex items-center gap-3 border-b border-border px-5 py-3">
      <div className="min-w-0 flex-1">
        {/* Breadcrumb: project › conversation. Mimics Cowork's
         *  "D:\…\TuttiPaletti / Agent task and responsibilities" line. */}
        <nav className="flex items-center gap-1.5 text-xs text-muted-foreground">
          {projectName ? (
            <>
              <span className="truncate">{projectName}</span>
              <span aria-hidden>/</span>
            </>
          ) : null}
          <h2
            className="truncate text-sm font-semibold text-foreground"
            title={topic || undefined}
          >
            {primary}
          </h2>
          <ChevronDown16Regular className="h-3 w-3 shrink-0" aria-hidden />
        </nav>
        {idShort ? (
          <p
            className="mt-0.5 flex items-center gap-1 text-[11px] text-muted-foreground"
            title={conversationId ?? undefined}
          >
            <NumberSymbol20Regular className="h-3 w-3" />
            <span className="font-mono">{idShort}</span>
          </p>
        ) : null}
      </div>
      {conversationId ? (
        <div className="flex items-center gap-1.5">
          <AgentPicker
            options={agentOptions}
            value={agentKey}
            onChange={onAgentChange}
            loading={agentsLoading}
            disabled={isStreaming}
          />
          <ViewModePicker value={viewMode} onChange={onViewModeChange} />
          <Button
            variant="ghost"
            size="sm"
            onClick={onCompact}
            disabled={compactPending || isStreaming}
            title="Summarize earlier messages to reclaim context window space"
          >
            <ArrowMinimize20Regular className="h-4 w-4" />
            <span className="hidden xl:inline">
              {compactPending ? "Compacting…" : "Compact"}
            </span>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onFork}
            disabled={forkPending}
            title="Create a copy of this conversation to replay or branch"
          >
            <BranchFork20Regular className="h-4 w-4" />
            <span className="hidden xl:inline">Fork</span>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onRename}
            disabled={renamePending}
            title="Rename this conversation"
          >
            <Edit20Regular className="h-4 w-4" />
            <span className="hidden xl:inline">Rename</span>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onArchive}
            disabled={archivePending}
            title="Archive this conversation"
          >
            <Archive20Regular className="h-4 w-4" />
            <span className="hidden xl:inline">Archive</span>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onDelete}
            disabled={deletePending}
            title="Permanently delete this conversation"
            className="text-muted-foreground hover:text-destructive"
          >
            <Delete20Regular className="h-4 w-4" />
            <span className="hidden xl:inline">Delete</span>
          </Button>
          {/* Only visible at lg+; that's the breakpoint where the right
           *  panel itself starts rendering — hiding the toggle below it
           *  avoids dangling controls on tablet widths. */}
          <Button
            variant="ghost"
            size="icon"
            onClick={onRightPanelToggle}
            aria-pressed={rightPanelOpen}
            aria-label={rightPanelOpen ? "Hide side panel" : "Show side panel"}
            title={rightPanelOpen ? "Hide side panel" : "Show side panel"}
            className="hidden lg:inline-flex"
          >
            {rightPanelOpen ? (
              <PanelRightContract20Regular className="h-4 w-4" />
            ) : (
              <PanelRightExpand20Regular className="h-4 w-4" />
            )}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

function AgentPicker({
  options,
  value,
  onChange,
  loading,
  disabled,
}: {
  options: AgentSelection[];
  value: string;
  onChange: (key: string) => void;
  loading: boolean;
  disabled: boolean;
}) {
  return (
    <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <Bot20Regular className="h-4 w-4" aria-hidden />
      <span className="sr-only">Agent</span>
      <select
        className={cn(
          "h-8 max-w-[10rem] rounded-md border border-input bg-background px-2 text-xs outline-none transition-colors",
          "focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
          "disabled:cursor-not-allowed disabled:opacity-50",
        )}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled || loading}
        title="Choose which agent answers this conversation"
      >
        {loading ? (
          <option value="">Loading…</option>
        ) : (
          options.map((opt) => (
            <option key={opt.key} value={opt.key}>
              {opt.label}
            </option>
          ))
        )}
      </select>
    </label>
  );
}

function ViewModePicker({
  value,
  onChange,
}: {
  value: ChatViewMode;
  onChange: (mode: ChatViewMode) => void;
}) {
  const current = CHAT_VIEW_MODES.find((m) => m.value === value);
  return (
    <label
      className="flex items-center gap-1.5 text-xs text-muted-foreground"
      title={current ? `${current.label}: ${current.hint}` : "Transcript detail level"}
    >
      <Eye20Regular className="h-4 w-4" aria-hidden />
      <span className="sr-only">Transcript view</span>
      <select
        aria-label="Transcript view"
        className={cn(
          "h-8 rounded-md border border-input bg-background px-2 text-xs outline-none transition-colors",
          "focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        )}
        value={value}
        onChange={(e) => onChange(e.target.value as ChatViewMode)}
      >
        {CHAT_VIEW_MODES.map((mode) => (
          <option key={mode.value} value={mode.value}>
            {mode.label}
          </option>
        ))}
      </select>
    </label>
  );
}

// ---------------------------------------------------------------------------
// Message list — Cowork-style flowing transcript
// ---------------------------------------------------------------------------

function MessageList({
  messages,
  pending,
  viewMode,
}: {
  messages: ChatMessageT[];
  pending?: { text: string; toolCalls: ReturnType<typeof useChatStream>["state"]["toolCalls"] };
  viewMode: ChatViewMode;
}) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (el && typeof el.scrollTo === "function") {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }
  }, [messages, pending?.text, pending?.toolCalls]);

  // In summary mode, drop role="tool" turns and assistant turns that only
  // carry tool_calls (no visible text).
  const visibleMessages = useMemo(() => {
    if (viewMode !== "summary") return messages;
    return messages.filter((m) => {
      if (m.role === "tool") return false;
      const hasText = typeof m.content === "string" && m.content.trim().length > 0;
      const hasParts = Array.isArray(m.parts) && m.parts.length > 0;
      return hasText || hasParts;
    });
  }, [messages, viewMode]);

  if (visibleMessages.length === 0 && !pending) {
    return (
      <div className="flex flex-1 items-center justify-center px-4">
        <EmptyState
          title="How can the agent help?"
          description="Ask anything — files can be dragged in or pasted directly. Replies stream live, including tool calls."
          className="max-w-md"
        />
      </div>
    );
  }

  return (
    <div ref={ref} className="flex-1 overflow-auto scrollbar-thin">
      <div className="mx-auto flex max-w-3xl flex-col gap-4 px-6 py-6">
        {visibleMessages.map((m, i) => (
          <CoworkMessage key={i} message={m} viewMode={viewMode} />
        ))}
        {pending ? (
          <CoworkMessage
            message={{ role: "assistant", content: pending.text }}
            pending
            toolCalls={pending.toolCalls}
            viewMode={viewMode}
          />
        ) : null}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ChatPage() {
  const params = useParams();
  const conversationId = params.conversationId;
  const conversationsQuery = useConversations();
  const activeConversation = useMemo(
    () => conversationsQuery.data?.find((c) => c.conversation_id === conversationId),
    [conversationsQuery.data, conversationId],
  );
  const messagesQuery = useConversationMessages(conversationId);
  const archive = useArchiveConversation();
  const fork = useForkConversation();
  const compact = useCompactConversation();
  const rename = useRenameConversation();
  const del = useDeleteConversation();
  // ``useChatStream(conversationId)`` scopes stream state per conversation
  // via the module-level zustand store, so navigating away from the chat
  // page mid-run no longer drops in-flight tool calls / plan steps —
  // remounting with the same id resubscribes to whatever the store
  // currently holds. ``conversationId`` may be undefined (NoConversationPicker
  // landing screen); the hook tolerates that by returning an EMPTY_STATE.
  const stream = useChatStream(conversationId);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const agentsQuery = useAgents();
  const healthQuery = useHealth();
  const agentOptions = useMemo(
    () => buildAgentOptions(agentsQuery.data?.agents),
    [agentsQuery.data],
  );
  const [agentKey, setAgentKey] = useState<string>(() =>
    loadStoredAgentKey(conversationId),
  );
  const viewMode = useChatPreferences((s) => s.viewMode);
  const setViewMode = useChatPreferences((s) => s.setViewMode);

  // Right-panel toggle. Persists per-browser so the user's preference
  // survives page reloads but isn't synced across devices (it's a
  // viewport-level affordance, not a setting).
  const [rightPanelOpen, setRightPanelOpen] = useState<boolean>(() => {
    return loadRightPanelOpen();
  });
  useEffect(() => {
    persistRightPanelOpen(rightPanelOpen);
  }, [rightPanelOpen]);

  // The "project name" shown in the breadcrumb only appears when the
  // backend really exposes a working directory via /health.checks. We
  // intentionally do NOT fall back to ``default_profile`` — a profile
  // name in the breadcrumb position would mislead users into thinking
  // it's a project folder. Per-conversation working dirs are tracked
  // as future work in docs/cowork-comparison.md (Phase 2).
  const projectName = useMemo(() => {
    const checks = (healthQuery.data?.checks ?? {}) as Record<string, unknown>;
    const wd = (checks.working_dir ?? checks.work_dir) as string | undefined;
    return pathBasename(wd ?? null);
  }, [healthQuery.data]);

  useEffect(() => {
    setAgentKey(loadStoredAgentKey(conversationId));
  }, [conversationId]);

  useEffect(() => {
    persistAgentKey(conversationId, agentKey);
  }, [conversationId, agentKey]);

  const selectedAgent = useMemo(
    () => agentOptions.find((o) => o.key === agentKey) ?? AGENT_DEFAULT,
    [agentOptions, agentKey],
  );

  const messages = messagesQuery.data ?? [];
  const isStreaming = stream.isStreaming;

  // No conversationId-switch reset: stream state is now keyed by
  // conversationId in the store, so switching naturally swaps in the
  // target conversation's state (or EMPTY_STATE if unseen).

  // Phase 1 — agent declared "done". The in-stream ``complete`` event
  // fires BEFORE the route's ``finally`` block has actually persisted
  // the assistant reply to conversation history. Refetching here would
  // race the backend's append_message and silently overwrite the live
  // streamed bubble with a stale (pre-completion) message list — which
  // is exactly the "result disappears at the end" symptom. So we only
  // do the optimistic write here; the refetch happens in phase 2 below.
  useEffect(() => {
    if (!stream.state.completed || !conversationId) return;
    const streamedText = stream.state.text;
    if (!streamedText) return;
    queryClient.setQueryData<ChatMessageT[]>(
      queryKeys.conversationMessages(conversationId),
      (prev) => {
        const list = prev ?? [];
        const last = list[list.length - 1];
        if (last?.role === "assistant" && last.content === streamedText) {
          return list;
        }
        return [...list, { role: "assistant", content: streamedText }];
      },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stream.state.completed, conversationId]);

  // Phase 2 — server confirmed the reply is in conversation history.
  // Now the refetch is safe: the backend has the new turn on disk so
  // useConversationMessages will return the canonical version (which
  // for chat purposes is identical to our optimistic write — same
  // ``role`` / ``content``).
  //
  // ``stream.reset()`` is NOT called here: the right-side panel
  // (Progress / Workspace / Context) needs ``toolCalls`` and
  // ``planSteps`` to stay visible until the user sends the next
  // message. A subsequent ``send()`` resets the bucket on its own.
  useEffect(() => {
    if (!stream.state.persistedAt || !conversationId) return;
    queryClient.invalidateQueries({
      queryKey: queryKeys.conversationMessages(conversationId),
    });
    queryClient.invalidateQueries({ queryKey: queryKeys.conversations });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stream.state.persistedAt, conversationId]);

  const onSend = async (text: string, attachments: FileMetadata[]) => {
    if (!conversationId) return;
    setRightPanelOpen(true);
    queryClient.setQueryData<ChatMessageT[]>(
      queryKeys.conversationMessages(conversationId),
      (prev) => [
        ...(prev ?? []),
        { role: "user", content: text, attachments },
      ],
    );
    await stream.send({
      conversationId,
      message: text,
      attachments: attachments.map((a) => ({ file_id: a.file_id })),
      agentId: selectedAgent.agentId,
      profile: selectedAgent.profile,
    });
  };

  const onArchive = async () => {
    if (!conversationId) return;
    if (!window.confirm("Archive this conversation?")) return;
    await archive.mutateAsync({ id: conversationId });
  };

  const onRename = async () => {
    if (!conversationId) return;
    const current = activeConversation?.topic ?? "";
    const next = window.prompt("Rename conversation", current);
    if (next === null) return;
    const trimmed = next.trim();
    if (!trimmed) {
      toast.error("Rename failed", "Title must not be empty.");
      return;
    }
    if (trimmed === current) return;
    try {
      await rename.mutateAsync({ id: conversationId, title: trimmed });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Could not rename conversation.";
      toast.error("Rename failed", message);
    }
  };

  const onDelete = async () => {
    if (!conversationId) return;
    const label =
      activeConversation?.topic || activeConversation?.channel || conversationId;
    if (
      !window.confirm(
        `Permanently delete "${label}"? This cannot be undone.`,
      )
    ) {
      return;
    }
    try {
      await del.mutateAsync({ id: conversationId });
      // The active conversation is gone — bounce to the chat root so the
      // page doesn't render a stale 404 while React Query refetches.
      navigate("/chat");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Could not delete conversation.";
      toast.error("Delete failed", message);
    }
  };

  const onCompact = async () => {
    if (!conversationId) return;
    if (
      !window.confirm(
        "Compact this conversation? Earlier messages will be replaced " +
          "by an LLM-generated summary. This cannot be undone — fork " +
          "first if you want to keep the original.",
      )
    )
      return;
    try {
      const result = await compact.mutateAsync({ id: conversationId });
      if (result.status === "compacted") {
        toast.success(
          "Conversation compacted",
          `${result.summarized ?? 0} messages folded into a summary; ${
            result.kept ?? 0
          } kept verbatim.`,
        );
      } else {
        toast.info(
          "Nothing to compact",
          `Conversation has only ${result.messages ?? 0} messages — below the threshold.`,
        );
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Could not compact conversation.";
      toast.error("Compact failed", message);
    }
  };

  const onFork = async () => {
    if (!conversationId) return;
    try {
      const result = await fork.mutateAsync({ conversationId });
      const target = `/chat/${encodeURIComponent(result.conversation_id)}`;
      const opened = window.open(target, "_blank", "noopener,noreferrer");
      if (opened) {
        toast.success(
          "Conversation forked",
          `${result.messages_copied} messages copied — opened in a new tab.`,
        );
      } else {
        toast.info("Conversation forked", "Pop-up blocked; switching to the copy.");
        navigate(target);
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Could not fork conversation.";
      toast.error("Fork failed", message);
    }
  };

  // No conversation selected → show the picker. Keeps the test happy
  // ("Pick or start a conversation" still rendered).
  if (!conversationId) {
    return <NoConversationPicker />;
  }

  return (
    <div className="flex h-full min-h-0 flex-1 overflow-hidden">
      <section className="flex min-w-0 flex-1 flex-col">
        <ChatHeader
          activeConversation={activeConversation}
          conversationId={conversationId}
          projectName={projectName}
          agentOptions={agentOptions}
          agentKey={agentKey}
          onAgentChange={setAgentKey}
          agentsLoading={agentsQuery.isLoading}
          isStreaming={isStreaming}
          onArchive={onArchive}
          onFork={onFork}
          onCompact={onCompact}
          onRename={onRename}
          onDelete={onDelete}
          archivePending={archive.isPending}
          forkPending={fork.isPending}
          compactPending={compact.isPending}
          renamePending={rename.isPending}
          deletePending={del.isPending}
          viewMode={viewMode}
          onViewModeChange={setViewMode}
          rightPanelOpen={rightPanelOpen}
          onRightPanelToggle={() => setRightPanelOpen((o) => !o)}
        />

        <div className="flex min-h-0 flex-1 flex-col">
          {messagesQuery.isLoading ? (
            <div className="flex-1 p-4">
              <Skeleton className="h-full w-full" />
            </div>
          ) : messagesQuery.error instanceof ApiError &&
            messagesQuery.error.status === 404 ? (
            <div className="flex flex-1 items-center justify-center p-6">
              <EmptyState
                title="Conversation not found"
                description="It may have been archived or never existed."
              />
            </div>
          ) : (
            <>
              <MessageList
                messages={messages}
                pending={
                  // Show the live streaming entry only while the agent
                  // is still working OR the assistant reply hasn't been
                  // persisted yet. Once the ``completed`` flag flips, the
                  // persisted reply takes over via ``messages`` and the
                  // pending entry would otherwise duplicate it. Tool
                  // calls + plan steps survive in the store and surface
                  // via RightPanel — they're not lost, just rendered
                  // through the side panel instead of the chat bubble.
                  isStreaming || (!stream.state.completed && stream.state.text)
                    ? { text: stream.state.text, toolCalls: stream.state.toolCalls }
                    : undefined
                }
                viewMode={viewMode}
              />
              {stream.error ? (
                <p className="border-t border-border bg-destructive/5 px-4 py-2 text-xs text-destructive">
                  {stream.error}
                </p>
              ) : null}
              {stream.state.pendingAskUser ? (
                <div className="border-t border-border bg-card/60 px-3 pt-3">
                  <AskUserCard
                    prompt={stream.state.pendingAskUser}
                    onAnswer={(answer) => void onSend(answer, [])}
                    disabled={isStreaming}
                  />
                </div>
              ) : null}
              <div className="border-t border-border px-4 py-3">
                <ChatComposer
                  onSend={onSend}
                  onCancel={stream.cancel}
                  isStreaming={isStreaming}
                />
              </div>
            </>
          )}
        </div>
      </section>

      {rightPanelOpen ? (
        <RightPanel
          projectName={projectName}
          planSteps={stream.state.planSteps}
          toolCalls={stream.state.toolCalls}
          streaming={isStreaming}
        />
      ) : null}
    </div>
  );
}

function NoConversationPicker() {
  const create = useCreateConversation();
  const navigate = useNavigate();
  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <EmptyState
        title="Pick or start a conversation"
        description="Conversations are persisted on disk via the ConversationManager (ADR-016)."
        action={
          <Button
            onClick={async () => {
              const conv = await create.mutateAsync({ channel: "rest" });
              navigate(`/chat/${encodeURIComponent(conv.conversation_id)}`);
            }}
            disabled={create.isPending}
          >
            <ChatAdd20Regular className="h-4 w-4" />
            Start conversation
          </Button>
        }
      />
    </div>
  );
}
