/**
 * @vitest-environment jsdom
 *
 * Regression tests for ``useChatStream`` — specifically the server-side
 * Stop wiring added in the Cowork-parity Phase 1.
 *
 * The contract we're protecting:
 *
 *   1. The ``started`` SSE event carries ``details.session_id``; the hook
 *      captures it into ``state.sessionId`` AND into an internal ref so
 *      ``cancel()`` can use it even when called from a stale closure.
 *
 *   2. ``cancel()`` first POSTs to
 *      ``/api/v1/execute/{session_id}/cancel`` (cooperative interrupt)
 *      and then aborts the SSE fetch. Without the server call, aborting
 *      the fetch only stops the *client* from receiving events — the
 *      agent keeps burning tokens on the server.
 *
 *   3. If no ``started`` event has arrived yet (``session_id`` unknown),
 *      ``cancel()`` still aborts the SSE fetch.
 */
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiFetchMock = vi.fn();
const sseStreamMock = vi.fn();

vi.mock("@/api/client", () => ({
  apiFetch: (...args: unknown[]) => apiFetchMock(...args),
  sseStream: (...args: unknown[]) => sseStreamMock(...args),
}));

// Import AFTER the mock so the hook picks up the mocked module.
import {
  __resetChatStreamStore,
  parsePlanMarkdown,
  useChatStream,
} from "./useChatStream";

type Event = { event: string; data: string };

/** Build an async iterable backed by a deferred queue so the test can
 *  control when events arrive (and when the stream ends). */
function createControllableStream() {
  const queue: Event[] = [];
  const waiters: ((value: IteratorResult<Event>) => void)[] = [];
  let closed = false;

  function push(evt: Event) {
    if (waiters.length > 0) {
      waiters.shift()!({ value: evt, done: false });
    } else {
      queue.push(evt);
    }
  }
  function close() {
    closed = true;
    while (waiters.length > 0) {
      waiters.shift()!({ value: undefined as unknown as Event, done: true });
    }
  }
  const iterable: AsyncIterable<Event> = {
    [Symbol.asyncIterator]() {
      return {
        next() {
          if (queue.length > 0) {
            return Promise.resolve({ value: queue.shift()!, done: false });
          }
          if (closed) {
            return Promise.resolve({
              value: undefined as unknown as Event,
              done: true,
            });
          }
          return new Promise<IteratorResult<Event>>((resolve) =>
            waiters.push(resolve),
          );
        },
      };
    },
  };
  return { iterable, push, close };
}

