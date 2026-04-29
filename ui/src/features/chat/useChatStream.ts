import { useCallback, useRef, useState } from "react";
import { sseStream } from "@/api/client";

export interface ToolCallView {
  id: string;
  name: string;
  args?: unknown;
  result?: unknown;
  pending: boolean;
}

export interface AssistantStreamState {
  text: string;
  toolCalls: ToolCallView[];
  completed: boolean;
}

interface SseEnvelope {
  event_type?: string;
  message?: string;
  details?: Record<string, unknown> | null;
}

export interface SendStreamingArgs {
  conversationId: string;
  message: string;
  attachments: { file_id: string }[];
  profile?: string;
}

const EMPTY_STATE: AssistantStreamState = { text: "", toolCalls: [], completed: false };

export function useChatStream() {
  const [state, setState] = useState<AssistantStreamState>(EMPTY_STATE);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const send = useCallback(
    async ({ conversationId, message, attachments, profile }: SendStreamingArgs) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setError(null);
      setState({ text: "", toolCalls: [], completed: false });
      setIsStreaming(true);

      try {
        const stream = sseStream(
          `/api/v1/conversations/${encodeURIComponent(conversationId)}/messages/stream`,
          {
            body: {
              message,
              ...(profile ? { profile } : {}),
              attachments,
            },
          },
          controller.signal,
        );
        for await (const evt of stream) {
          let payload: SseEnvelope = {};
          try {
            payload = JSON.parse(evt.data) as SseEnvelope;
          } catch {
            continue;
          }
          handleEvent(evt.event, payload, setState);
        }
      } catch (err) {
        if (controller.signal.aborted) {
          return;
        }
        setError((err as Error).message ?? String(err));
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
        setIsStreaming(false);
      }
    },
    [],
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const reset = useCallback(() => setState(EMPTY_STATE), []);

  return { state, isStreaming, error, send, cancel, reset };
}

function handleEvent(
  eventName: string | undefined,
  payload: SseEnvelope,
  setState: React.Dispatch<React.SetStateAction<AssistantStreamState>>,
): void {
  if (eventName === "assistant_persisted") {
    setState((prev) => ({ ...prev, completed: true }));
    return;
  }
  if (eventName === "message_persisted") return;

  const type = payload.event_type;
  const details = (payload.details ?? {}) as Record<string, unknown>;
  switch (type) {
    case "llm_token": {
      const token =
        (typeof details.token === "string" && details.token) ||
        (typeof payload.message === "string" ? payload.message : "");
      if (token) {
        setState((prev) => ({ ...prev, text: prev.text + token }));
      }
      break;
    }
    case "tool_call": {
      const id = String(details.tool_call_id ?? `call-${Date.now()}-${Math.random()}`);
      const name = String(details.tool ?? details.name ?? "tool");
      const args = details.arguments ?? details.args;
      setState((prev) => ({
        ...prev,
        toolCalls: [...prev.toolCalls, { id, name, args, pending: true }],
      }));
      break;
    }
    case "tool_result": {
      const id = String(details.tool_call_id ?? "");
      const result = details.result ?? details.output ?? payload.message;
      setState((prev) => ({
        ...prev,
        toolCalls: prev.toolCalls.map((tc) =>
          tc.id === id || (!id && tc.pending) ? { ...tc, result, pending: false } : tc,
        ),
      }));
      break;
    }
    case "final_answer": {
      const finalText = (typeof details.content === "string" && details.content) || payload.message;
      if (typeof finalText === "string" && finalText.length > 0) {
        setState((prev) => ({ ...prev, text: finalText }));
      }
      break;
    }
    case "complete": {
      setState((prev) => ({ ...prev, completed: true }));
      break;
    }
    case "error": {
      const msg = typeof details.error === "string" ? details.error : payload.message ?? "Stream error";
      setState((prev) => ({ ...prev, text: prev.text + `\n\n_Error: ${msg}_` }));
      break;
    }
    default:
      break;
  }
}
