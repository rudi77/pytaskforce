---
feature: context-manager
status: shipped
since: 2026-04-13
last_verified: 2026-05-16
owner: rudi77
adr: ADR-025
---

# Context Manager

The single source of truth for everything the agent sends to the LLM in one
turn — the system prompt, the running message log, and the OpenAI-format tool
definitions. The ReAct loop drives, the ContextManager owns the bytes that
actually go on the wire. Before every model call it rebuilds the system prompt,
runs role-aware compression if the token budget is hot, and applies an
emergency preflight truncation so a single oversized turn cannot poison the
next request. It also exposes a structured snapshot for `/context` and `/tree`
inspection, and accepts post-execution snapshots from sub-agents so the parent
agent can show what its children worked on.

## Capabilities (what the operator/profile-author can do)

- bound the agent's input window with `context_management.max_input_tokens` and
  start compressing early with `context_management.compression_trigger` (or the
  legacy `context_management.summary_threshold` message count)
- cap individual oversized messages with `agent.tool_message_max_chars` and
  `agent.assistant_message_max_chars` to keep one bad tool result from
  dominating the budget
- inspect what the next LLM call will contain via the `/context` and `/tree`
  CLI commands (system prompt, every message, memory, skills, tools, sub-agent
  snapshots)
- resume a paused execution (`ask_user` answer arrived, conversation
  reactivated) by restoring the full message list verbatim
- let a sub-agent register its final context snapshot on the parent before it
  shuts down, so `/tree --sub-agents` shows what each child actually saw

## Invariants (what must always be true)

- The system prompt is always `messages[0]`; rebuilding the prompt mid-turn
  overwrites that slot in-place rather than appending a duplicate system turn.
- Compression and preflight mutate the existing message list in place — every
  external reference (the ReAct loop's local handle, the agent's
  `state["messages"]`) sees the same updated content after the call returns.
- A `role="tool"` message that survives compression always has a matching
  preceding `role="assistant"` message containing a `tool_calls` entry with
  the same `tool_call_id`; orphan tool messages are dropped before the next
  LLM request.
- Trimming the history to the last N messages never splits a tool-call pair:
  if the kept window starts inside a tool reply, the window is widened backward
  to include the assistant message that issued the call.
- Compression is triggered by either signal first: estimated tokens above
  `compression_trigger`, or message count above `summary_threshold`. Below
  both, the message list is returned unchanged (cheap no-op).
- Compression has a guaranteed terminal fallback: if the LLM summary call
  fails, the prompt is itself over budget, or any exception escapes, the
  deterministic fallback runs — keep the system prompt plus the last 10
  messages plus a one-line "[N earlier messages compressed]" marker.
- The preflight check runs *after* compression and only acts when the prompt
  is still over `max_input_tokens`; the in-budget path is a single token
  estimate and a return.
- `restore()` adopts the supplied message list as-is; if `messages[0]` is a
  system turn, its content becomes the new "last system prompt" returned by
  the `system_prompt` accessor.
- Sub-agent snapshots are scoped to one execution turn: `initialize()` clears
  the list, and at most `MAX_SUB_AGENT_SNAPSHOTS` (10) entries are kept per
  turn — additional registrations are dropped with a debug log.
- `prepare_for_llm()` called before `initialize()`/`restore()` is a logged
  warning and a no-op — it never raises and never silently mutates an empty
  context into a malformed prompt.
- The snapshot returned by `snapshot()` is a frozen dataclass tree: callers
  may read it freely, but mutating it does not affect the live context.

## Configuration surface (the profile keys operators rely on)

- `context_management.max_input_tokens: int` (default `100000`) — hard ceiling
  on estimated input tokens for one LLM call. Read by `factory.py` from the
  profile-root `context_management:` block and forwarded to the agent
  constructor.
- `context_management.compression_trigger: int` (default `40000`) — token
  threshold above which compression runs before the next LLM call
- `context_management.summary_threshold: int` (default `20`) — message-count
  threshold for the same compression decision (whichever trigger fires first
  wins)
- `agent.tool_message_max_chars: int` (default `1500`) — per-message hard cap
  for `role="tool"` content; set to `0` to disable
- `agent.assistant_message_max_chars: int` (default `4000`) — per-message hard
  cap for `role="assistant"` content; set to `0` to disable

## Extension points

- `TokenEstimatorProtocol` — operators can plug a different token counter
  (e.g. tiktoken-based) into `TokenBudgeter` for more accurate budgeting.
  Default is `HeuristicTokenEstimator` (chars/4).
- `ContextManagerProtocol` — the public protocol in
  `core.interfaces.context_manager` is the seam other components (the ReAct
  loop, orchestration tools, CLI inspection commands) depend on; an
  alternative implementation can be wired in instead of the default
  `ContextManager` so long as it preserves the invariants above.

## Tests (must exist and pass)

- spec("context-manager.system_prompt_always_at_index_zero")
- spec("context-manager.compression_mutates_in_place")
- spec("context-manager.orphan_tool_messages_dropped")
- spec("context-manager.tool_call_pairs_preserved_on_trim")
- spec("context-manager.deterministic_fallback_runs_when_llm_summary_fails")
- spec("context-manager.preflight_truncates_when_over_max_input_tokens")
- spec("context-manager.restore_recovers_full_message_list")
- spec("context-manager.sub_agent_snapshots_cleared_on_initialize")
- spec("context-manager.sub_agent_snapshots_capped_at_ten")
- spec("context-manager.prepare_for_llm_before_init_is_noop_warning")
- spec("context-manager.role_caps_truncate_with_marker")
- spec("context-manager.snapshot_is_frozen_tree")

## Known gaps

- **Messages list is mutated without a lock.** The `_messages` list is exposed
  directly via the `messages` property and mutated from `initialize`,
  `restore`, `append_message`, and `compress`. Parallel sub-agent callbacks
  triggering `append_message()` concurrently can corrupt ordering and produce
  `tool_call_id` mismatches against the next LLM request. Tracked in #306.
- **Heuristic token estimator silently misjudges non-OpenAI providers.** The
  default `HeuristicTokenEstimator` (and the optional tiktoken estimator's
  `cl100k_base` fallback) drifts 10–40% on Claude/Gemini/Ollama, which can
  push compression too early or let the prompt overflow `max_input_tokens`
  without warning. Tracked in #323.
- **Content-filter recovery in `LiteLLMService` does not re-run orphan-tool
  sanitization on the streaming path.** Stripping `role="tool"` messages
  during `tool_results_only` recovery can leave assistant messages whose
  `tool_calls` no longer have replies, which the next provider request
  rejects. The ContextManager's normal flow is sanitized, but the recovery
  path is not. Tracked in #325.
- **`max_steps` and compression count do not share semantics.** The agent's
  step counter increments differently across happy/error paths in the ReAct
  loop, so "messages added per step" cannot be relied on to predict when
  compression will fire. Tracked in #346.
- **No `@pytest.mark.spec` markers exist yet.** Spec-check will flag every
  marker above as "asserted but missing test" on first run.

## Cross-references

- adr: ADR-025 (Tool-result context isolation — the policy that keeps raw
  tool output out of the message log, the ContextManager owns the
  enforcement)
- related_spec: react-loop.md (the loop drives, the ContextManager owns the
  messages)
- related_spec: content-filter-recovery.md (recovery strips messages the
  ContextManager normally sanitizes)
- related_spec: tools.md (oversized tool results are what the role caps
  exist to contain)
- docs: CLAUDE.md → "Context Management" and "Context Engineering — Tool
  Results & Filter Recovery" sections
- commit: b5829cc (introduced 2026-04-13)
