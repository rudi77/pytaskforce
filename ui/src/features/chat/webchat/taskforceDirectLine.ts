import {
  createMappingContext,
  eventToActivity,
  type MappingResult,
} from "./eventToActivity";
import type { Activity, AdapterSignal, TaskforceEvent } from "./types";

/**
 * Minimal Observable-shaped subject — enough to satisfy WebChat's
 * `directLine` interface contract without dragging in RxJS just for
 * this. WebChat subscribes via `.subscribe(observer)` and only relies
 * on a small subset of the Observable interface.
 */
class Subject<T> {
  private subscribers = new Set<(value: T) => void>();
  /** Last value, replayed to late subscribers (Behaviour-style). */
  private lastValue: T | undefined;
  private hasValue = false;

  next(value: T): void {
    this.lastValue = value;
    this.hasValue = true;
    for (const fn of this.subscribers) {
      try {
        fn(value);
      } catch {
        // Subscribers throwing must not kill the whole stream.
      }
    }
  }

  /** WebChat passes `{ next }` objects, not bare functions. */
  subscribe(observer: ((value: T) => void) | { next: (value: T) => void }): {
    unsubscribe: () => void;
  } {
    const fn = typeof observer === "function" ? observer : observer.next.bind(observer);
    if (this.hasValue && this.lastValue !== undefined) {
      // Replay so late subscribers see the latest connectionStatus.
      fn(this.lastValue);
    }
    this.subscribers.add(fn);
    return { unsubscribe: () => this.subscribers.delete(fn) };
  }
}

/**
 * Connection-status enum as defined by DirectLine. We only ever emit
 * `Connecting` (1) → `Online` (2), never the failure states (3, 4, 5).
 */
export const enum ConnectionStatus {
  Uninitialised = 0,
  Connecting = 1,
  Online = 2,
}

/**
 * In-memory DirectLine adapter that bridges Taskforce SSE events into
 * a stream of WebChat-compatible Activities + a sidecar signal stream.
 *
 * Usage shape:
 *
 *   const adapter = new TaskforceDirectLine("conv-1");
 *   adapter.activity$.subscribe((activity) => …);
 *   adapter.signals$.subscribe((signal) => {
 *     if (signal.kind === "ask_user") setAskUser(signal);
 *   });
 *
 *   // Wire the SSE source:
 *   for await (const event of sseStream) {
 *     adapter.handleEvent(event);
 *   }
 *
 *   // Pass adapter to WebChat:
 *   <ReactWebChat directLine={adapter} … />
 *
 * The user-message side (postActivity) is intentionally NOT wired up
 * here — the integration commit in ChatPage will plug `postActivity`
 * into the existing send-mission flow rather than have WebChat own
 * that path.
 */
export class TaskforceDirectLine {
  public readonly activity$ = new Subject<Activity>();
  public readonly signals$ = new Subject<AdapterSignal>();
  public readonly connectionStatus$ = new Subject<ConnectionStatus>();

  private mapping: { ctx: ReturnType<typeof createMappingContext>; assistantBuffer: string };

  constructor(conversationId: string) {
    this.mapping = {
      ctx: createMappingContext(conversationId),
      assistantBuffer: "",
    };
    this.connectionStatus$.next(ConnectionStatus.Online);
  }

  /**
   * Feed a single Taskforce SSE event into the adapter. Updates the
   * internal mapping state, then fans out activities + signals to
   * subscribers.
   */
  handleEvent(event: TaskforceEvent): MappingResult {
    const result = eventToActivity(event, this.mapping);
    this.mapping = { ctx: result.ctx, assistantBuffer: result.assistantBuffer };
    for (const activity of result.activities) {
      this.activity$.next(activity);
    }
    for (const signal of result.signals) {
      this.signals$.next(signal);
    }
    return result;
  }

  /**
   * Inject a user message directly (used when the host's send-mission
   * flow has confirmed the message hit the server). WebChat would
   * normally echo the user's own message via `postActivity`; we let
   * the host control timing so the activity appears only after the
   * server accepts it.
   */
  echoUserMessage(text: string): void {
    const id = `user-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    this.activity$.next({
      id,
      type: "message",
      timestamp: new Date().toISOString(),
      from: { id: "user", role: "user" },
      conversation: { id: this.mapping.ctx.conversationId },
      text,
    });
  }

  /**
   * Stub `postActivity` to satisfy DirectLine's interface — the actual
   * send-mission flow lives in ChatPage and bypasses this method. We
   * return a synthetic activity-id immediately so WebChat doesn't
   * error out if any internal callback tries to invoke it.
   */
  postActivity(): Subject<string> {
    const subject = new Subject<string>();
    subject.next(`postActivity-noop-${Date.now()}`);
    return subject;
  }

  /** Tear down — flushes pending state so future events are dropped. */
  end(): void {
    this.mapping = {
      ctx: createMappingContext(this.mapping.ctx.conversationId),
      assistantBuffer: "",
    };
  }
}
