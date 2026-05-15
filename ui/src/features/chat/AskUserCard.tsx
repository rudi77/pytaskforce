import { useEffect, useRef, useState } from "react";
import { CornerDownRight, HelpCircle, Send } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type { PendingAskUser } from "@/features/chat/useChatStream";

interface AskUserCardProps {
  prompt: PendingAskUser;
  /** Send the user's answer through the same path as a normal chat message;
   *  the executor resumes the paused state on the server side. */
  onAnswer: (answer: string) => void;
  /** True while the previous send is still in flight, so the input can be
   *  disabled to avoid double-sends. */
  disabled?: boolean;
}

/**
 * Inline prompt card that surfaces a paused agent's ``ask_user`` request.
 *
 * Two flavours:
 *
 *   - **Chat-side question** (no ``channel``): renders a focusable textarea
 *     and a Send button. Submitting the answer just calls ``onAnswer`` —
 *     the parent feeds it into the existing ``send()`` flow, which appends
 *     a normal user message; the backend executor resumes the paused
 *     session from that message.
 *
 *   - **Channel-targeted question** (``channel`` + ``recipient_id`` set):
 *     the answer is expected on the named channel (e.g. Telegram), not in
 *     the chat UI. The card explains this so the user doesn't waste typing
 *     here. ``missing`` fields are still listed for context.
 */
export function AskUserCard({ prompt, onAnswer, disabled }: AskUserCardProps) {
  const [draft, setDraft] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // Auto-focus when a fresh prompt appears so the user can just start
  // typing the answer. Re-focuses if the prompt text changes (rare but
  // possible if the agent re-asks).
  useEffect(() => {
    if (!prompt.channel) {
      textareaRef.current?.focus();
    }
  }, [prompt.question, prompt.channel]);

  const handleSubmit = () => {
    const trimmed = draft.trim();
    if (!trimmed) return;
    onAnswer(trimmed);
    setDraft("");
  };

  const onKeyDown: React.KeyboardEventHandler<HTMLTextAreaElement> = (e) => {
    if (
      e.key === "Enter" &&
      !e.shiftKey &&
      (e.metaKey || e.ctrlKey || !e.nativeEvent.isComposing)
    ) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const channelTargeted = Boolean(prompt.channel);

  return (
    <div
      role="region"
      aria-label="Agent is asking for input"
      className={cn(
        "mx-auto w-full max-w-3xl rounded-xl border-2 border-amber-400/60 bg-amber-50/40 p-4 shadow-sm",
        "dark:border-amber-500/40 dark:bg-amber-500/5",
      )}
    >
      <header className="mb-2 flex items-center gap-2">
        <span
          className="flex h-7 w-7 items-center justify-center rounded-full border border-amber-500/60 bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-200"
          aria-hidden
        >
          <HelpCircle className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-300">
            Agent is asking
          </p>
          {channelTargeted ? (
            <p className="text-[11px] text-muted-foreground">
              Answer expected on{" "}
              <span className="font-medium">{prompt.channel}</span>
              {prompt.recipientId ? (
                <>
                  {" "}
                  · recipient{" "}
                  <span className="font-mono">{prompt.recipientId}</span>
                </>
              ) : null}
            </p>
          ) : null}
        </div>
      </header>

      {prompt.question ? (
        <p className="mb-2 whitespace-pre-wrap text-sm leading-relaxed text-foreground">
          {prompt.question}
        </p>
      ) : null}

      {prompt.missing.length > 0 ? (
        <div className="mb-2 flex flex-wrap items-center gap-1.5 text-xs">
          <span className="text-muted-foreground">Needs:</span>
          {prompt.missing.map((field) => (
            <Badge key={field} variant="outline" className="font-mono text-[10px]">
              {field}
            </Badge>
          ))}
        </div>
      ) : null}

      {channelTargeted ? (
        <p className="mt-2 text-xs italic text-muted-foreground">
          The agent is paused. It will resume automatically once an answer
          arrives on the channel above. You can also reply here to provide
          the answer manually.
        </p>
      ) : null}

      <div className="mt-3 flex flex-col gap-2">
        <Textarea
          ref={textareaRef}
          rows={2}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={
            channelTargeted
              ? "Type an answer here to override the channel reply…"
              : "Type your answer…"
          }
          className="resize-none border-amber-300/60 bg-background/80 text-sm focus-visible:ring-amber-500/40 dark:border-amber-500/30"
          disabled={disabled}
          aria-label="Answer to agent question"
        />
        <div className="flex items-center justify-end gap-2">
          <span className="mr-auto text-[11px] text-muted-foreground">
            <CornerDownRight className="mr-1 inline h-3 w-3" />
            ⌘/Ctrl + Enter to send
          </span>
          <Button
            type="button"
            size="sm"
            onClick={handleSubmit}
            disabled={disabled || draft.trim().length === 0}
          >
            <Send className="h-3.5 w-3.5" />
            Send answer
          </Button>
        </div>
      </div>
    </div>
  );
}
