# `src/features/chat/webchat/` — botframework-webchat adapter

Tracks issue [#440](https://github.com/rudi77/pytaskforce/issues/440).

This directory provides the **infrastructure** for rendering the Taskforce
chat via `botframework-webchat`. The actual wire-up of `<ReactWebChat>`
into `ChatPage` is a follow-up commit; what's here is the standalone
adapter layer plus exhaustive unit tests for the event-mapping logic.

## Files

| Path | Purpose |
|---|---|
| `types.ts` | Minimal DirectLine `Activity` typings + `TaskforceEvent` + `AdapterSignal` value objects. We re-declare the narrow subset locally rather than depending on `botframework-directlinejs` (1MB+ runtime, RxJS v6) just for types. |
| `eventToActivity.ts` | Pure-function mapper `TaskforceEvent → { activities, signals, ctx }`. Threaded `ctx` so streaming `llm_token` events grow the same in-progress assistant activity instead of producing one per token. |
| `eventToActivity.test.ts` | 11 unit tests covering every SSE branch (started / llm_token / tool_call / tool_result / final_answer / ask_user / plan_updated / complete / error / unknown). |
| `taskforceDirectLine.ts` | Thin class implementing the subset of DirectLine's interface WebChat actually subscribes to (`activity$`, `connectionStatus$`, `postActivity`) backed by a tiny home-rolled Subject. Adds a sidecar `signals$` for overlay-only payloads (ask_user, plan_updated). |

## Event → Activity mapping

| Taskforce event | WebChat output |
|---|---|
| `started` | No activity; `{ kind: "session_started", sessionId }` signal so ChatPage can capture the session id for cooperative cancel. |
| `llm_token` | Mints a `message` activity on the first token; subsequent tokens replace it (same `id`) with the growing text. `channelData.taskforce.inProgress = true` while streaming. |
| `tool_call` | Standalone `message` activity with a custom attachment (`application/vnd.taskforce.tool-call+json`, `pending: true`). Consumer wires `attachmentMiddleware` to render the existing Taskforce tool-call card. |
| `tool_result` | Paired `message` activity with the same attachment contentType (`pending: false`). The attachmentMiddleware may merge the two visually. |
| `final_answer` | Finalises the in-progress assistant activity in place (same `id`); clears `inProgress`. |
| `plan_updated` | No activity; `{ kind: "plan_updated", steps }` signal so the RightPanel updates without polluting the chat stream. |
| `ask_user` | **No activity** — emits `{ kind: "ask_user", … }` signal exclusively. The existing `AskUserCard` overlay consumes it. Putting `ask_user` in the WebChat stream would leave a stale "what date?" bubble hanging around after the user answers. |
| `complete` | Finalises the in-progress activity if any buffered text remains; emits `{ kind: "stream_completed" }`. |
| `error` | Destructive `message` activity + `{ kind: "stream_error", message }` signal. |
| (any other) | Silently ignored — the SSE schema may grow event types we don't yet model. |

## Why an adapter at all?

`botframework-webchat` was designed for the Microsoft Bot Framework
DirectLine REST + WebSocket protocol. The Taskforce backend speaks a
different streaming protocol (SSE with the event types listed above).
Rather than rewrite WebChat to consume SSE, we feed it a synthetic
`directLine` implementation that exposes the four things WebChat
actually reads (`activity$`, `connectionStatus$`, `postActivity()`,
`end()`) and translate at the boundary.

The reverse direction (user-message send) deliberately stays inside
ChatPage's existing send-mission flow rather than going through
`directLine.postActivity()` — this keeps cooperative cancel,
attachment uploads and mention handling on the path they're already
proven to work on. The adapter's `postActivity` is a no-op stub
for interface compliance.

## Sidecar signals

`signals$` exists because three event categories don't fit the
"add an activity to the chat scroll" mental model:

- **ask_user** is HITL — needs a focused affordance, not a bubble.
- **plan_updated** belongs in the right panel, not the conversation.
- **session_started** / **stream_completed** / **stream_error** are
  control-plane signals consumed by ChatPage to drive its stop-button,
  cancel logic and toast notifications.

Subscribers wire one observer to `activity$` (WebChat) and another
to `signals$` (overlay components) — clean separation, no filtering
ceremony at the consumer side.
