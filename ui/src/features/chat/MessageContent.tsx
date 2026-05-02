import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";
import { WidgetRenderer } from "./widgets/WidgetRenderer";
import type { MessagePart, WidgetEventHandler } from "./widgets/types";

interface MessageContentProps {
  parts: MessagePart[];
  pending?: boolean;
  messageId?: string;
  onWidgetEvent?: WidgetEventHandler;
}

/**
 * Renders the body of a chat message as a sequence of typed parts.
 *
 * `text` parts are rendered as Markdown (GFM); `widget` parts use the typed
 * WidgetRenderer. A bare-string `content` field can be normalised into
 * `[{type: "text", text: ...}]` via `partsFromContent`.
 */
export function MessageContent({
  parts,
  pending,
  messageId,
  onWidgetEvent,
}: MessageContentProps) {
  if (parts.length === 0 && pending) {
    return <span className="animate-pulse text-muted-foreground">▍</span>;
  }
  return (
    <div className="space-y-3">
      {parts.map((part, idx) => {
        if (part.type === "text") {
          return (
            <div
              key={idx}
              className={cn(
                "prose prose-sm max-w-none break-words leading-relaxed dark:prose-invert",
                "prose-p:my-2 prose-p:leading-relaxed prose-pre:my-2 prose-headings:mt-3",
              )}
            >
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  code({ className, children, ...props }) {
                    return (
                      <code
                        className={cn(
                          "rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]",
                          className,
                        )}
                        {...props}
                      >
                        {children}
                      </code>
                    );
                  },
                  pre: ({ children }) => (
                    <pre className="overflow-auto scrollbar-thin rounded-md border border-border bg-muted/60 p-3 text-xs">
                      {children}
                    </pre>
                  ),
                  table: ({ children }) => (
                    <div className="my-2 overflow-auto scrollbar-thin rounded-md border border-border">
                      <table className="min-w-full divide-y divide-border text-sm">
                        {children}
                      </table>
                    </div>
                  ),
                }}
              >
                {part.text || (pending && idx === parts.length - 1 ? "▍" : "")}
              </ReactMarkdown>
            </div>
          );
        }
        return (
          <WidgetRenderer
            key={idx}
            widget={part.widget}
            widgetId={part.widgetId}
            messageId={messageId}
            onEvent={onWidgetEvent}
          />
        );
      })}
    </div>
  );
}

export function partsFromContent(
  content: string | undefined,
  parts?: MessagePart[],
): MessagePart[] {
  if (parts && parts.length > 0) return parts;
  if (!content) return [];
  return [{ type: "text", text: content }];
}
