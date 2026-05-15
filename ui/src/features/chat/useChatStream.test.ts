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
import { useChatStream } from "./useChatStream";

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
