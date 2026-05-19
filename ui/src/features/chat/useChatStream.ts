import { useCallback, useEffect } from "react";
import { create } from "zustand";

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

export interface PendingAskUser {
  question: string;
  /** Hint listing the structured fields the agent still needs (free-form
   *  strings — typically short labels like ``["start_date", "end_date"]``).
   *  Empty when the agent just wants a freeform reply. */
  missing: string[];
  /** When set, the question is being routed to a specific channel (e.g.
   *  Telegram) rather than the chat UI; the chat-side prompt should make
   *  that explicit so the user doesn't think they need to answer here. */
  channel?: string | null;
  recipientId?: string | null;
}

/** One row of the Cowork-style progress panel. Derived from
 *  ``plan_updated`` SSE events. */
export interface PlanStepView {
  description: string;
  done: boolean;
}

export interface AssistantStreamState {
  text: string;
  toolCalls: ToolCallView[];
  /** Plan steps as last reported by the agent (Markdown checklist parsed
   *  into a structured form). Empty when the agent isn't using the
   *  PlannerTool. */
  planSteps: PlanStepView[];
  /** Set by the in-stream ``complete`` event — the LLM has finished, but
   *  the backend may not have persisted the assistant reply yet (the
   *  persist happens in the route's ``finally`` block, after this event
   *  fires). UI should optimistically show the streamed text but wait
   *  on ``persisted`` before triggering a refetch. */
  completed: boolean;
  /** Bumped (timestamp ms) by the ``assistant_persisted`` SSE event —
   *  the server has now written the assistant reply to conversation
   *  history. Refetching messages now is safe. We use a timestamp
   *  rather than a bool so consumers can ``useEffect`` on it across
   *  multiple completions in the same conversation. */
  persistedAt: number | null;
  /** Server-side session id, captured from the ``started`` SSE event. Needed
   *  for cooperative interruption via ``POST /api/v1/execute/{id}/cancel``. */
  sessionId: string | null;
  /** Populated by an ``ask_user`` event. Persists across stream-end so the
   *  prompt UI stays visible while the agent is paused waiting for input.
   *  Cleared when the user sends the next message. */
  pendingAskUser: PendingAskUser | null;
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
  planSteps: [],
  completed: false,
  persistedAt: null,
  sessionId: null,
  pendingAskUser: null,
};

const STREAM_STATE_STORAGE_KEY = "taskforce.chat.streamState.v1";

function readPersistedStreams(): Record<string, AssistantStreamState> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.sessionStorage.getItem(STREAM_STATE_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object"
      ? (parsed as Record<string, AssistantStreamState>)
      : {};
  } catch {
    return {};
  }
}

function persistStreamState(
  conversationId: string,
  state: AssistantStreamState,
): void {
  if (typeof window === "undefined") return;
  try {
    const streams = readPersistedStreams();
    streams[conversationId] = state;
    window.sessionStorage.setItem(
      STREAM_STATE_STORAGE_KEY,
      JSON.stringify(streams),
    );
  } catch {
    /* sessionStorage is best-effort UI state */
  }
}

function removePersistedStreamState(conversationId: string): void {
  if (typeof window === "undefined") return;
  try {
    const streams = readPersistedStreams();
    delete streams[conversationId];
    window.sessionStorage.setItem(
      STREAM_STATE_STORAGE_KEY,
      JSON.stringify(streams),
    );
  } catch {
    /* sessionStorage is best-effort UI state */
  }
}

function clearPersistedStreamState(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(STREAM_STATE_STORAGE_KEY);
  } catch {
    /* sessionStorage is best-effort UI state */
  }
}

/** Parse the PlannerTool's Markdown checklist (e.g. ``"[x] 1. fetch\n[ ] 2. write"``)
 *  into a structured plan-step list. Lines that don't match the checkbox shape
 *  are kept as plain pending entries so we never silently drop content. */
