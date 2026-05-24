import type {
  Activity,
  AdapterSignal,
  MessageActivity,
  TaskforceEvent,
} from "./types";

/**
 * Attachment content-types we emit. Consumers wire matching renderers
 * via WebChat's `attachmentMiddleware`.
 */
export const ATTACHMENT_TOOL_CALL = "application/vnd.taskforce.tool-call+json";

const BOT_ID = "taskforce-agent";
const BOT_NAME = "Taskforce";

interface MappingContext {
  /** Conversation id used for every produced Activity. */
  conversationId: string;
  /** Monotonic counter; provides Activity ids. */
  seq: number;
  /** The activity id currently being grown by `llm_token`/`final_answer`. */
  inProgressAssistantActivityId: string | null;
}

export interface MappingResult {
  /** Activities to push to the WebChat activity$ stream. */
  activities: Activity[];
  /** Side-channel signals — drive ask_user overlay, plan panel, etc. */
  signals: AdapterSignal[];
  /** Mutated mapping context — caller threads it through subsequent calls. */
  ctx: MappingContext;
}

function nextId(ctx: MappingContext): { ctx: MappingContext; id: string } {
  const id = `tf-${ctx.seq}`;
  return { ctx: { ...ctx, seq: ctx.seq + 1 }, id };
}

function makeAssistantMessage(
  id: string,
  conversationId: string,
  text: string,
  inProgress: boolean,
): MessageActivity {
  return {
    id,
    type: "message",
    timestamp: new Date().toISOString(),
    from: { id: BOT_ID, name: BOT_NAME, role: "bot" },
    conversation: { id: conversationId },
    text,
    channelData: inProgress ? { taskforce: { inProgress: true } } : undefined,
  };
}

/** Initialise a fresh mapping context for a new conversation/session. */
export function createMappingContext(conversationId: string): MappingContext {
  return {
    conversationId,
    seq: 1,
    inProgressAssistantActivityId: null,
  };
}

/**
 * Pure-function adapter: maps one Taskforce SSE event to zero or more
 * DirectLine activities + zero or more side-channel signals.
 *
 * The function is deterministic given the `ctx`; consumers thread the
 * returned `ctx` into the next call so streaming `llm_token` events
 * grow the same assistant message instead of producing one per token.
 */
