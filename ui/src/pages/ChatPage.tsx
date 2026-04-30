import { useEffect, useMemo, useRef } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Archive, GitBranch, MessageSquarePlus } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/EmptyState";
import {
  queryKeys,
  useArchiveConversation,
  useArchivedConversations,
  useConversationMessages,
  useConversations,
  useCreateConversation,
  useForkConversation,
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
    <div ref={ref} className="flex-1 space-y-4 overflow-auto scrollbar-thin px-1">
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
    });
  };

  const onArchive = async () => {
    if (!conversationId) return;
    if (!window.confirm("Archive this conversation?")) return;
    await archive.mutateAsync({ id: conversationId });
  };

  const onFork = async () => {
    if (!conversationId) return;
    const result = await fork.mutateAsync({ conversationId });
    navigate(`/chat/${encodeURIComponent(result.conversation_id)}`);
  };

  const headerTitle = useMemo(() => {
    return conversationId ? `Conversation ${conversationId.slice(0, 12)}…` : "Chat";
  }, [conversationId]);

  return (
    <div className="grid h-[calc(100vh-7rem)] grid-cols-1 gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
      <div className="hidden lg:block">
        <ConversationsSidebar activeId={conversationId} />
      </div>
      <Card className="flex h-full min-h-0 flex-col">
        <CardHeader className="flex flex-row items-center justify-between gap-2 border-b border-border pb-3">
          <CardTitle>{headerTitle}</CardTitle>
          <div className="flex items-center gap-2">
            {conversationId ? (
              <>
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
        <CardContent className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden pt-3">
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
