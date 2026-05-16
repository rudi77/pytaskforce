---
feature: conversations
status: shipped
since: 2026-03-18
last_verified: 2026-05-16
owner: rudi77
adr: ADR-016
---

# Conversation Persistence — Persistent Dialogue Units

A conversation is a long-lived, file-backed dialogue between the user and the
agent that survives process restart. Each message the user sends is appended
to the conversation's history and the agent's reply is appended back. Users
can fork a conversation to replay it under a different profile, archive it
when finished, compact it to free context window, or hard-delete it. The
streaming endpoint pushes agent progress (tokens, tool calls, final answer)
to clients via Server-Sent Events.

## Capabilities (what the user can do)

- create a new conversation on a given channel (`rest`, `cli`, `telegram`, ...)
- list active conversations, newest activity first
- list archived conversations (with optional limit)
- get the full message history (or the most recent N messages) for a conversation
- append a message and receive the agent's reply in one round-trip
- stream the agent's reply token-by-token via SSE
- attach previously-uploaded files (`POST /api/v1/files`) to a message
- fork a conversation from message index N into a fresh conversation
- compact a conversation by summarizing earlier turns into a single system message
- archive a conversation (optionally with a user-supplied summary)
- hard-delete a conversation (irreversible — removes index entry and message log)
- bind a new conversation to a project so the agent's working directory becomes the project path (see related_spec: cowork.md)

## Invariants (what must always be true)

- Creating a new conversation for a channel/sender pair archives any previously active conversation for that same channel/sender — there is at most one active conversation per (channel, sender) at any time.
- `get_or_create` is idempotent for a given (channel, sender): repeated calls return the same id until the conversation is archived or deleted.
- Auto-archival fires on `get_or_create` for any active conversation idle beyond the inactivity threshold (default 24 h); stale conversations transition to `archived` before a new id is returned.
- `archive` is reversible by inspection (the data is still there) but the conversation no longer appears in the active list. `delete` is irreversible — both index entry and message log are purged.
- `delete` returns 404 when the id does not exist; the active-list scan is the source of truth for existence.
- Streaming reply persistence is best-effort but never silent: a cancelled or failed stream still appends an assistant message — with a `[partial — interrupted]` marker when tokens were received but no `complete` event arrived, or the structured error text when an `ERROR` event was the only output, or the literal `[no response]` placeholder when nothing at all came back.
- Append (both `POST /messages` and the SSE variant) persists the user message BEFORE the agent runs — a crash mid-execution does not lose user input.
- When a conversation has a `project_id`, the executor runs with `work_dir` set to that project's path; conversations without `project_id` fall back to the profile's configured `persistence.work_dir`.
- A referenced project that has been deleted does NOT block a chat reply — the executor falls back to the default work directory and the message is still answered.
- `compact` is refused (returns `status="skipped"`, `reason="below_threshold"`) when there are not enough messages to be worth summarizing (`len(messages) <= keep_last_n + 1`); it never produces a destructive write in that case.
- `compact` rejects an empty/whitespace summary from the summarizer rather than silently destroying history.
- `fork` strips volatile per-message fields (`message_id`, `timestamp`, `conversation_id`, `sequence`, ...) from the copied payloads so the new conversation's storage layout is internally consistent; tool-call linkage fields (`tool_calls`, `tool_call_id`, `name`) are preserved so the forked transcript still validates against provider APIs.

## API surface (the contract clients depend on)

- POST   /api/v1/conversations → 201 created
- POST   /api/v1/conversations → 400 when `project_id` references an unknown project
- GET    /api/v1/conversations → 200 (list of active, optional `project_id` query filter)
- GET    /api/v1/conversations/archived → 200 (optional `limit` query, default 20, max 100; optional `project_id` filter)
- GET    /api/v1/conversations/{id}/messages → 200 (optional `limit` query)
- POST   /api/v1/conversations/{id}/messages → 200 with agent reply
- POST   /api/v1/conversations/{id}/messages → 400 on empty message or unknown attachment file_id
- POST   /api/v1/conversations/{id}/messages/stream → 200 SSE stream (`message_persisted`, raw progress events, `assistant_persisted`, `error`)
- POST   /api/v1/conversations/{id}/messages/stream → 400 on empty message
- POST   /api/v1/conversations/{id}/archive → 204
- DELETE /api/v1/conversations/{id} → 204
- DELETE /api/v1/conversations/{id} → 404 if missing
- POST   /api/v1/conversations/{id}/fork → 201 with `{conversation_id, source_id, messages_copied}`
- POST   /api/v1/conversations/{id}/compact → 200 with `{status, summarized, kept, summary_preview}` or `{status="skipped", reason, messages}`
- POST   /api/v1/conversations/{id}/compact → 404 when the conversation does not exist

