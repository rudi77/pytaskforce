import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Archive,
  Bot,
  Eye,
  GitBranch,
  Hash,
  MessageSquare,
  MessageSquarePlus,
  PanelLeft,
} from "lucide-react";
import { toast } from "@/components/ui/toast";
import { useQueryClient } from "@tanstack/react-query";

import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/EmptyState";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  queryKeys,
  useAgents,
  useArchiveConversation,
  useArchivedConversations,
  useConversationMessages,
  useConversations,
  useCreateConversation,
  useForkConversation,
  type AgentSummary,
  type ChatMessage as ChatMessageT,
  type ConversationInfo,
  type FileMetadata,
} from "@/api/queries";
import { ApiError } from "@/api/client";
import { ChatComposer } from "@/features/chat/ChatComposer";
import { MessageBubble } from "@/features/chat/MessageView";
import { useChatStream } from "@/features/chat/useChatStream";
import {
  CHAT_VIEW_MODES,
  useChatPreferences,
  type ChatViewMode,
} from "@/features/chat/useChatPreferences";
import { cn } from "@/lib/utils";
import { formatRelativeTime } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Agent selection helpers (unchanged from the previous design)
// ---------------------------------------------------------------------------

interface AgentSelection {
  /** Stable key used for the dropdown value and localStorage. */
  key: string;
  label: string;
  /** Either custom-agent id (sent as `agent_id`) or profile name (sent as `profile`). Empty string = server default. */
  agentId?: string;
  profile?: string;
}

const AGENT_DEFAULT: AgentSelection = { key: "", label: "Default (server)" };