export function parsePlanMarkdown(plan: string): PlanStepView[] {
  if (!plan || plan.trim() === "" || plan.trim() === "No active plan.") {
    return [];
  }
  const steps: PlanStepView[] = [];
  for (const raw of plan.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    const match = line.match(/^\[( |x|X)\]\s*(?:\d+\.\s*)?(.*)$/);
    if (match) {
      const done = match[1].toLowerCase() === "x";
      const description = match[2].trim();
      if (description) steps.push({ description, done });
    } else {
      steps.push({ description: line, done: false });
    }
  }
  return steps;
}

// ---------------------------------------------------------------------------
// Global stream store
// ---------------------------------------------------------------------------
//
// Pre-#274 ``useChatStream`` owned its own component-local state via
// ``useState``. When the user navigated away from the chat page mid-run, the
// hook unmounted, the SSE ``for await`` loop's ``setState`` calls landed in
// a dead React tree, and on return the panel showed an empty stream — the
// agent was still busy on the server but the UI had no idea.
//
// Now state is keyed by conversationId in a module-scoped zustand store and
// the SSE iteration writes through ``setState`` of the store, not React
// component state. Navigation no longer interrupts streaming, and a
// re-mounted ``ChatPage`` instantly resubscribes to whatever the store
// currently holds for that conversation.

interface ChatStreamStore {
  /** Per-conversation stream state. Looked up at render time. */
  streams: Record<string, AssistantStreamState>;
  /** Per-conversation "is currently consuming SSE events" flag. */
  streamingByConversation: Record<string, boolean>;
  /** Per-conversation last error message. */
  errors: Record<string, string | null>;
  /** Most-recently-targeted conversationId, used as a fallback for the
   *  parameter-less ``useChatStream()`` form (legacy tests). */
  currentConversation: string | null;

  /** Patch one conversation's stream state. Caller passes either a
   *  partial replacement OR a transform function — same ergonomics as
   *  ``setState``. */
  patchStream: (
    conversationId: string,
    patch:
      | Partial<AssistantStreamState>
      | ((prev: AssistantStreamState) => AssistantStreamState),
  ) => void;
  setStreaming: (conversationId: string, streaming: boolean) => void;
  setError: (conversationId: string, error: string | null) => void;
  setCurrent: (conversationId: string | null) => void;
  resetConversation: (conversationId: string) => void;
  resetAll: () => void;
}

const useChatStreamStore = create<ChatStreamStore>((set) => ({
  streams: {},
  streamingByConversation: {},
  errors: {},
  currentConversation: null,

  patchStream: (conversationId, patch) =>
    set((state) => {
      const prev = state.streams[conversationId] ?? EMPTY_STATE;
      const next = typeof patch === "function" ? patch(prev) : { ...prev, ...patch };
      persistStreamState(conversationId, next);
      return {
        streams: { ...state.streams, [conversationId]: next },
      };
    }),
  setStreaming: (conversationId, streaming) =>
    set((state) => ({
      streamingByConversation: {
        ...state.streamingByConversation,
        [conversationId]: streaming,
      },
    })),
  setError: (conversationId, error) =>
    set((state) => ({
      errors: { ...state.errors, [conversationId]: error },
    })),
  setCurrent: (conversationId) =>
    set({ currentConversation: conversationId }),
  resetConversation: (conversationId) =>
    set((state) => {
      const streams = { ...state.streams };
      const streaming = { ...state.streamingByConversation };
      const errors = { ...state.errors };
      delete streams[conversationId];
      delete streaming[conversationId];
      delete errors[conversationId];
      removePersistedStreamState(conversationId);
      return {
        streams,
        streamingByConversation: streaming,
        errors,
      };
    }),
  resetAll: () =>
    set({
      streams: {},
      streamingByConversation: {},
      errors: {},
      currentConversation: null,
    }),
}));

// AbortControllers can't go through zustand: they're not serialisable and we
// don't want their identity to trigger re-renders. Module-scope map keyed
// by conversationId means a re-mounted hook still reaches the in-flight
// controller of the previous mount.
const _abortControllers = new Map<string, AbortController>();

