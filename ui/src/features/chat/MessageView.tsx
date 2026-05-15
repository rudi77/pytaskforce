import { useMemo } from "react";
import { Bot, ChevronRight, Download, FileText, ImageIcon, User, Wrench } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { getApiBaseUrl, getApiToken } from "@/lib/settings";
import type { ChatMessage, FileMetadata } from "@/api/queries";
import type { ToolCallView } from "@/features/chat/useChatStream";
import { MessageContent, partsFromContent } from "@/features/chat/MessageContent";
import type { ChatViewMode } from "@/features/chat/useChatPreferences";
import type { WidgetEventHandler } from "@/features/chat/widgets/types";

interface MessageBubbleProps {
  message: ChatMessage;
  pending?: boolean;
  toolCalls?: ToolCallView[];
  onWidgetEvent?: WidgetEventHandler;
  /** Controls how much detail is rendered. Defaults to ``normal``. */
  viewMode?: ChatViewMode;
}

/**
 * One row in the chat transcript.
 *
 * Layout note: both user and assistant messages share a uniform full-width
 * content column (avatar on the left, body on the right). We deliberately
 * dropped the variable-width "speech bubble" look — distinct widths felt
 * inconsistent and made the transcript hard to scan. The role is signalled
 * via avatar, label and a subtle background tint instead.
 */
export function MessageBubble({
  message,
  pending,
  toolCalls,
  onWidgetEvent,
  viewMode = "normal",
}: MessageBubbleProps) {
  const isUser = message.role === "user";
  const parts = partsFromContent(message.content, message.parts);
  // Summary mode hides every tool call; assistant text + user prompts remain
  // visible because that's the whole point of the mode (read what was said,
  // not how it was figured out).
  const showToolCalls = viewMode !== "summary" && toolCalls && toolCalls.length > 0;
  const expandToolCalls = viewMode === "verbose";

  return (
    <div
      className={cn(
        "group flex gap-4 rounded-xl border border-transparent px-4 py-4 transition-colors",
        isUser ? "bg-muted/40" : "bg-card hover:border-border",
      )}
    >
      <Avatar isUser={isUser} />
      <div className="min-w-0 flex-1 space-y-2">
        <header className="flex items-center gap-2 text-xs">
          <span className="font-semibold text-foreground">
            {isUser ? "You" : "Assistant"}
          </span>
          {pending ? <StreamingDots /> : null}
        </header>

        {showToolCalls ? (
          <ToolCallList calls={toolCalls!} defaultOpen={expandToolCalls} />
        ) : null}

        <MessageContent parts={parts} pending={pending} onWidgetEvent={onWidgetEvent} />

        {message.attachments && message.attachments.length > 0 ? (
          <AttachmentChips attachments={message.attachments} />
        ) : null}
      </div>
    </div>
  );
}

function StreamingDots() {
  return (
    <span
      className="inline-flex items-center gap-1 text-primary"
      role="status"
      aria-live="polite"
      aria-label="Streaming response"
    >
      <span className="flex items-center gap-1">
        <span className="h-1.5 w-1.5 animate-streaming-dot rounded-full bg-primary [animation-delay:0ms]" />
        <span className="h-1.5 w-1.5 animate-streaming-dot rounded-full bg-primary [animation-delay:150ms]" />
        <span className="h-1.5 w-1.5 animate-streaming-dot rounded-full bg-primary [animation-delay:300ms]" />
      </span>
      <span className="text-[10px] uppercase tracking-wide">streaming</span>
    </span>
  );
}