function buildAgentOptions(agents: AgentSummary[] | undefined): AgentSelection[] {
  if (!agents) return [AGENT_DEFAULT];
  const custom: AgentSelection[] = [];
  const profiles: AgentSelection[] = [];
  const plugins: AgentSelection[] = [];
  for (const a of agents) {
    if (a.source === "custom") {
      custom.push({
        key: `custom:${a.agent_id}`,
        label: `${a.name} (${a.agent_id})`,
        agentId: a.agent_id,
      });
    } else if (a.source === "plugin") {
      plugins.push({
        key: `plugin:${a.agent_id}`,
        label: `${a.name} (plugin)`,
        agentId: a.agent_id,
      });
    } else if (a.source === "profile") {
      profiles.push({
        key: `profile:${a.profile}`,
        label: `${a.profile} (profile)`,
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
    /* storage unavailable — silently ignore */
  }
}

// ---------------------------------------------------------------------------
// Sidebar — conversation list (used inline on desktop, inside Sheet on mobile)
// ---------------------------------------------------------------------------

interface SidebarBodyProps {
  activeId?: string;
  onNavigate?: () => void;
}

function SidebarBody({ activeId, onNavigate }: SidebarBodyProps) {
  const navigate = useNavigate();
  const conversations = useConversations();
  const archived = useArchivedConversations(20);
  const create = useCreateConversation();

  const onNew = async () => {
    const conv = await create.mutateAsync({ channel: "rest" });
    onNavigate?.();
    navigate(`/chat/${encodeURIComponent(conv.conversation_id)}`);
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-3">
        <h2 className="text-sm font-semibold">Conversations</h2>
        <Button size="sm" onClick={onNew} disabled={create.isPending}>
          <MessageSquarePlus className="h-4 w-4" />
          New
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-auto scrollbar-thin px-2 py-2">
        <SidebarSection label="Active">
          {conversations.isLoading ? (
            <Skeleton className="h-12" />
          ) : conversations.data && conversations.data.length > 0 ? (
            conversations.data.map((c) => (
              <ConversationItem
                key={c.conversation_id}
                conversation={c}
                active={activeId === c.conversation_id}
                onNavigate={onNavigate}
              />
            ))
          ) : (
            <p className="px-1 text-xs text-muted-foreground">
              No active conversations.
            </p>
          )}
        </SidebarSection>

        <SidebarSection label="Archived" className="mt-3">
          {archived.isLoading ? (
            <Skeleton className="h-10" />
          ) : archived.data && archived.data.length > 0 ? (
            archived.data.map((c) => (
              <ConversationItem
                key={c.conversation_id}
                conversation={{
                  conversation_id: c.conversation_id,
                  topic: c.topic,
                  channel: null,
                  message_count: c.message_count,
                  last_activity: c.archived_at,
                }}
                active={false}
                badge="archived"
                onNavigate={onNavigate}
              />
            ))
          ) : (
            <p className="px-1 text-xs text-muted-foreground">
              No archived conversations.
            </p>
          )}
        </SidebarSection>
      </div>
    </div>
  );
}

function SidebarSection({
  label,
  className,
  children,
}: {
  label: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("flex flex-col gap-0.5", className)}>
      <p className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </p>
      {children}
    </div>
  );
}

interface ConversationItemFields {
  conversation_id: string;
  topic?: string | null;
  channel?: string | null;
  message_count: number;
  last_activity: string;
}

function ConversationItem({
  conversation: c,
  active,
  badge,
  onNavigate,
}: {
  conversation: ConversationItemFields;
  active: boolean;
  badge?: string;
  onNavigate?: () => void;
}) {
  const title = c.topic || c.channel || c.conversation_id;
  const subtitle = c.message_count
    ? `${c.message_count} msg · ${formatRelativeTime(c.last_activity)}`
    : formatRelativeTime(c.last_activity);
  return (
    <Link
      to={`/chat/${encodeURIComponent(c.conversation_id)}`}
      onClick={onNavigate}
      className={cn(
        "group flex items-start gap-2 rounded-md border border-transparent px-2 py-2 text-sm transition-colors",
        active
          ? "border-primary/40 bg-primary/10"
          : "hover:bg-accent",
      )}
    >
      <span
        className={cn(
          "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md border text-muted-foreground",
          active && "border-primary/40 text-primary",
        )}
        aria-hidden
      >
        <MessageSquare className="h-3 w-3" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <span className="truncate font-medium">{title}</span>
          {c.channel ? (
            <Badge variant="outline" className="shrink-0 px-1 py-0 text-[9px] uppercase">
              {c.channel}
            </Badge>
          ) : null}
          {badge ? (
            <Badge variant="outline" className="ml-auto shrink-0 px-1 py-0 text-[9px]">
              {badge}
            </Badge>
          ) : null}
        </span>
        <span className="block truncate text-[11px] text-muted-foreground">
          {subtitle}
        </span>
      </span>
    </Link>
  );
}

// ---------------------------------------------------------------------------
// Header — toolbar with topic, ID and actions
// ---------------------------------------------------------------------------

interface ChatHeaderProps {
  activeConversation: ConversationInfo | undefined;
  conversationId: string | undefined;
  agentOptions: AgentSelection[];
  agentKey: string;
  onAgentChange: (key: string) => void;
  agentsLoading: boolean;
  isStreaming: boolean;
  onArchive: () => void;
  onFork: () => void;
  archivePending: boolean;
  forkPending: boolean;
  onOpenSidebar: () => void;
  viewMode: ChatViewMode;
  onViewModeChange: (mode: ChatViewMode) => void;
}

function ChatHeader({
  activeConversation,
  conversationId,
  agentOptions,
  agentKey,
  onAgentChange,
  agentsLoading,
  isStreaming,
  onArchive,
  onFork,
  archivePending,
  forkPending,
  onOpenSidebar,
  viewMode,
  onViewModeChange,
}: ChatHeaderProps) {
  const topic = activeConversation?.topic;
  const channel = activeConversation?.channel;
  const idShort = conversationId ? `${conversationId.slice(0, 8)}…` : null;
  const primary = topic || channel || (idShort ? "Untitled conversation" : "Chat");

  return (
    <div className="flex items-center gap-2 border-b border-border bg-card/60 px-3 py-2">
      <Button
        variant="ghost"
        size="sm"
        onClick={onOpenSidebar}
        className="md:hidden"
        aria-label="Open conversations"
      >
        <PanelLeft className="h-4 w-4" />
      </Button>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <h2 className="truncate text-sm font-semibold" title={topic || undefined}>
            {primary}
          </h2>
          {channel && topic ? (
            <Badge variant="outline" className="shrink-0 px-1 py-0 text-[10px] uppercase">
              {channel}
            </Badge>
          ) : null}
        </div>
        {idShort ? (
          <p
            className="flex items-center gap-1 text-[11px] text-muted-foreground"
            title={conversationId ?? undefined}
          >
            <Hash className="h-3 w-3" />
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
            variant="outline"
            size="sm"
            onClick={onFork}
            disabled={forkPending}
            title="Create a copy of this conversation to replay or branch"
          >
            <GitBranch className="h-4 w-4" />
            <span className="hidden lg:inline">Fork</span>
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={onArchive}
            disabled={archivePending}
            title="Archive this conversation"
          >
            <Archive className="h-4 w-4" />
            <span className="hidden lg:inline">Archive</span>
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
      <Bot className="h-4 w-4" aria-hidden />
      <span className="sr-only">Agent</span>
      <select
        className={cn(
          "h-8 max-w-[12rem] rounded-md border border-input bg-background px-2 text-xs outline-none transition-colors",
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
      <Eye className="h-4 w-4" aria-hidden />
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
// Message list + empty / pending states
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
    // jsdom (the test environment) doesn't implement Element.scrollTo;
    // guard the call so it can't throw in tests or older browsers.
    if (el && typeof el.scrollTo === "function") {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }
  }, [messages, pending?.text, pending?.toolCalls]);

  // In summary mode, drop role="tool" turns and assistant turns that only
  // carry tool_calls (no visible text). The remaining transcript reads as
  // "user asked X, assistant answered Y" — which is the whole point of the
  // mode.
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
      <div className="mx-auto flex max-w-3xl flex-col gap-2 px-4 py-4">
        {visibleMessages.map((m, i) => (
          <MessageBubble key={i} message={m} viewMode={viewMode} />
        ))}
        {pending ? (
          <MessageBubble
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
  const stream = useChatStream();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const agentsQuery = useAgents();
  const agentOptions = useMemo(
    () => buildAgentOptions(agentsQuery.data?.agents),
    [agentsQuery.data],
  );
  const [agentKey, setAgentKey] = useState<string>(() =>
    loadStoredAgentKey(conversationId),
  );
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const viewMode = useChatPreferences((s) => s.viewMode);
  const setViewMode = useChatPreferences((s) => s.setViewMode);

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

  useEffect(() => {
    stream.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  useEffect(() => {
    if (stream.state.completed && conversationId) {
      queryClient.invalidateQueries({
        queryKey: queryKeys.conversationMessages(conversationId),
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.conversations });
      stream.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stream.state.completed, conversationId]);

  const onSend = async (text: string, attachments: FileMetadata[]) => {
    if (!conversationId) return;
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

  return (
    <Card className="flex h-full min-h-0 flex-1 overflow-hidden">
      {/* Desktop sidebar (inline). Mobile uses a Sheet anchored to the header. */}
      <aside className="hidden w-72 shrink-0 border-r border-border bg-card md:flex md:flex-col">
        <SidebarBody activeId={conversationId} />
      </aside>

      <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
        <SheetContent side="left" className="w-80 max-w-[85vw] p-0">
          <SheetHeader className="sr-only">
            <SheetTitle>Conversations</SheetTitle>
          </SheetHeader>
          <SidebarBody
            activeId={conversationId}
            onNavigate={() => setSidebarOpen(false)}
          />
        </SheetContent>

        <section className="flex min-w-0 flex-1 flex-col">
          <ChatHeader
            activeConversation={activeConversation}
            conversationId={conversationId}
            agentOptions={agentOptions}
            agentKey={agentKey}
            onAgentChange={setAgentKey}
            agentsLoading={agentsQuery.isLoading}
            isStreaming={isStreaming}
            onArchive={onArchive}
            onFork={onFork}
            archivePending={archive.isPending}
            forkPending={fork.isPending}
            onOpenSidebar={() => setSidebarOpen(true)}
            viewMode={viewMode}
            onViewModeChange={setViewMode}
          />

          <div className="flex min-h-0 flex-1 flex-col">
            {!conversationId ? (
              <NoConversationPicker />
            ) : messagesQuery.isLoading ? (
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
                    isStreaming || stream.state.text || stream.state.toolCalls.length > 0
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
                <div className="border-t border-border bg-card/60 p-3">
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

      </Sheet>
    </Card>
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
            <MessageSquarePlus className="h-4 w-4" />
            Start conversation
          </Button>
        }
      />
    </div>
  );
}