/** Test-only reset. Wipes all stream state AND in-flight controllers. */
export function __resetChatStreamStore(
  options: { clearPersisted?: boolean } = {},
) {
  for (const ctrl of _abortControllers.values()) {
    try {
      ctrl.abort();
    } catch {
      /* nothing */
    }
  }
  _abortControllers.clear();
  if (options.clearPersisted !== false) {
    clearPersistedStreamState();
  }
  useChatStreamStore.getState().resetAll();
}

// ---------------------------------------------------------------------------
// SSE drive — lives at module scope, NOT inside a hook.
// ---------------------------------------------------------------------------

async function drive(args: SendStreamingArgs): Promise<void> {
  const { conversationId, message, attachments, profile, agentId } = args;
  const store = useChatStreamStore.getState();

  // Replace any in-flight controller for this conversation so a fresh send
  // supersedes the previous one cleanly (matches the legacy single-flight
  // behaviour).
  const existing = _abortControllers.get(conversationId);
  if (existing) {
    existing.abort();
  }
  const controller = new AbortController();
  _abortControllers.set(conversationId, controller);
  store.setCurrent(conversationId);
  store.setError(conversationId, null);
  // Reset the per-conversation state — ``pendingAskUser`` clears because
  // the user's new message *is* the answer to the previous question; the
  // executor resumes from saved state on its own side.
  store.patchStream(conversationId, () => ({
    text: "",
    toolCalls: [],
    planSteps: [],
    completed: false,
    persistedAt: null,
    sessionId: null,
    pendingAskUser: null,
  }));
  store.setStreaming(conversationId, true);

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
      handleEvent(conversationId, evt.event, payload);
    }
  } catch (err) {
    if (controller.signal.aborted) {
      return;
    }
    store.setError(conversationId, (err as Error).message ?? String(err));
  } finally {
    if (_abortControllers.get(conversationId) === controller) {
      _abortControllers.delete(conversationId);
    }
    useChatStreamStore.getState().setStreaming(conversationId, false);
  }
}

async function cancelStream(conversationId: string): Promise<void> {
  // Two-step cancellation: first ask the server to interrupt the agent
  // cooperatively (so it persists state + emits a final ``complete`` with
  // ``status=paused``), THEN tear down the SSE connection. Without the
  // first step, aborting the fetch only stops the client from receiving
  // events — the agent keeps running on the server until it finishes.
  const sessionId =
    useChatStreamStore.getState().streams[conversationId]?.sessionId ?? null;
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
  _abortControllers.get(conversationId)?.abort();
}

// ---------------------------------------------------------------------------
// Public hook
// ---------------------------------------------------------------------------

/**
 * Read + drive chat streaming state for a single conversation.
 *
 * Passing ``conversationId`` is strongly preferred — it scopes state per
 * conversation so navigating away and back doesn't lose in-flight tool
 * calls or plan steps. Omitting it falls back to whichever conversation
 * was most recently the target of ``send()`` (legacy single-stream
 * behaviour, kept for tests and any code that drives only one
 * conversation at a time).
 */
export function useChatStream(conversationId?: string) {
  const currentFromStore = useChatStreamStore((s) => s.currentConversation);
  const activeId = conversationId ?? currentFromStore;

  const state = useChatStreamStore((s) =>
    activeId
      ? s.streams[activeId] ??
        readPersistedStreams()[activeId] ??
        EMPTY_STATE
      : EMPTY_STATE,
  );
  const isStreaming = useChatStreamStore((s) =>
    activeId ? !!s.streamingByConversation[activeId] : false,
  );
  const error = useChatStreamStore((s) =>
    activeId ? s.errors[activeId] ?? null : null,
  );

  useEffect(() => {
    if (!activeId) return;
    const store = useChatStreamStore.getState();
    if (store.streams[activeId]) return;
    const persisted = readPersistedStreams()[activeId];
    if (persisted) {
      store.patchStream(activeId, persisted);
    }
  }, [activeId]);

  const send = useCallback(async (args: SendStreamingArgs) => {
    await drive(args);
  }, []);

  const cancel = useCallback(async () => {
    if (!activeId) return;
    await cancelStream(activeId);
  }, [activeId]);

  const reset = useCallback(() => {
    if (!activeId) return;
    useChatStreamStore.getState().resetConversation(activeId);
  }, [activeId]);

  return { state, isStreaming, error, send, cancel, reset };
}

