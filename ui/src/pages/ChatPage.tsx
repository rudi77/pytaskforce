import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Archive, Bot, GitBranch, MessageSquare, MessageSquarePlus, Sparkles } from "lucide-react";
import { toast } from "@/components/ui/toast";
import { useQueryClient } from "@tanstack/react-query";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/EmptyState";
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
  type FileMetadata,
} from "@/api/queries";
import { ApiError } from "@/api/client";
import { ChatComposer } from "@/features/chat/ChatComposer";
import { MessageBubble } from "@/features/chat/MessageView";
import { useChatStream } from "@/features/chat/useChatStream";
import { cn } from "@/lib/utils";
import { formatRelativeTime } from "@/lib/utils";

function ConversationListItem({
  active,
  title,
  subtitle,
  badge,
  to,
}: {
  active: boolean;
  title: string;
  subtitle: string;
  badge?: string;
  to: string;
}) {
  return (
    <Link
      to={to}
      className={cn(
        "flex flex-col gap-0.5 rounded-md border border-transparent px-3 py-2 text-sm transition-colors",
        active
          ? "border-primary/40 bg-primary/10"
          : "hover:bg-accent",
      )}
    >
      <div className="flex items-center gap-2">
        <span className="truncate font-medium">{title}</span>
        {badge ? (
          <Badge variant="outline" className="ml-auto px-1 py-0 text-[10px]">
            {badge}
          </Badge>
        ) : null}
      </div>
      <span className="truncate text-xs text-muted-foreground">{subtitle}</span>
    </Link>
  );
}

function ConversationsSidebar({ activeId }: { activeId?: string }) {
  const navigate = useNavigate();
  const conversations = useConversations();
  const archived = useArchivedConversations(20);
  const create = useCreateConversation();

  const onNew = async () => {
    const conv = await create.mutateAsync({ channel: "rest" });
    navigate(`/chat/${encodeURIComponent(conv.conversation_id)}`);
  };

  return (
    <Card className="flex h-full flex-col">
      <CardHeader className="flex flex-row items-center justify-between gap-2 pb-3">
        <CardTitle>Conversations</CardTitle>
        <Button size="sm" onClick={onNew} disabled={create.isPending}>
          <MessageSquarePlus className="h-4 w-4" />
          New
        </Button>
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden pt-0">
        <div className="flex min-h-0 flex-1 flex-col gap-1 overflow-auto scrollbar-thin">
          <p className="px-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Active
          </p>
          {conversations.isLoading ? (
            <Skeleton className="h-12" />
          ) : conversations.data && conversations.data.length > 0 ? (
            conversations.data.map((c) => (
              <ConversationListItem
                key={c.conversation_id}
                active={activeId === c.conversation_id}
                title={c.topic ?? c.channel ?? c.conversation_id}
                subtitle={`${c.message_count} messages · ${formatRelativeTime(c.last_activity)}`}
                to={`/chat/${encodeURIComponent(c.conversation_id)}`}
              />
            ))
          ) : (
            <p className="px-1 text-xs text-muted-foreground">No active conversations.</p>
          )}

          <p className="mt-2 px-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Archived
          </p>
          {archived.isLoading ? (
            <Skeleton className="h-10" />
          ) : archived.data && archived.data.length > 0 ? (
            archived.data.map((c) => (
              <ConversationListItem
                key={c.conversation_id}
                active={false}
                title={c.topic || c.conversation_id}
                subtitle={c.summary || formatRelativeTime(c.archived_at)}
                badge="archived"
                to={`/chat/${encodeURIComponent(c.conversation_id)}`}
              />
            ))
          ) : (
            <p className="px-1 text-xs text-muted-foreground">No archived conversations.</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function MessageList({
  messages,
  pending,
}: {
  messages: ChatMessageT[];
  pending?: { text: string; toolCalls: ReturnType<typeof useChatStream>["state"]["toolCalls"] };
}) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight, behavior: "smooth" });
  }, [messages, pending?.text, pending?.toolCalls]);

  return (
    <div ref={ref} className="flex-1 overflow-auto scrollbar-thin">
      <div className="mx-auto flex max-w-3xl flex-col gap-2 py-2">
        {messages.length === 0 && !pending ? <ConversationStarter /> : null}
        {messages.map((m, i) => (
          <MessageBubble key={i} message={m} />
        ))}
        {pending ? (
          <MessageBubble
            message={{ role: "assistant", content: pending.text }}
            pending
            toolCalls={pending.toolCalls}
          />
        ) : null}
      </div>
    </div>
  );
}

