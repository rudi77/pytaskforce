---
feature: context-manager-ctxman
status: shipped
since: 2026-06-12
last_verified: 2026-06-12
owner: rudi77
---

# Context Manager — ctxman Backend

An alternative context-manager backend that delegates context bookkeeping to
the external ctxman service (REST, stateful): server-side token accounting,
compaction, eviction, externalization of large content, and frames for
sub-agent isolation. Operators switch between the in-process backend and
ctxman with a single profile key; the agent loop, CLI inspection, and resume
semantics behave identically either way. The agent still calls its own LLM —
ctxman only manages what goes into the context window.

## Capabilities (what the operator/profile-author can do)

- switch the context backend per profile (`context_management.backend:
  local | ctxman`) without changing agent code, tools, or prompts
- choose the outage behavior: `degrade` keeps the mission running on the
  locally cached context when ctxman is unreachable, `fail` aborts loudly
- let the LLM retrieve externalized content on demand: the agent gains an
  `expand_context_ref` tool that resolves summarized/elided segments, and
  evicted content degrades to its summary instead of an error
- run sequential sub-agents inside a frame of the parent's ctxman session,
  so their working context is promoted and evicted on return instead of
  accumulating; parallel sub-agents get isolated sessions automatically
- inspect server-side state (session id, watermark, server token count) in
  the `/context` snapshot alongside the usual sections
- observe a session's lifecycle through ctxman's event feed (pull with an
  `after_seq` cursor, or SSE stream) for dashboards and debugging
- archive the session on agent shutdown so ctxman runs terminal promotion
  (durable facts are extracted before the session closes)

## Invariants (what must always be true)

- The messages list keeps the same object identity across initialize,
  append, and remote synchronization — every external handle sees the
  rendered context after `prepare_for_llm()` returns.
- The system prompt at `messages[0]` is always the locally built dynamic
  prompt; the server's static prompt never replaces it in the served view.
- Synchronous context mutations never perform network I/O; all remote
  traffic happens at the prepare-for-LLM synchronization point.
- Buffered messages are flushed as one batch per synchronization, and a
  failed flush is replayed with the same idempotency key and the same
  payload, so retries can never duplicate or reorder segments.
- The server's static region is replaced only when the base system prompt
  actually changes; per-turn dynamic rebuilds never touch it (prefix
  caching stays intact).
- Local compression and preflight truncation are disabled under this
  backend — budget enforcement is the server's job, and a hard/emergency
  watermark triggers a server-side GC rather than local mutation.
- With `on_unavailable: degrade`, a ctxman outage never aborts the mission:
  the locally cached message list is a complete, valid history and pending
  segments are delivered on a later turn. With `fail`, the error propagates.
- A batch rejected for open tool-call units is repaired with synthetic
  cancellation results and retried, never silently dropped.
- Restoring a paused execution attaches to a fresh ctxman session seeded
  with the full restored history.
- A new turn in an existing conversation reattaches to that conversation's
  ctxman session — its id and flush cursor are persisted in the agent's
  per-conversation state (session id == conversation id) — instead of
  creating a new session each turn. On reattach only the current user turn
  is staged (prior turns already live server-side) and the saved flush
  sequence is continued, so per-turn append idempotency keys never collide.
  An expired/GC'd session (ctxman's idempotency retention) falls back to a
  fresh session with the full history re-staged.
- Frames are strictly sequential: a sub-agent frame is pushed only after
  the parent's pending messages are flushed, is popped even when the
  sub-agent fails, and concurrent sub-agents never share a session.
- Closing the owning agent archives the session best-effort; an archive or
  client-close failure never breaks agent shutdown.

## Configuration surface (the profile keys operators rely on)

All keys live under the profile-root `context_management:` block.

- `context_management.backend: str` (default `local`) — `local | ctxman`;
  any other value fails agent construction
- `context_management.ctxman.base_url: str` (default `http://localhost:5291`)
- `context_management.ctxman.provider: str` (default `openai`) — render
  format, `openai | anthropic`
- `context_management.ctxman.auth_mode: str` (default `none`) — `none |
  api_key`; with `api_key` the key is sent as `X-Api-Key`
