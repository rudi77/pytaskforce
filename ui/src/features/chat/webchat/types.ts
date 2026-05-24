/**
 * DirectLine-shaped Activity types — minimal subset we actually emit
 * from the Taskforce adapter. botframework-webchat consumes the full
 * DirectLine schema; we only produce the fields that drive its visible
 * rendering (message body, attachments, typing indicators).
 *
 * Why our own typings rather than importing from
 * `botframework-directlinejs`? That package adds a 1MB+ runtime + RxJS
 * v6; we'd only use the type declarations. Re-declaring the narrow
 * subset here keeps the bundle lean and makes the contract explicit.
 */

export type ActivityType = "message" | "typing" | "event";

export interface ActivityFrom {
  id: string;
  role: "bot" | "user" | "channel";
  name?: string;
}

export interface BaseActivity {
  /** Unique id assigned by the adapter. */
  id: string;
  type: ActivityType;
  /** ISO timestamp; populated by the adapter so consumers can sort. */
  timestamp: string;
  from: ActivityFrom;
  /** ID of the conversation/session this activity belongs to. */
  conversation?: { id: string };
}

export interface MessageActivity extends BaseActivity {
  type: "message";
  text?: string;
  /** Custom attachments rendered by WebChat's `attachmentMiddleware`.
   *  The Taskforce widgets ride on this slot (contentType =
   *  `application/vnd.taskforce.tool-call+json` etc.). */
  attachments?: Attachment[];
  /** Channel-specific data — used to mark internal Taskforce statuses
   *  (e.g. `inProgress=true` for streaming assistant turns) so the
   *  adapter can keep replacing the same activity until it finalises. */
  channelData?: Record<string, unknown>;
}

export interface TypingActivity extends BaseActivity {
  type: "typing";
}

export interface EventActivity extends BaseActivity {
  type: "event";
  /** Event name, e.g. `taskforce/plan_updated`. */
  name: string;
  value?: unknown;
}

export type Activity = MessageActivity | TypingActivity | EventActivity;

export interface Attachment {
  contentType: string;
  content: unknown;
  name?: string;
}

/**
 * Sub-set of Taskforce SSE events we adapt to WebChat. Mirrors the
 * shape produced by `useChatStream` so the adapter doesn't need its
 * own decoding pass.
 */
export type TaskforceEvent =
  | { event_type: "started"; details?: { session_id?: string } | null }
  | { event_type: "llm_token"; message?: string; details?: { token?: string } | null }
  | {
      event_type: "tool_call";
      details?: {
        tool_call_id?: string;
        name?: string;
        args?: unknown;
        agent_path?: string[] | null;
      } | null;
    }
  | {
      event_type: "tool_result";
      details?: {
        tool_call_id?: string;
        result?: unknown;
        error?: string | null;
      } | null;
    }
  | { event_type: "final_answer"; message?: string }
  | {
      event_type: "plan_updated";
      details?: { steps?: Array<{ description: string; done: boolean }> } | null;
    }
  | {
      event_type: "ask_user";
      message?: string;
      details?: {
        missing?: string[];
        channel?: string | null;
        recipient_id?: string | null;
      } | null;
    }
  | { event_type: "complete"; message?: string }
  | { event_type: "error"; message?: string }
  | { event_type: string; message?: string; details?: Record<string, unknown> | null };

/** Side-channel signals the adapter exposes alongside the Activity stream. */
export type AdapterSignal =
  | {
      kind: "ask_user";
      question: string;
      missing: string[];
      channel: string | null;
      recipientId: string | null;
    }
  | { kind: "plan_updated"; steps: Array<{ description: string; done: boolean }> }
  | { kind: "session_started"; sessionId: string }
  | { kind: "stream_completed" }
  | { kind: "stream_error"; message: string };