// ---------------------------------------------------------------------------
// Event dispatcher
// ---------------------------------------------------------------------------

function handleEvent(
  conversationId: string,
  eventName: string | undefined,
  payload: SseEnvelope,
): void {
  const { patchStream } = useChatStreamStore.getState();

  if (eventName === "assistant_persisted") {
    // Server-side write of the assistant reply is complete; mark the
    // moment so consumers can safely trigger a refetch without racing
    // the backend's write. ``completed`` is also bumped here so a
    // run that never emitted an in-stream ``complete`` event (e.g.
    // pure content-filter recovery path) still flips out of "live".
    patchStream(conversationId, (prev) => ({
      ...prev,
      completed: true,
      persistedAt: Date.now(),
    }));
    return;
  }
  if (eventName === "message_persisted") return;

  const type = payload.event_type;
  const details = (payload.details ?? {}) as Record<string, unknown>;
  switch (type) {
    case "started": {
      const sid = typeof details.session_id === "string" ? details.session_id : null;
      if (sid) {
        patchStream(conversationId, (prev) => ({ ...prev, sessionId: sid }));
      }
      break;
    }
    case "llm_token": {
      const token =
        (typeof details.token === "string" && details.token) ||
        (typeof payload.message === "string" ? payload.message : "");
      if (token) {
        patchStream(conversationId, (prev) => ({ ...prev, text: prev.text + token }));
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
      patchStream(conversationId, (prev) => ({
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
      patchStream(conversationId, (prev) => ({
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
        patchStream(conversationId, (prev) => ({ ...prev, text: finalText }));
      }
      break;
    }
    case "plan_updated": {
      const planRaw =
        (typeof details.plan === "string" && details.plan) ||
        (Array.isArray(details.steps) ? details.steps.join("\n") : "");
      // Always replace — an empty plan ("No active plan.") must clear
      // the previous steps so the panel doesn't show a stale checklist
      // after the agent abandons its plan.
      const steps = parsePlanMarkdown(planRaw);
      patchStream(conversationId, (prev) => ({ ...prev, planSteps: steps }));
      break;
    }
    case "ask_user": {
      const question = typeof details.question === "string" ? details.question : "";
      const missingRaw = Array.isArray(details.missing) ? details.missing : [];
      const missing = missingRaw.filter(
        (m): m is string => typeof m === "string" && m.length > 0,
      );
      const channel =
        typeof details.channel === "string" && details.channel.length > 0
          ? details.channel
          : null;
      const recipientId =
        typeof details.recipient_id === "string" && details.recipient_id.length > 0
          ? details.recipient_id
          : null;
      // Only surface a prompt when there's *something* to show; otherwise
      // the agent's intent is unclear and a blank card looks broken.
      if (question || missing.length > 0) {
        patchStream(conversationId, (prev) => ({
          ...prev,
          pendingAskUser: { question, missing, channel, recipientId },
        }));
      }
      break;
    }
    case "complete": {
      patchStream(conversationId, (prev) => ({ ...prev, completed: true }));
      break;
    }
    case "error": {
      const msg = typeof details.error === "string" ? details.error : payload.message ?? "Stream error";
      patchStream(conversationId, (prev) => ({
        ...prev,
        text: prev.text + `\n\n_Error: ${msg}_`,
      }));
      break;
    }
    default:
      break;
  }
}
