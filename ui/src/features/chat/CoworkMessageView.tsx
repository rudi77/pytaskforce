/**
 * Cowork-style message rendering.
 *
 * - User turns are right-aligned chips on a muted background (like a chat
 *   bubble), max ~70 % width.
 * - Assistant turns flow full-width without a bubble — Markdown takes
 *   the foreground, so the agent's reply reads like a document. Above
 *   the body, a single collapsed "Tool-Summary" line shows what the
 *   agent did (count of tools, files, commands). Expanding it reveals
 *   the existing ToolCallList.
 *
 * The legacy ``MessageBubble`` from ``MessageView.tsx`` is preserved
 * because other surfaces (sub-agent inspector, tests) still rely on
 * it; the chat page now uses these variants instead.
 */

import { useMemo, useState } from "react";
import {
  ChevronRight,
  Wrench,
  Bot,
  FileEdit,
  Terminal as TerminalIcon,
  Globe,
} from "lucide-react";

import { cn } from "@/lib/utils";
import type { ChatMessage, FileMetadata } from "@/api/queries";
import type { ToolCallView } from "@/features/chat/useChatStream";
import { Badge } from "@/components/ui/badge";
import { MessageContent, partsFromContent } from "@/features/chat/MessageContent";
import type { ChatViewMode } from "@/features/chat/useChatPreferences";
import type { WidgetEventHandler } from "@/features/chat/widgets/types";
import { AttachmentChips } from "@/features/chat/MessageView";

interface CoworkMessageProps {
  message: ChatMessage;
  pending?: boolean;
  toolCalls?: ToolCallView[];
  onWidgetEvent?: WidgetEventHandler;
  viewMode?: ChatViewMode;
}

export function CoworkMessage({
  message,
  pending,
  toolCalls,
  onWidgetEvent,
  viewMode = "normal",
}: CoworkMessageProps) {
  if (message.role === "user") {
    return <UserChip message={message} />;
  }
  if (message.role === "tool") {
    // In Cowork the raw tool turns never appear inline — they're folded
    // into the assistant's preceding turn via the tool-summary chip. We
    // keep them hidden here.
    return null;
  }
  return (
    <AssistantTurn
      message={message}
      pending={pending}
      toolCalls={toolCalls}
      onWidgetEvent={onWidgetEvent}
      viewMode={viewMode}
    />
  );
}

// ---------------------------------------------------------------------------
// User turn — small right-aligned bubble
// ---------------------------------------------------------------------------