describe("useChatStream — server-side cancellation (Cowork-parity Phase 1)", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    sseStreamMock.mockReset();
    __resetChatStreamStore();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("captures session_id from the started event into state.sessionId", async () => {
    const stream = createControllableStream();
    sseStreamMock.mockReturnValue(stream.iterable);

    const { result } = renderHook(() => useChatStream());

    // Fire-and-forget send; the SSE loop runs in the background.
    const sendPromise = result.current.send({
      conversationId: "conv-1",
      message: "hi",
      attachments: [],
    });

    stream.push({
      event: "message",
      data: JSON.stringify({
        event_type: "started",
        details: { session_id: "sess-abc-123" },
      }),
    });

    await waitFor(() => {
      expect(result.current.state.sessionId).toBe("sess-abc-123");
    });

    // Clean teardown so the test doesn't leak unfinished promises into the
    // next one.
    stream.close();
    await sendPromise;
  });

  it("cancel() POSTs to /api/v1/execute/{id}/cancel before aborting the fetch", async () => {
    const stream = createControllableStream();
    sseStreamMock.mockReturnValue(stream.iterable);
    apiFetchMock.mockResolvedValue({
      session_id: "sess-abc-123",
      status: "interrupt_requested",
    });

    const { result } = renderHook(() => useChatStream());

    const sendPromise = result.current.send({
      conversationId: "conv-1",
      message: "hi",
      attachments: [],
    });

    stream.push({
      event: "message",
      data: JSON.stringify({
        event_type: "started",
        details: { session_id: "sess-abc-123" },
      }),
    });

    await waitFor(() => {
      expect(result.current.state.sessionId).toBe("sess-abc-123");
    });

    await result.current.cancel();

    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = apiFetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/execute/sess-abc-123/cancel");
    expect((init as { method?: string }).method).toBe("POST");

    stream.close();
    await sendPromise;
  });

  it("cancel() still aborts the fetch when no session_id is known yet", async () => {
    const stream = createControllableStream();
    sseStreamMock.mockReturnValue(stream.iterable);

    const { result } = renderHook(() => useChatStream());

    const sendPromise = result.current.send({
      conversationId: "conv-1",
      message: "hi",
      attachments: [],
    });

    // No ``started`` event yet — cancel before the agent has even
    // identified itself.
    await result.current.cancel();

    expect(apiFetchMock).not.toHaveBeenCalled();
    // The controller was aborted; the SSE iterator's stream.close() drains
    // the loop and isStreaming flips back to false.
    stream.close();
    await sendPromise;
    await waitFor(() => expect(result.current.isStreaming).toBe(false));
  });

  it("captures ask_user events into state.pendingAskUser (chat-side)", async () => {
    const stream = createControllableStream();
    sseStreamMock.mockReturnValue(stream.iterable);

    const { result } = renderHook(() => useChatStream());

    const sendPromise = result.current.send({
      conversationId: "conv-1",
      message: "schedule a meeting",
      attachments: [],
    });

    stream.push({
      event: "message",
      data: JSON.stringify({
        event_type: "ask_user",
        details: {
          question: "Which day works for you?",
          missing: ["date"],
        },
      }),
    });

    await waitFor(() => {
      expect(result.current.state.pendingAskUser).not.toBeNull();
    });
    expect(result.current.state.pendingAskUser).toEqual({
      question: "Which day works for you?",
      missing: ["date"],
      channel: null,
      recipientId: null,
    });

    stream.close();
    await sendPromise;
  });

  it("captures channel routing fields when the question targets a channel", async () => {
    const stream = createControllableStream();
    sseStreamMock.mockReturnValue(stream.iterable);

    const { result } = renderHook(() => useChatStream());

    const sendPromise = result.current.send({
      conversationId: "conv-1",
      message: "ping the user",
      attachments: [],
    });

    stream.push({
      event: "message",
      data: JSON.stringify({
        event_type: "ask_user",
        details: {
          question: "Approve the wire transfer?",
          missing: [],
          channel: "telegram",
          recipient_id: "u-42",
        },
      }),
    });

    await waitFor(() => {
      expect(result.current.state.pendingAskUser?.channel).toBe("telegram");
    });
    expect(result.current.state.pendingAskUser?.recipientId).toBe("u-42");

    stream.close();
    await sendPromise;
  });

  it("clears pendingAskUser on the next send() (the answer is the next message)", async () => {
    const stream = createControllableStream();
    sseStreamMock.mockReturnValue(stream.iterable);

    const { result } = renderHook(() => useChatStream());

    const firstSend = result.current.send({
      conversationId: "conv-1",
      message: "kick off",
      attachments: [],
    });

    stream.push({
      event: "message",
      data: JSON.stringify({
        event_type: "ask_user",
        details: { question: "Confirm?", missing: [] },
      }),
    });
    await waitFor(() => {
      expect(result.current.state.pendingAskUser?.question).toBe("Confirm?");
    });
    stream.close();
    await firstSend;

    // Replace the stream mock for the resume call.
    const stream2 = createControllableStream();
    sseStreamMock.mockReturnValue(stream2.iterable);

    const secondSend = result.current.send({
      conversationId: "conv-1",
      message: "yes",
      attachments: [],
    });

    await waitFor(() => {
      expect(result.current.state.pendingAskUser).toBeNull();
    });

    stream2.close();
    await secondSend;
  });

  it("ignores ask_user events with no question and no missing fields", async () => {
    const stream = createControllableStream();
    sseStreamMock.mockReturnValue(stream.iterable);

    const { result } = renderHook(() => useChatStream());

    const sendPromise = result.current.send({
      conversationId: "conv-1",
      message: "hi",
      attachments: [],
    });

    // Defensive: a malformed event with empty payload shouldn't render a
    // blank prompt card to the user.
    stream.push({
      event: "message",
      data: JSON.stringify({
        event_type: "ask_user",
        details: { question: "", missing: [] },
      }),
    });

    // Give the loop a tick to process.
    stream.push({
      event: "message",
      data: JSON.stringify({
        event_type: "llm_token",
        details: { token: "ok" },
      }),
    });

    await waitFor(() => {
      expect(result.current.state.text).toBe("ok");
    });
    expect(result.current.state.pendingAskUser).toBeNull();

    stream.close();
    await sendPromise;
  });

  it("clears planSteps when plan_updated reports an empty plan", async () => {
    const stream = createControllableStream();
    sseStreamMock.mockReturnValue(stream.iterable);

    const { result } = renderHook(() => useChatStream());

    const sendPromise = result.current.send({
      conversationId: "conv-1",
      message: "go",
      attachments: [],
    });

    // Populate the plan first…
    stream.push({
      event: "message",
      data: JSON.stringify({
        event_type: "plan_updated",
        details: { plan: "[ ] 1. Step one" },
      }),
    });
    await waitFor(() => {
      expect(result.current.state.planSteps).toHaveLength(1);
    });

    // …then have the agent abandon the plan. The panel must clear.
    stream.push({
      event: "message",
      data: JSON.stringify({
        event_type: "plan_updated",
        details: { plan: "No active plan." },
      }),
    });
    await waitFor(() => {
      expect(result.current.state.planSteps).toEqual([]);
    });

    stream.close();
    await sendPromise;
  });

  it("captures plan_updated events into state.planSteps (Cowork progress panel)", async () => {
    const stream = createControllableStream();
    sseStreamMock.mockReturnValue(stream.iterable);

    const { result } = renderHook(() => useChatStream());

    const sendPromise = result.current.send({
      conversationId: "conv-1",
      message: "process the mail",
      attachments: [],
    });

    stream.push({
      event: "message",
      data: JSON.stringify({
        event_type: "plan_updated",
        details: {
          action: "create_plan",
          plan: "[x] 1. Read mail\n[ ] 2. Classify\n[ ] 3. Draft reply",
        },
      }),
    });

    await waitFor(() => {
      expect(result.current.state.planSteps).toHaveLength(3);
    });
    expect(result.current.state.planSteps[0]).toEqual({
      description: "Read mail",
      done: true,
    });
    expect(result.current.state.planSteps[2]).toEqual({
      description: "Draft reply",
      done: false,
    });

    stream.close();
    await sendPromise;
  });

  it("parsePlanMarkdown handles the documented PlannerTool format", () => {
    expect(parsePlanMarkdown("No active plan.")).toEqual([]);
    expect(parsePlanMarkdown("")).toEqual([]);
    expect(parsePlanMarkdown("[x] 1. Done\n[ ] 2. Pending")).toEqual([
      { description: "Done", done: true },
      { description: "Pending", done: false },
    ]);
    // Tolerant to upper-case X + missing numbering.
    expect(parsePlanMarkdown("[X] do the thing")).toEqual([
      { description: "do the thing", done: true },
    ]);
    // Free lines are kept as pending entries (better than silent drop).
    expect(parsePlanMarkdown("just text")).toEqual([
      { description: "just text", done: false },
    ]);
  });

  it("cancel() swallows a 404 from the cancel endpoint (stale session)", async () => {
    const stream = createControllableStream();
    sseStreamMock.mockReturnValue(stream.iterable);
    apiFetchMock.mockRejectedValue(new Error("404 Not Found"));

    const { result } = renderHook(() => useChatStream());

    const sendPromise = result.current.send({
      conversationId: "conv-1",
      message: "hi",
      attachments: [],
    });

    stream.push({
      event: "message",
      data: JSON.stringify({
        event_type: "started",
        details: { session_id: "sess-stale" },
      }),
    });

    await waitFor(() => {
      expect(result.current.state.sessionId).toBe("sess-stale");
    });

    // Must not throw even when the server says "no such session".
    await expect(result.current.cancel()).resolves.toBeUndefined();

    stream.close();
    await sendPromise;
  });
});