For project binding, see related_spec: cowork.md (`project_id` body field on
create; `project_id` query filter on list).

## Event stream contract (SSE — `/messages/stream`)

The SSE stream forwards the agent's `StreamEvent`s as raw `data:` lines
(JSON-serialised `ProgressUpdate`) and frames the boundaries with named events.

- `message_persisted` — fires once before the agent runs; payload: `{conversation_id}`
- raw `data: {...}` lines — every executor `ProgressUpdate` (LLM tokens, tool calls, plan updates, final answer)
- `: ping` — SSE comment emitted every `TASKFORCE_SSE_PING_INTERVAL` seconds (default 10 s; floor 0.1 s) to keep reverse-proxy connections warm
- `assistant_persisted` — final event; payload: `{conversation_id, completed: bool, content}` — fires from the `finally` block, so cancelled streams still emit it
- `error` — replaces `assistant_persisted` when the producer raises; payload: `{error, error_type}`

## Configuration surface

- `TASKFORCE_SSE_PING_INTERVAL` — float seconds between SSE keepalive pings (default 10.0, min 0.1)
- `TASKFORCE_WORK_DIR` — base directory under which `conversations/{id}/messages.json` is stored when no project is bound (default `.taskforce`)
- `ConversationManager(inactivity_threshold_hours=...)` — auto-archive threshold (default 24 h); set at manager construction in the infrastructure builder

## Tests (must exist and pass)

- spec("conversations.create_archives_previous_active")
- spec("conversations.get_or_create_idempotent_per_channel_sender")
- spec("conversations.auto_archive_stale_on_get_or_create")
- spec("conversations.append_persists_user_message_before_agent_runs")
- spec("conversations.stream_persists_partial_on_cancel")
- spec("conversations.stream_persists_error_message_when_no_tokens")
- spec("conversations.delete_returns_404_when_missing")
- spec("conversations.fork_copies_messages_and_strips_volatile_fields")
- spec("conversations.fork_preserves_tool_call_linkage")
- spec("conversations.compact_below_threshold_is_noop")
- spec("conversations.compact_rejects_empty_summary")
- spec("conversations.compact_returns_404_for_unknown_id")
- spec("conversations.project_bound_conversation_routes_workdir_to_project_path")

## Known gaps

- **No ownership or tenant-scoping on any conversation route.** Any authenticated caller can list, read, append to, fork, compact, archive, or delete any conversation by id. Tracked in #279.
- **`fork` is not atomic.** It creates the target conversation, then appends messages one at a time; a crash mid-loop leaves a partially-populated forked conversation in the index. Tracked in #314.
- **The fork copy loop is naive — large transcripts incur N round-trips to the store and no transactional guarantee that the source is unchanged during the copy.** Tracked in #336.
- **SSE `error` events leak the exception type and message** (`{error, error_type}`) — recon material for attackers probing the agent. Tracked in #287.
- **The SSE stream does not emit a typed `error` event for executor-level failures** mid-stream; downstream errors only surface as the producer exception in the `error` SSE frame, which clients have to parse out of band. Tracked in #288.
- **The streaming endpoint does not detect client disconnects** and keeps the executor running until completion even after the SSE consumer has gone away. Tracked in #310.
- **Archived conversations are not paginated by cursor**, only by `limit` (max 100). Long history lists clip silently.
- **No backend `@pytest.mark.spec` markers exist yet** — Tests section above asserts the target, not current state.

## Cross-references

- adr: ADR-016 (Persistent Agent Architecture — conversations replace sessions)
- related_spec: cowork.md (project binding via `project_id`)
- related_spec: gateway.md (channel-driven inbound messages reuse `ConversationManager.get_or_create`)
- related_spec: multi-tenant.md (tracking issue for tenant-scoping is #279)
- docs: docs/api.md (REST reference)
- commit: 7627942 (introduced 2026-03-18)
