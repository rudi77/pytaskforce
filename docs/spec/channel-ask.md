---
feature: channel-ask
status: shipped
since: 2026-03-15
last_verified: 2026-05-16
owner: rudi77
---

# ChannelAskRouter — Per-Channel Question/Answer Routing

When the agent decides it needs more information from a human, it calls the
`ask_user` tool. If the question carries a `channel` + `recipient_id` (e.g.
`telegram`, `teams`) the ChannelAskRouter delivers it via the Communication
Gateway to the paired user on that channel, pauses the agent, and resumes
the execution once the user replies. Plain (non-channel) `ask_user` calls
still go to the originating session (web/REST/CLI). The pairing flow itself
(`/link <code>`) is owned by the gateway — this spec is only about the
question/answer round-trip that runs on top of it.

## Capabilities (what the user can do)

- ask a question from any agent on any channel via `ask_user(channel="…", recipient_id="…", question="…")`
- omit `channel`/`recipient_id` and have the question delivered to the originating session (web chat, REST caller, CLI)
- have the question inherit `channel` + `recipient_id` automatically when the agent omits them but the conversation came in over a channel
- answer on the same channel the question arrived on and have the agent resume from exactly that point
- answer through the web/REST chat path even when the question was sent over a channel (web path uses the standard pause/resume; channel path uses the polling router)
- pair a channel sender to a logical user via `/link <code>` (owned by gateway) so future channel-targeted asks can address them

## Invariants (what must always be true)

- An `ask_user` event with no `channel` AND no `recipient_id` is always treated as a plain pause — it goes through the normal session pause/resume, not the channel router.
- An `ask_user` event with both `channel` and `recipient_id` is always routed through the gateway and never delivered to the originating session.
- An `ask_user` event with only `channel` (no `recipient_id`) is completed from the source conversation's `recipient_id` before routing — the router never sends a question without a recipient.
- A channel question that the gateway fails to send returns no response (router returns `None`); the agent surfaces the failure rather than waiting indefinitely.
- The pending entry for a channel question is cleared once a response is received, so a follow-up message from the same sender starts a fresh inbound flow.
- The pending entry for a channel question is also cleared on poll timeout, so a later unrelated message from the same sender is not silently consumed as the answer to a stale question.
- A response is matched to a pending question by `(channel, sender_id)`; a sender with no pending question goes through the normal inbound flow.
- A pending question is single-resolve: once an answer is stored, a second inbound message from the same sender does not overwrite it.
- A pending question survives process restart (file-backed by default), so an agent that was waiting before restart still resumes correctly afterwards.
- The `/link` pairing intercept runs before the recipient resolver (see gateway spec), so an unpaired sender can complete pairing without a known logical user.

## Configuration surface

- ChannelAskRouter currently hardcodes `poll_interval = 2.0s` and `max_wait = 600s` (10 minutes) for channel-targeted asks. Neither is operator-configurable today — see Known gaps.
- Plain (non-channel) `ask_user` uses the standard pause/resume from the ReAct loop and is bounded by `agent.max_steps`, not by a wall-clock timeout.

## Event stream contract

The router does not introduce new event types. It consumes / completes
existing `ASK_USER` events emitted by the ReAct loop (see `react-loop.md`):

- `ASK_USER` (plain) — `data` has `question` only; handled by the originating session.
- `ASK_USER` (channel-targeted) — `data` carries `channel` + `recipient_id` + `question`; consumed by the router, which sends and polls. The downstream `ProgressUpdate` is annotated with `channel_routed: true` (question sent) or `channel_response_received: true` (answer received).

## Extension points

- `PendingChannelQuestionStoreProtocol` in `taskforce.core.interfaces.channel_ask` — host applications can replace the default file-backed store (e.g. a Postgres-backed store for multi-tenant deployments). The framework default is `FilePendingChannelQuestionStore` writing under `<work_dir>/pending_channel_questions/`.
- The router itself depends only on the gateway's `send_channel_question` / `poll_channel_response` / `clear_channel_question` methods; alternative gateway implementations that honour those three methods are drop-in.

## Tests (must exist and pass)

- spec("channel-ask.plain_ask_uses_session_pause")
- spec("channel-ask.channel_ask_routes_via_gateway")
- spec("channel-ask.missing_recipient_filled_from_source")
- spec("channel-ask.send_failure_returns_none")
- spec("channel-ask.response_clears_pending_entry")
- spec("channel-ask.timeout_clears_pending_entry")
- spec("channel-ask.response_matched_by_channel_and_sender_id")
- spec("channel-ask.pending_entry_single_resolve")
- spec("channel-ask.pending_entry_survives_restart")

## Known gaps

- **No inner timeout on `poll_channel_response`** — each poll iteration awaits the store call without its own deadline; a hung store call blocks the agent indefinitely despite the outer `max_wait` budget. Tracked in #338.
- **`PendingChannelStore` has no TTL** — entries that are never resolved and never time out (e.g. on a crash mid-poll) accumulate on disk. There is no background sweeper. Tracked in #348.
- **Race when the user answers on two channels in parallel** — if the same sender is paired on multiple channels and both reply simultaneously, the resolve order is non-deterministic and the loser's answer is dropped instead of queued. Tracked in #309.
- **`poll_interval` and `max_wait` are hardcoded** (2s / 600s) — operators cannot tune them per profile or per call. Long-form questions on Teams routinely need more than 10 minutes.
- **No backend `@pytest.mark.spec` markers exist yet** — Tests section above asserts the target, not current state. Spec-check will flag every marker as "asserted but missing test" on first run.

## Cross-references

- related_spec: gateway.md (owns `/link <code>` pairing, `send_channel_question`, `poll_channel_response`, `clear_channel_question`, and the recipient resolver)
- related_spec: react-loop.md (emits the `ASK_USER` event the router consumes; `paused` status semantics on pause)
- related_spec: conversations.md (source conversation provides the fallback `channel` + `recipient_id`)
- docs: CLAUDE.md → "Channel-based User Interaction" / `ChannelAskProtocol`
