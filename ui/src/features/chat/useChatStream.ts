import { useCallback, useRef, useState } from "react";
import { apiFetch, sseStream } from "@/api/client";

export interface ToolCallView {
  id: string;
  name: string;
  args?: unknown;
  result?: unknown;
  pending: boolean;
  /** Hierarchical chain of specialists when the call originated from a
   *  sub-agent (e.g. ``["coding_worker"]`` or ``["planner", "worker"]``).
   *  ``null`` for tool calls from the root agent. */
  agentPath?: string[] | null;
  /** Specialist label of the agent that emitted the call (matches the
   *  last entry of ``agentPath``). */
  sourceAgent?: string | null;
}

export interface AssistantStreamState {
  text: string;
  toolCalls: ToolCallView[];
  completed: boolean;
  /** Server-side session id, captured from the ``started`` SSE event. Needed
   *  for cooperative interruption via ``POST /api/v1/execute/{id}/cancel``. */
  sessionId: string | null;
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
  agentId?: string;
}

const EMPTY_STATE: AssistantStreamState = {
  text: "",
  toolCalls: [],
  completed: false,
  sessionId: null,
};

export function useChatStream() {
  const [state, setState] = useState<AssistantStreamState>(EMPTY_STATE);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  // Mirrors ``state.sessionId`` for use inside ``cancel`` without triggering a
  // re-render-driven stale closure. The state copy is what UI reads; this one
  // is what the cancel handler reads.
  const sessionIdRef = useRef<string | null>(null);

  const send = useCallback(
    async ({ conversationId, message, attachments, profile, agentId }: SendStreamingArgs) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      sessionIdRef.current = null;
      setError(null);
      setState({ text: "", toolCalls: [], completed: false, sessionId: null });
      setIsStreaming(true);

      try {
        const stream = sseStream(
          `/api/v1/conversations/${encodeURIComponent(conversationId)}/messages/stream`,
          {
            body: {
              message,
              ...(profile ? { profile } : {}),
              ...(agentId ? { agent_id: agentId } : {}),
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
          handleEvent(evt.event, payload, setState, sessionIdRef);
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

  const cancel = useCallback(async () => {
    // Two-step cancellation: first ask the server to interrupt the agent
    // cooperatively (so it persists state + emits a final ``complete`` with
    // ``status=paused``), THEN tear down the SSE connection. Without the
    // first step, aborting the fetch only stops the client from receiving
    // events — the agent keeps running on the server until it finishes.
    const sessionId = sessionIdRef.current;
    if (sessionId) {
      try {
        await apiFetch<{ session_id: string; status: string }>(
          `/api/v1/execute/${encodeURIComponent(sessionId)}/cancel`,
          { method: "POST" },
        );
      } catch {
        // 404 (session already completed) or transient network errors
        // shouldn't prevent the client-side abort below.
      }
    }
    abortRef.current?.abort();
  }, []);

  const reset = useCallback(() => {
    sessionIdRef.current = null;
    setState(EMPTY_STATE);
  }, []);

  return { state, isStreaming, error, send, cancel, reset };
}

function handleEvent(
  eventName: string | undefined,
  payload: SseEnvelope,
  setState: React.Dispatch<React.SetStateAction<AssistantStreamState>>,
  sessionIdRef: React.MutableRefObject<string | null>,
): void {
  if (eventName === "assistant_persisted") {
    setState((prev) => ({ ...prev, completed: true }));
    return;
  }
  if (eventName === "message_persisted") return;

  const type = payload.event_type;
  const details = (payload.details ?? {}) as Record<string, unknown>;
  switch (type) {
    case "started": {
      const sid = typeof details.session_id === "string" ? details.session_id : null;
      if (sid) {
        sessionIdRef.current = sid;
        setState((prev) => ({ ...prev, sessionId: sid }));
      }
      break;
    }
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
      const id = String(
        details.tool_call_id ?? details.id ?? `call-${Date.now()}-${Math.random()}`,
      );
      const name = String(details.tool ?? details.name ?? "tool");
      const args = details.arguments ?? details.args;
      const agentPath = Array.isArray(details.agent_path)
        ? (details.agent_path as string[])
        : null;
      const sourceAgent =
        typeof details.source_agent === "string" ? details.source_agent : null;
      setState((prev) => ({
        ...prev,
        toolCalls: [
          ...prev.toolCalls,
          { id, name, args, pending: true, agentPath, sourceAgent },
        ],
      }));
      break;
    }
    case "tool_result": {
      const id = String(details.tool_call_id ?? details.id ?? "");
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
