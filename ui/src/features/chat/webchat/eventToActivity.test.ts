/**
 * @vitest-environment node
 */
import { describe, expect, it } from "vitest";

import { ATTACHMENT_TOOL_CALL, createMappingContext, eventToActivity } from "./eventToActivity";
import type { MessageActivity, TaskforceEvent } from "./types";

function freshState(conversationId = "conv-1") {
  return { ctx: createMappingContext(conversationId), assistantBuffer: "" };
}

describe("eventToActivity", () => {
  it("started → session_started signal, no activities", () => {
    const state = freshState();
    const result = eventToActivity(
      { event_type: "started", details: { session_id: "s-42" } },
      state,
    );

    expect(result.activities).toEqual([]);
    expect(result.signals).toEqual([{ kind: "session_started", sessionId: "s-42" }]);
  });

  it("llm_token first → new in-progress assistant message", () => {
    const state = freshState();
    const result = eventToActivity(
      { event_type: "llm_token", details: { token: "Hello" } },
      state,
    );

    expect(result.activities).toHaveLength(1);
    const msg = result.activities[0] as MessageActivity;
    expect(msg.text).toBe("Hello");
    expect(msg.channelData).toEqual({ taskforce: { inProgress: true } });
    expect(result.assistantBuffer).toBe("Hello");
    expect(result.ctx.inProgressAssistantActivityId).toBe(msg.id);
  });

  it("llm_token second → replaces the same activity id with growing text", () => {
    const state = freshState();
    const first = eventToActivity(
      { event_type: "llm_token", details: { token: "Hello" } },
      state,
    );
    const second = eventToActivity(
      { event_type: "llm_token", details: { token: " world" } },
      { ctx: first.ctx, assistantBuffer: first.assistantBuffer },
    );

    expect(second.activities).toHaveLength(1);
    const msg = second.activities[0] as MessageActivity;
    expect(msg.id).toBe(first.activities[0].id);
    expect(msg.text).toBe("Hello world");
  });

  it("tool_call → tool-call-attachment activity, separate from assistant message", () => {
    const state = freshState();
    const result = eventToActivity(
      {
        event_type: "tool_call",
        details: { tool_call_id: "t-1", name: "python", args: { code: "print(1)" } },
      },
      state,
    );

    expect(result.activities).toHaveLength(1);
    const msg = result.activities[0] as MessageActivity;
    expect(msg.attachments).toHaveLength(1);
    expect(msg.attachments?.[0].contentType).toBe(ATTACHMENT_TOOL_CALL);
    const content = msg.attachments?.[0].content as { name: string; pending: boolean };
    expect(content.name).toBe("python");
    expect(content.pending).toBe(true);
  });

  it("tool_result → paired result attachment (pending: false)", () => {
    const state = freshState();
    const result = eventToActivity(
      {
        event_type: "tool_result",
        details: { tool_call_id: "t-1", result: { output: 1 } },
      },
      state,
    );
    const msg = result.activities[0] as MessageActivity;
    const content = msg.attachments?.[0].content as { pending: boolean; result: unknown };
    expect(content.pending).toBe(false);
    expect(content.result).toEqual({ output: 1 });
  });

  it("final_answer → finalises in-progress activity in place", () => {
    const state = freshState();
    const first = eventToActivity(
      { event_type: "llm_token", details: { token: "Hi" } },
      state,
    );
    const final = eventToActivity(
      { event_type: "final_answer", message: "Hi there!" },
      { ctx: first.ctx, assistantBuffer: first.assistantBuffer },
    );

    expect(final.activities).toHaveLength(1);
    const msg = final.activities[0] as MessageActivity;
    expect(msg.id).toBe(first.activities[0].id); // same id — replacement
    expect(msg.text).toBe("Hi there!");
    expect(msg.channelData).toBeUndefined(); // no longer in progress
    expect(final.ctx.inProgressAssistantActivityId).toBeNull();
    expect(final.assistantBuffer).toBe("");
  });

  it("ask_user does NOT emit an activity; it emits an overlay signal", () => {
    const state = freshState();
    const result = eventToActivity(
      {
        event_type: "ask_user",
        message: "What date?",
        details: { missing: ["start_date"], channel: "telegram", recipient_id: "@u" },
      },
      state,
    );

    expect(result.activities).toEqual([]);
    expect(result.signals).toEqual([
      {
        kind: "ask_user",
        question: "What date?",
        missing: ["start_date"],
        channel: "telegram",
        recipientId: "@u",
      },
    ]);
  });

  it("plan_updated emits an overlay signal, no activity", () => {
    const state = freshState();
    const result = eventToActivity(
      {
        event_type: "plan_updated",
        details: { steps: [{ description: "Step 1", done: false }] },
      },
      state,
    );
    expect(result.activities).toEqual([]);
    expect(result.signals).toEqual([
      { kind: "plan_updated", steps: [{ description: "Step 1", done: false }] },
    ]);
  });

  it("complete → emits stream_completed signal; if buffer was non-empty, finalises in place", () => {
    const state = freshState();
    const first = eventToActivity(
      { event_type: "llm_token", details: { token: "Done." } },
      state,
    );
    const complete = eventToActivity(
      { event_type: "complete" },
      { ctx: first.ctx, assistantBuffer: first.assistantBuffer },
    );

    expect(complete.signals).toEqual([{ kind: "stream_completed" }]);
    expect(complete.activities).toHaveLength(1);
    expect(complete.ctx.inProgressAssistantActivityId).toBeNull();
  });

  it("error → destructive bot message + stream_error signal", () => {
    const state = freshState();
    const result = eventToActivity(
      { event_type: "error", message: "LLM provider down" },
      state,
    );
    expect(result.signals).toEqual([{ kind: "stream_error", message: "LLM provider down" }]);
    const msg = result.activities[0] as MessageActivity;
    expect(msg.text).toBe("LLM provider down");
    expect(msg.channelData).toEqual({ taskforce: { error: true } });
  });

  it("unknown event type is silently ignored", () => {
    const state = freshState();
    const result = eventToActivity(
      { event_type: "future_event_we_dont_know" } as TaskforceEvent,
      state,
    );
    expect(result.activities).toEqual([]);
    expect(result.signals).toEqual([]);
    expect(result.ctx).toEqual(state.ctx);
  });
});