export function eventToActivity(
  event: TaskforceEvent,
  state: { ctx: MappingContext; assistantBuffer: string },
): MappingResult & { assistantBuffer: string } {
  const { ctx, assistantBuffer } = state;

  // The TaskforceEvent union includes a generic catch-all branch (any
  // `event_type: string`) so TypeScript can't narrow `event.details`
  // into the specific shape for the well-known branches. Read details
  // via a typed alias inside each case — final_answer/complete/error
  // don't have details and never reach this read.
  const detailsAny = ((event as { details?: Record<string, unknown> }).details ?? {}) as Record<
    string,
    unknown
  > & Record<string, never>;

  switch (event.event_type) {
    case "started": {
      const sessionId: string | undefined = detailsAny.session_id;
      const signals: AdapterSignal[] = sessionId
        ? [{ kind: "session_started", sessionId }]
        : [];
      return { ctx, activities: [], signals, assistantBuffer: "" };
    }

    case "llm_token": {
      // First token of a turn: mint a new assistant message activity and
      // mark it as the in-progress one. Subsequent tokens replace that
      // activity with the growing text so consumers see the streaming
      // bubble update in place.
      const token: string = (detailsAny.token as string | undefined) ?? event.message ?? "";
      if (!token) return { ctx, activities: [], signals: [], assistantBuffer };

      const nextBuffer = assistantBuffer + token;

      let activityId = ctx.inProgressAssistantActivityId;
      let nextCtx = ctx;
      if (!activityId) {
        const { ctx: c2, id } = nextId(ctx);
        activityId = id;
        nextCtx = { ...c2, inProgressAssistantActivityId: id };
      }

      return {
        ctx: nextCtx,
        activities: [
          makeAssistantMessage(activityId, nextCtx.conversationId, nextBuffer, true),
        ],
        signals: [],
        assistantBuffer: nextBuffer,
      };
    }

    case "tool_call": {
      // Tool calls are rendered as a custom-attachment message bubble.
      // We emit a brand-new activity (not the in-progress assistant
      // message) so WebChat shows the tool-call card distinctly.
      const { ctx: nextCtx, id } = nextId(ctx);
      const activity: MessageActivity = {
        id,
        type: "message",
        timestamp: new Date().toISOString(),
        from: { id: BOT_ID, name: BOT_NAME, role: "bot" },
        conversation: { id: nextCtx.conversationId },
        attachments: [
          {
            contentType: ATTACHMENT_TOOL_CALL,
            content: {
              tool_call_id: detailsAny.tool_call_id ?? null,
              name: detailsAny.name ?? "(unknown tool)",
              args: detailsAny.args ?? null,
              agent_path: detailsAny.agent_path ?? null,
              pending: true,
            },
          },
        ],
      };
      return { ctx: nextCtx, activities: [activity], signals: [], assistantBuffer };
    }

    case "tool_result": {
      // The tool-call attachment lives on its own activity; updating it
      // in place is overkill for the demo path. We emit a second
      // attachment activity carrying the result so consumers can render
      // a paired "result" card. The attachmentMiddleware on the
      // consumer side may choose to merge the two visually.
      const { ctx: nextCtx, id } = nextId(ctx);
      const activity: MessageActivity = {
        id,
        type: "message",
        timestamp: new Date().toISOString(),
        from: { id: BOT_ID, name: BOT_NAME, role: "bot" },
        conversation: { id: nextCtx.conversationId },
        attachments: [
          {
            contentType: ATTACHMENT_TOOL_CALL,
            content: {
              tool_call_id: detailsAny.tool_call_id ?? null,
              name: "(result)",
              result: detailsAny.result ?? null,
              error: detailsAny.error ?? null,
              pending: false,
            },
          },
        ],
      };
      return { ctx: nextCtx, activities: [activity], signals: [], assistantBuffer };
    }

    case "final_answer": {
      const text = event.message ?? assistantBuffer;
      const activityId = ctx.inProgressAssistantActivityId;
      if (activityId) {
        // Finalise the in-progress assistant message in place.
        const finalised = makeAssistantMessage(
          activityId,
          ctx.conversationId,
          text,
          false,
        );
        return {
          ctx: { ...ctx, inProgressAssistantActivityId: null },
          activities: [finalised],
          signals: [],
          assistantBuffer: "",
        };
      }
      // No streaming preamble — emit a fresh final message.
      const { ctx: nextCtx, id } = nextId(ctx);
      return {
        ctx: nextCtx,
        activities: [makeAssistantMessage(id, nextCtx.conversationId, text, false)],
        signals: [],
        assistantBuffer: "",
      };
    }

    case "plan_updated": {
      const steps: Array<{ description: string; done: boolean }> =
        detailsAny.steps ?? [];
      // Plan updates do NOT show as activities in the chat stream;
      // they're a side-channel signal consumed by the RightPanel.
      return {
        ctx,
        activities: [],
        signals: [{ kind: "plan_updated", steps }],
        assistantBuffer,
      };
    }

    case "ask_user": {
      // ask_user is OVERLAY-only — routed to AskUserCard, never injected
      // into the WebChat activity stream. Otherwise WebChat would
      // render a transient bot message that hangs around forever.
      const missing: string[] = detailsAny.missing ?? [];
      const channel: string | null = detailsAny.channel ?? null;
      const recipientId: string | null = detailsAny.recipient_id ?? null;
      return {
        ctx,
        activities: [],
        signals: [
          {
            kind: "ask_user",
            question: event.message ?? "",
            missing,
            channel,
            recipientId,
          },
        ],
        assistantBuffer,
      };
    }

    case "complete": {
      const activityId = ctx.inProgressAssistantActivityId;
      const activities: Activity[] = [];
      if (activityId && assistantBuffer) {
        activities.push(
          makeAssistantMessage(activityId, ctx.conversationId, assistantBuffer, false),
        );
      }
      return {
        ctx: { ...ctx, inProgressAssistantActivityId: null },
        activities,
        signals: [{ kind: "stream_completed" }],
        assistantBuffer: "",
      };
    }

    case "error": {
      const message = event.message ?? "Stream error";
      const { ctx: nextCtx, id } = nextId(ctx);
      const activity: MessageActivity = {
        id,
        type: "message",
        timestamp: new Date().toISOString(),
        from: { id: BOT_ID, name: BOT_NAME, role: "bot" },
        conversation: { id: nextCtx.conversationId },
        text: message,
        channelData: { taskforce: { error: true } },
      };
      return {
        ctx: { ...nextCtx, inProgressAssistantActivityId: null },
        activities: [activity],
        signals: [{ kind: "stream_error", message }],
        assistantBuffer: "",
      };
    }

    default:
      // Unrecognised event types are silently ignored — the SSE schema
      // may grow new event types we don't yet model.
      return { ctx, activities: [], signals: [], assistantBuffer };
  }
}
