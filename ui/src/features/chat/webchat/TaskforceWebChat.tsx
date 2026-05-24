import { useEffect, useMemo, useRef } from "react";
import ReactWebChat from "botframework-webchat";

import type { ChatMessage } from "@/api/queries";

import { TaskforceDirectLine } from "./taskforceDirectLine";
import type { Activity, MessageActivity } from "./types";
import type { ToolCallView } from "../useChatStream";

interface Props {
  conversationId: string;
  /** Conversation history loaded from the server. */
  messages: ChatMessage[];
  /** Currently-streaming assistant text + tool calls, if any. */
  pending?: { text: string; toolCalls: ToolCallView[] };
}

/**
 * FluentUI-tinted styleOptions for `<ReactWebChat>`. Reads the same
 * Fluent CSS variables that `<FluentProvider>` injects, so the bubble
 * colors track the active light/dark theme automatically.
 *
 * Kept inline (rather than a hook) because WebChat re-instantiates a
 * full chat session whenever the `styleOptions` reference changes —
 * memoising via `useMemo` is enough.
 */
function useFluentStyleOptions() {
  return useMemo(
    () => ({
      // Surfaces
      backgroundColor: "var(--colorNeutralBackground1)",
      bubbleBackground: "var(--colorNeutralBackground3)",
      bubbleFromUserBackground: "var(--colorBrandBackground2)",
      bubbleBorderRadius: 12,
      bubbleFromUserBorderRadius: 12,
      bubbleBorderWidth: 0,
      bubbleFromUserBorderWidth: 0,
      // Text
      primaryFont: "var(--fontFamilyBase, Inter, system-ui, sans-serif)",
      fontSizeSmall: "0.75rem",
      bubbleTextColor: "var(--colorNeutralForeground1)",
      bubbleFromUserTextColor: "var(--colorNeutralForegroundOnBrand)",
      // Layout
      paddingRegular: 8,
      paddingWide: 16,
      // Hide built-in chrome we don't want
      hideSendBox: true, // chat composer lives in ChatPage, not inside WebChat
      hideUploadButton: true,
      hideScrollToEndButton: true,
      // Subtle send vs. receive distinction without shadows.
      // `showAvatarInGroup` requires the literal `true | "status" | "sender"`
      // — we don't show avatars at all, so leave it undefined.
      typingAnimationDuration: 4_000,
    }),
    [],
  );
}

/** Convert a server-side ChatMessage into a WebChat MessageActivity. */
function historyMessageToActivity(
  message: ChatMessage,
  conversationId: string,
  index: number,
): MessageActivity | null {
  const text =
    typeof message.content === "string"
      ? message.content
      : (message.parts ?? [])
          .map((p) => (p.type === "text" ? p.text : ""))
          .filter(Boolean)
          .join("\n");
  if (!text) return null;
  return {
    id: `history-${index}`,
    type: "message",
    timestamp: new Date(0).toISOString(),
    from:
      message.role === "user"
        ? { id: "user", role: "user" }
        : { id: "taskforce-agent", role: "bot", name: "Taskforce" },
    conversation: { id: conversationId },
    text,
  };
}

/**
 * Drives a `<ReactWebChat>` instance with a `TaskforceDirectLine`
 * adapter. Translates the existing `useChatStream` state (history +
 * streaming text + tool calls) into activities pushed onto the
 * adapter's stream, in the same shape `eventToActivity` would emit
 * for real SSE events.
 *
 * Opt-in via `useChatPreferences().useWebChatRenderer` — the Cowork-
 * style scroller remains the default. AskUserCard / MentionPicker /
 * RightPanel / composer stay outside this component and unchanged.
 */
export function TaskforceWebChat({ conversationId, messages, pending }: Props) {
  // One adapter per conversation. Re-mount the chat (new adapter)
  // whenever the conversation id changes.
  const adapterRef = useRef<TaskforceDirectLine | null>(null);
  if (!adapterRef.current || adapterRef.current.conversationId !== conversationId) {
    adapterRef.current?.end();
    adapterRef.current = new TaskforceDirectLine(conversationId);
  }
  const adapter = adapterRef.current;
  const styleOptions = useFluentStyleOptions();

  // Replay historical messages once per conversation load.
  const replayedRef = useRef<{ id: string; count: number }>({
    id: "",
    count: -1,
  });
  useEffect(() => {
    if (
      replayedRef.current.id === conversationId &&
      replayedRef.current.count === messages.length
    ) {
      return;
    }
    replayedRef.current = { id: conversationId, count: messages.length };
    messages.forEach((message, i) => {
      const activity = historyMessageToActivity(message, conversationId, i);
      if (activity) {
        adapter.activity$.next(activity as Activity);
      }
    });
  }, [conversationId, messages, adapter]);

  // Update / emit the in-progress assistant message as the stream
  // grows. Uses a stable "in-progress" id so WebChat replaces the same
  // activity instead of stacking dozens of bubbles.
  useEffect(() => {
    if (!pending) return;
    if (!pending.text) return;
    const inProgress: MessageActivity = {
      id: `in-progress-${conversationId}`,
      type: "message",
      timestamp: new Date().toISOString(),
      from: { id: "taskforce-agent", role: "bot", name: "Taskforce" },
      conversation: { id: conversationId },
      text: pending.text,
      channelData: { taskforce: { inProgress: true } },
    };
    adapter.activity$.next(inProgress);
  }, [pending?.text, conversationId, adapter, pending]);

  // Tear down the adapter when this component unmounts.
  useEffect(() => {
    return () => {
      adapterRef.current?.end();
      adapterRef.current = null;
    };
  }, []);

  // ReactWebChat insists on a non-null directLine and styleOptions
  // object reference. Cast the adapter — its surface is intentionally
  // a subset of the full DirectLine interface (WebChat reads only
  // `activity$`, `connectionStatus$`, `postActivity`, `end`).
  return (
    <div className="flex-1 overflow-hidden">
      <ReactWebChat
        directLine={adapter as unknown as Parameters<typeof ReactWebChat>[0]["directLine"]}
        styleOptions={styleOptions}
        userID="user"
        username="You"
        locale="en-US"
      />
    </div>
  );
}