function UserChip({ message }: { message: ChatMessage }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[70%] rounded-2xl bg-muted px-4 py-2.5 text-[15px] leading-relaxed text-foreground">
        {message.content}
        {message.attachments && message.attachments.length > 0 ? (
          <div className="mt-2">
            <AttachmentChips attachments={message.attachments} />
          </div>
        ) : null}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Assistant turn — flowing layout
// ---------------------------------------------------------------------------

function AssistantTurn({
  message,
  pending,
  toolCalls,
  onWidgetEvent,
  viewMode = "normal",
}: CoworkMessageProps) {
  const parts = partsFromContent(message.content, message.parts);
  const showToolSummary =
    viewMode !== "summary" && toolCalls && toolCalls.length > 0;
  const expandToolDefault = viewMode === "verbose";

  const hasBody =
    (typeof message.content === "string" && message.content.length > 0) ||
    (Array.isArray(message.parts) && message.parts.length > 0);

  return (
    <article className="space-y-3 px-1 py-2">
      {showToolSummary ? (
        <ToolSummary
          calls={toolCalls!}
          defaultOpen={expandToolDefault}
          stillRunning={!!pending}
        />
      ) : null}

      {pending && !hasBody ? <StreamingDots /> : null}

      <div className="text-[15px] leading-relaxed">
        <MessageContent
          parts={parts}
          pending={pending}
          onWidgetEvent={onWidgetEvent}
        />
      </div>

      {message.attachments && message.attachments.length > 0 ? (
        <AttachmentChips attachments={message.attachments} />
      ) : null}
    </article>
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
      <span className="h-1.5 w-1.5 animate-streaming-dot rounded-full bg-primary [animation-delay:0ms]" />
      <span className="h-1.5 w-1.5 animate-streaming-dot rounded-full bg-primary [animation-delay:150ms]" />
      <span className="h-1.5 w-1.5 animate-streaming-dot rounded-full bg-primary [animation-delay:300ms]" />
    </span>
  );
}

// ---------------------------------------------------------------------------
// Tool-summary chip — Cowork's "18 Tools verwendet, 13 Dateien gelesen, …"
// ---------------------------------------------------------------------------

interface ToolStats {
  tools: number;
  filesRead: number;
  filesWritten: number;
  commands: number;
}

function summarize(calls: ToolCallView[]): ToolStats {
  let filesRead = 0;
  let filesWritten = 0;
  let commands = 0;
  for (const c of calls) {
    if (c.name === "file_read") filesRead += 1;
    else if (c.name === "file_write" || c.name === "edit") filesWritten += 1;
    else if (c.name === "shell" || c.name === "bash" || c.name === "powershell") {
      commands += 1;
    }
  }
  return { tools: calls.length, filesRead, filesWritten, commands };
}

function ToolSummary({
  calls,
  defaultOpen,
  stillRunning,
}: {
  calls: ToolCallView[];
  defaultOpen?: boolean;
  stillRunning?: boolean;
}) {
  const [open, setOpen] = useState(!!defaultOpen);
  const stats = useMemo(() => summarize(calls), [calls]);

  const parts: string[] = [];
  parts.push(`${stats.tools} Tool${stats.tools !== 1 ? "s" : ""} verwendet`);
  if (stats.filesRead > 0) parts.push(`${stats.filesRead} Dateien gelesen`);
  if (stats.filesWritten > 0) parts.push(`${stats.filesWritten} Dateien geschrieben`);
  if (stats.commands > 0) parts.push(`${stats.commands} Befehle ausgeführt`);

  return (
    <div className="rounded-lg border border-border bg-muted/30">
      <button
        type="button"
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-muted-foreground hover:text-foreground"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <Wrench className="h-3.5 w-3.5" />
        <span>{parts.join(", ")}</span>
        {stillRunning ? (
          <Badge variant="warning" className="px-1 py-0 text-[10px]">
            läuft
          </Badge>
        ) : null}
        <ChevronRight
          className={cn(
            "ml-auto h-3.5 w-3.5 transition-transform",
            open && "rotate-90",
          )}
        />
      </button>
      {open ? (
        <ul className="space-y-1.5 border-t border-border px-3 py-2">
          {calls.map((call) => (
            <ToolRow key={call.id} call={call} />
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function ToolIcon({ name }: { name: string }) {
  if (name === "shell" || name === "bash" || name === "powershell") {
    return <TerminalIcon className="h-3 w-3 text-muted-foreground" />;
  }
  if (name === "file_write" || name === "edit") {
    return <FileEdit className="h-3 w-3 text-muted-foreground" />;
  }
  if (name === "web_search" || name === "web_fetch") {
    return <Globe className="h-3 w-3 text-muted-foreground" />;
  }
  return <Wrench className="h-3 w-3 text-muted-foreground" />;
}

function ToolRow({ call }: { call: ToolCallView }) {
  const depth = call.agentPath?.length ?? 0;
  return (
    <li
      className="rounded-md border border-border bg-card/60 text-xs"
      style={depth > 0 ? { marginLeft: depth * 12 } : undefined}
    >
      <details className="group">
        <summary className="flex cursor-pointer list-none items-center gap-2 px-2 py-1 [&::-webkit-details-marker]:hidden">
          <ChevronRight className="h-3 w-3 text-muted-foreground transition-transform group-open:rotate-90" />
          <ToolIcon name={call.name} />
          <span className="font-mono">{call.name}</span>
          {depth > 0 ? <SubAgentBadge path={call.agentPath ?? []} /> : null}
          <span className="ml-auto text-[10px] text-muted-foreground">
            {call.pending ? "läuft…" : "fertig"}
          </span>
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

// Re-export the file metadata type so consumers don't need a separate import.
export type { FileMetadata };