- `context_management.ctxman.api_key: str | null` — overridden by
  `TASKFORCE_CTXMAN_API_KEY` when set
- `context_management.ctxman.tenant_id: str | null` — sent as `X-Tenant-Id`
- `context_management.ctxman.timeout_seconds: int` (default `30`)
- `context_management.ctxman.turn_advance: bool` (default `true`)
- `context_management.ctxman.on_unavailable: str` (default `degrade`) —
  `degrade | fail`
- `context_management.ctxman.gc_on_hard_watermark: bool` (default `true`)
- `context_management.ctxman.archive_on_close: bool` (default `true`)
- `context_management.ctxman.frames.enabled: bool` (default `true`)

## Extension points

- `set_context_manager_factory_override` in
  `application/infrastructure_overrides.py` — replaces the backend
  selection wholesale; receives the merged profile config and returns a
  context-manager factory (or None for the local default). Resolved on
  every agent build.
- `ContextManagerProtocol` (`core.interfaces.context_manager`) — the seam
  this backend implements; any further backend must preserve the local
  context-manager invariants plus the identity/overlay invariants above.

## Tests (must exist and pass)

- spec("context-manager-ctxman.messages_list_identity_stable")
- spec("context-manager-ctxman.system_prompt_overlaid_locally")
- spec("context-manager-ctxman.prepare_before_initialize_is_noop")
- spec("context-manager-ctxman.lazy_session_with_static_region")
- spec("context-manager-ctxman.outbox_flushed_as_single_batch")
- spec("context-manager-ctxman.failed_flush_replays_same_key")
- spec("context-manager-ctxman.restore_creates_fresh_session")
- spec("context-manager-ctxman.fresh_session_persists_record_into_state")
- spec("context-manager-ctxman.resume_attaches_without_recreating_session")
- spec("context-manager-ctxman.resume_stages_only_the_new_user_turn")
- spec("context-manager-ctxman.gone_session_recreated_with_full_history")
- spec("context-manager-ctxman.compress_and_preflight_are_noops")
- spec("context-manager-ctxman.budget_413_triggers_gc_and_retry")
- spec("context-manager-ctxman.degrade_keeps_local_context")
- spec("context-manager-ctxman.fail_mode_propagates_outage")
- spec("context-manager-ctxman.open_units_repaired_with_synthetic_results")
- spec("context-manager-ctxman.static_put_only_on_base_prompt_change")
- spec("context-manager-ctxman.expand_ref_410_returns_summary")
- spec("context-manager-ctxman.push_frame_flushes_outbox_first")
- spec("context-manager-ctxman.frame_bound_adapter_shares_session")
- spec("context-manager-ctxman.sequential_sub_agent_runs_in_frame")
- spec("context-manager-ctxman.degraded_push_falls_back_to_own_session")
- spec("context-manager-ctxman.session_archived_on_close")
- spec("context-manager-ctxman.archive_failure_does_not_break_shutdown")

## Known gaps

- **Server token accounting misses the dynamic prompt overlay.** The
  per-turn dynamic system-prompt suffix is invisible to ctxman; a fixed
  4k-token headroom is reserved in the session budget as compensation, so
  the effective budget is approximate, not exact.
- **Frame pop and archive require a compaction model on the ctxman side.**
  Terminal promotion calls ctxman's compaction LLM; a ctxman instance
  without compaction credentials answers 503 `promotion_failed` — frames
  then degrade to isolated sessions and archive is skipped with a warning.
- **Only paused-execution restore starts a fresh ctxman session.** Normal
  turn-to-turn continuation reattaches to the conversation's session (see the
  reattach invariant). The ask_user/HITL `restore` path still seeds a fresh
  session with the full restored history; that session is orphaned until
  ctxman retention sweeps it.
- **Tool definitions sent to the LLM bypass the render result.** The agent
  uses its locally built tool list; the server's rendered tool section is
  ignored, so a server-side tool diff is not reflected mid-mission.

## Cross-references

- related_spec: context-manager.md (the local backend and the shared
  protocol contract)
- related_spec: react-loop.md (the loop's message-list identity assumption
  this backend must honor)
- docs: ctxman spec — `docs/ctxman-spec.md` in the ctxman repository
  (sessions, segments, render, frames, GC, events)
