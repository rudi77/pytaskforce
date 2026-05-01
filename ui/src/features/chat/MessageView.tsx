import { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Bot, Download, FileText, ImageIcon, Wrench } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { getApiBaseUrl, getApiToken } from "@/lib/settings";
import type { ChatMessage, FileMetadata } from "@/api/queries";
import type { ToolCallView } from "@/features/chat/useChatStream";

interface MessageBubbleProps {
  message: ChatMessage;
  pending?: boolean;
  toolCalls?: ToolCallView[];
}

export function MessageBubble({ message, pending, toolCalls }: MessageBubbleProps) {
  const isUser = message.role === "user";
  return (
    <div className={cn("flex gap-3", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[88%] rounded-lg border px-4 py-3 text-sm shadow-sm",
          isUser
            ? "border-primary/40 bg-primary/10 text-foreground"
            : "border-border bg-card",
        )}
      >
        <div className="mb-1 flex items-center gap-2 text-[10px] uppercase tracking-wide text-muted-foreground">
          <span>{isUser ? "You" : "Assistant"}</span>
          {pending ? <span className="animate-pulse text-primary">streaming…</span> : null}
        </div>
        {toolCalls && toolCalls.length > 0 ? <ToolCallList calls={toolCalls} /> : null}
        <div className="prose prose-sm max-w-none break-words dark:prose-invert">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              code({ className, children, ...props }) {
                return (
                  <code
                    className={cn(
                      "rounded bg-muted px-1 py-0.5 font-mono text-xs",
                      className,
                    )}
                    {...props}
                  >
                    {children}
                  </code>
                );
              },
              pre: ({ children }) => (
                <pre className="overflow-auto scrollbar-thin rounded-md bg-muted p-3 text-xs">
                  {children}
                </pre>
              ),
            }}
          >
            {message.content || (pending ? "▍" : "")}
          </ReactMarkdown>
        </div>
        {message.attachments && message.attachments.length > 0 ? (
          <AttachmentChips attachments={message.attachments} />
        ) : null}
      </div>
    </div>
  );
}

function ToolCallList({ calls }: { calls: ToolCallView[] }) {
  if (calls.length === 0) return null;
  return (
    <ul className="mb-2 space-y-1.5">
      {calls.map((call) => {
        const depth = call.agentPath?.length ?? 0;
        return (
          <li
            key={call.id}
            className="rounded-md border border-border bg-muted/40 text-xs"
            style={depth > 0 ? { marginLeft: depth * 12 } : undefined}
          >
            <details>
              <summary className="flex cursor-pointer items-center gap-2 px-2 py-1.5">
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
    <div className="mt-3 flex flex-wrap gap-2">
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
      className="group flex items-center gap-2 rounded-md border border-border bg-muted/40 px-2 py-1 text-xs transition-colors hover:border-primary/40"
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