function ConversationStarter() {
  return (
    <div className="my-8 flex flex-col items-center gap-3 rounded-2xl border border-dashed border-border bg-card/40 px-6 py-10 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
        <Sparkles className="h-5 w-5" />
      </div>
      <div className="space-y-1">
        <p className="text-base font-semibold">How can the agent help?</p>
        <p className="max-w-md text-sm text-muted-foreground">
          Ask anything — files can be dragged in or pasted directly. Replies stream
          live, including tool calls and (soon) interactive widgets.
        </p>
      </div>
    </div>
  );
}

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
    <label className="flex items-center gap-2 text-xs text-muted-foreground">
      <Bot className="h-4 w-4" />
      <span className="hidden sm:inline">Agent</span>
      <select
        className="h-8 rounded-md border border-input bg-background px-2 text-xs outline-none ring-offset-background focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
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

export default function ChatPage() {
  const params = useParams();
  const conversationId = params.conversationId;
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
    // Optimistically add the user message to the cache.
    queryClient.setQueryData<ChatMessageT[]>(
      queryKeys.conversationMessages(conversationId),
      (prev) => [
        ...(prev ?? []),
        { role: "user", content: text, attachments: attachments },
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
      // Open the fork in a new tab so the user keeps the original
      // conversation in view (the most common reason to fork is to
      // compare an alternate path side-by-side).
      const opened = window.open(target, "_blank", "noopener,noreferrer");
      if (opened) {
        toast.success(
          "Conversation forked",
          `${result.messages_copied} messages copied — opened in a new tab.`,
        );
      } else {
        // Pop-up blocked — fall back to in-place navigation so the user
        // doesn't lose the operation entirely.
        toast.info("Conversation forked", "Pop-up blocked; switching to the copy.");
        navigate(target);
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Could not fork conversation.";
      toast.error("Fork failed", message);
    }
  };

  const headerTitle = useMemo(() => {
    return conversationId ? `Conversation ${conversationId.slice(0, 12)}…` : "Chat";
  }, [conversationId]);

  return (
    <div className="grid h-[calc(100vh-7rem)] grid-cols-1 gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
      <div className="hidden lg:block">
        <ConversationsSidebar activeId={conversationId} />
      </div>
      <Card className="flex h-full min-h-0 flex-col overflow-hidden">
        <CardHeader className="flex flex-row items-center justify-between gap-2 border-b border-border bg-card/60 py-3">
          <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <MessageSquare className="h-4 w-4" />
            <span className="font-mono text-xs">{headerTitle}</span>
          </CardTitle>
          <div className="flex items-center gap-2">
            {conversationId ? (
              <>
                <AgentPicker
                  options={agentOptions}
                  value={agentKey}
                  onChange={setAgentKey}
                  loading={agentsQuery.isLoading}
                  disabled={isStreaming}
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={onFork}
                  disabled={fork.isPending}
                  title="Create a copy of this conversation to replay or branch"
                >
                  <GitBranch className="h-4 w-4" />
                  Fork
                </Button>
                <Button variant="outline" size="sm" onClick={onArchive} disabled={archive.isPending}>
                  <Archive className="h-4 w-4" />
                  Archive
                </Button>
              </>
            ) : null}
          </div>
        </CardHeader>
        <CardContent className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden p-4">
          {!conversationId ? (
            <NoConversation />
          ) : messagesQuery.isLoading ? (
            <Skeleton className="flex-1 w-full" />
          ) : messagesQuery.error instanceof ApiError &&
            messagesQuery.error.status === 404 ? (
            <EmptyState
              title="Conversation not found"
              description="It may have been archived or never existed."
            />
          ) : (
            <>
              <MessageList
                messages={messages}
                pending={
                  isStreaming || stream.state.text || stream.state.toolCalls.length > 0
                    ? { text: stream.state.text, toolCalls: stream.state.toolCalls }
                    : undefined
                }
              />
              {stream.error ? (
                <p className="text-xs text-destructive">{stream.error}</p>
              ) : null}
              <ChatComposer
                onSend={onSend}
                onCancel={stream.cancel}
                isStreaming={isStreaming}
              />
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function NoConversation() {
  const create = useCreateConversation();
  const navigate = useNavigate();
  return (
    <div className="flex flex-1 items-center justify-center">
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