function Avatar({ isUser }: { isUser: boolean }) {
  return (
    <div
      className={cn(
        "flex h-9 w-9 shrink-0 items-center justify-center rounded-full border text-foreground",
        isUser
          ? "border-border bg-background"
          : "border-primary/30 bg-primary/10 text-primary",
      )}
      aria-hidden
    >
      {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
    </div>
  );
}

function ToolCallList({
  calls,
  defaultOpen,
}: {
  calls: ToolCallView[];
  defaultOpen?: boolean;
}) {
  if (calls.length === 0) return null;
  return (
    <ul className="space-y-1.5">
      {calls.map((call) => {
        const depth = call.agentPath?.length ?? 0;
        return (
          <li
            key={call.id}
            className="rounded-md border border-border bg-muted/40 text-xs"
            style={depth > 0 ? { marginLeft: depth * 12 } : undefined}
          >
            <details className="group/tool" open={defaultOpen}>
              <summary className="flex cursor-pointer list-none items-center gap-2 px-2 py-1.5 [&::-webkit-details-marker]:hidden">
                <ChevronRight className="h-3 w-3 text-muted-foreground transition-transform group-open/tool:rotate-90" />
                <Wrench className="h-3 w-3 text-muted-foreground" />
                <span className="font-mono">{call.name}</span>
                {depth > 0 ? <SubAgentBadge path={call.agentPath ?? []} /> : null}
                {call.pending ? (
                  <Badge variant="warning" className="ml-auto px-1 py-0 text-[10px]">
                    running…
                  </Badge>
                ) : (
                  <Badge variant="success" className="ml-auto px-1 py-0 text-[10px]">
                    done
                  </Badge>
                )}
              </summary>
              <div className="space-y-2 px-2 pb-2 font-mono text-[11px] text-muted-foreground">
                {call.args !== undefined ? (
                  <div>
                    <div className="font-semibold text-foreground">args</div>
                    <pre className="overflow-auto whitespace-pre-wrap">
                      {typeof call.args === "string"
                        ? call.args
                        : JSON.stringify(call.args, null, 2)}
                    </pre>
                  </div>
                ) : null}
                {call.result !== undefined ? (
                  <div>
                    <div className="font-semibold text-foreground">result</div>
                    <pre className="overflow-auto whitespace-pre-wrap">
                      {typeof call.result === "string"
                        ? call.result
                        : JSON.stringify(call.result, null, 2)}
                    </pre>
                  </div>
                ) : null}
              </div>
            </details>
          </li>
        );
      })}
    </ul>
  );
}

function SubAgentBadge({ path }: { path: string[] }) {
  if (path.length === 0) return null;
  return (
    <Badge
      variant="outline"
      className="gap-1 border-primary/40 px-1 py-0 text-[10px] font-normal text-primary"
      title={`Sub-agent: ${path.join(" › ")}`}
    >
      <Bot className="h-2.5 w-2.5" />
      <span className="font-mono">{path.join(" › ")}</span>
    </Badge>
  );
}

interface AttachmentChipsProps {
  attachments: FileMetadata[];
}

export function AttachmentChips({ attachments }: AttachmentChipsProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {attachments.map((att) => (
        <AttachmentChip key={att.file_id} attachment={att} />
      ))}
    </div>
  );
}

function useAttachmentDownload() {
  return useMemo(() => {
    return async (attachment: FileMetadata) => {
      const base = getApiBaseUrl();
      const token = getApiToken();
      const headers: Record<string, string> = {};
      if (token) headers.Authorization = `Bearer ${token}`;
      const response = await fetch(
        `${base}/api/v1/files/${encodeURIComponent(attachment.file_id)}`,
        { headers },
      );
      if (!response.ok) {
        throw new Error(`Download failed: ${response.statusText}`);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = attachment.name;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    };
  }, []);
}

function AttachmentChip({ attachment }: { attachment: FileMetadata }) {
  const download = useAttachmentDownload();
  const isImage = attachment.mime.startsWith("image/");
  const Icon = isImage ? ImageIcon : FileText;
  return (
    <button
      type="button"
      onClick={() => download(attachment)}
      className="group inline-flex items-center gap-2 rounded-md border border-border bg-muted/40 px-2.5 py-1 text-xs transition-colors hover:border-primary/40 hover:bg-muted"
      title={`Download ${attachment.name}`}
    >
      <Icon className="h-3.5 w-3.5 text-muted-foreground group-hover:text-foreground" />
      <span className="font-medium">{attachment.name}</span>
      <span className="text-muted-foreground">{formatBytes(attachment.size)}</span>
      <Download className="h-3 w-3 text-muted-foreground group-hover:text-foreground" />
    </button>
  );
}

export function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}