describe("useChatStream — state survives unmount (#274)", () => {
  beforeEach(() => {
    apiFetchMock.mockReset();
    sseStreamMock.mockReset();
    __resetChatStreamStore();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("a remounted hook observes the events the previous mount received", async () => {
    // Reproduces "navigate away mid-run, come back later": the SSE loop
    // is driven by a module-level store, so events that arrive between
    // unmount and remount must still be visible to the second mount.
    const stream = createControllableStream();
    sseStreamMock.mockReturnValue(stream.iterable);

    // Mount #1: start the run.
    const first = renderHook(() => useChatStream("conv-X"));
    const sendPromise = first.result.current.send({
      conversationId: "conv-X",
      message: "do work",
      attachments: [],
    });

    stream.push({
      event: "message",
      data: JSON.stringify({
        event_type: "started",
        details: { session_id: "sess-X" },
      }),
    });
    await waitFor(() =>
      expect(first.result.current.state.sessionId).toBe("sess-X"),
    );

    // Simulate the user navigating away — the chat page unmounts.
    first.unmount();

    // Events keep coming while the page is gone. Without the store
    // refactor these would land in the dead hook's setState and be lost.
    stream.push({
      event: "message",
      data: JSON.stringify({
        event_type: "tool_call",
        details: {
          tool_call_id: "tc-1",
          tool: "file_read",
          arguments: { path: "src/foo.py" },
        },
      }),
    });
    stream.push({
      event: "message",
      data: JSON.stringify({
        event_type: "plan_updated",
        details: { plan: "[ ] 1. read file\n[ ] 2. write file" },
      }),
    });

    // Give the SSE iteration a tick to drain the queued events into the
    // store (the iterator microtasks need to run).
    await new Promise((r) => setTimeout(r, 0));

    // Mount #2: user comes back to the same conversation.
    const second = renderHook(() => useChatStream("conv-X"));

    // The just-mounted hook must see what the previous mount missed.
    await waitFor(() => {
      expect(second.result.current.state.sessionId).toBe("sess-X");
      expect(second.result.current.state.toolCalls).toHaveLength(1);
      expect(second.result.current.state.toolCalls[0].name).toBe("file_read");
      expect(second.result.current.state.planSteps).toHaveLength(2);
    });

    stream.close();
    await sendPromise;
  });

  it("scopes state per conversationId so chats don't leak into each other", async () => {
    const streamA = createControllableStream();
    sseStreamMock.mockReturnValueOnce(streamA.iterable);

    const hookA = renderHook(() => useChatStream("conv-A"));
    const sendA = hookA.result.current.send({
      conversationId: "conv-A",
      message: "hi",
      attachments: [],
    });
    streamA.push({
      event: "message",
      data: JSON.stringify({
        event_type: "started",
        details: { session_id: "sess-A" },
      }),
    });
    await waitFor(() =>
      expect(hookA.result.current.state.sessionId).toBe("sess-A"),
    );

    // Open the OTHER conversation in a separate hook — it must not see
    // conv-A's state spilling over.
    const hookB = renderHook(() => useChatStream("conv-B"));
    expect(hookB.result.current.state.sessionId).toBeNull();
    expect(hookB.result.current.state.toolCalls).toEqual([]);
    expect(hookB.result.current.isStreaming).toBe(false);

    streamA.close();
    await sendA;
  });
});
