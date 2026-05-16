---
feature: content-filter-recovery
status: shipped
since: 2026-05-10
last_verified: 2026-05-16
owner: rudi77
adr: ADR-025
---

# Content-Filter Recovery

When a provider (Azure / OpenAI) rejects a request with a content-policy
error, the LLM service retries it through progressively more aggressive
recovery stages instead of failing the whole agent run. The trigger
usually sits in accumulated tool-result snippets (web fetches, shell
output) — not in the latest user turn — so the cheapest strip runs
first and the expensive `rephrase` stage is the last resort. Streaming
consumers (UI, ReAct loop) are told to discard partial output from the
failed attempt via a `stream_restart` event, and if every stage fails
the user sees an actionable German error message naming the real
cause, not a generic "etwas ging schief" fallback.

## Capabilities (what the operator / user gets)

- transparently retry a content-filter rejection without losing the conversation
- run recovery on both blocking (`complete()`) and streaming (`complete_stream()`) paths
- progress through four stages, stopping at the first one that succeeds: `tool_results_only` → `aggressive` → `no_tools` → `rephrase`
- opt out of the LLM-cost `rephrase` stage by constructing `LiteLLMService(recover_via_rephrase=False)` (default: on)
- tune how many recent user/assistant turns survive the `aggressive` strip via the `recovery_keep_last_n` constructor knob (default 2)
- receive a `stream_restart` event before each retry so accumulated tokens from the failed attempt can be discarded
- get an actionable German user-facing message (`/compact`, new conversation, Azure shield hint) instead of a blank reply when every stage fails

## Invariants (what must always be true)

- A provider error is classified as content-filter iff its message contains one of `_CONTENT_FILTER_KEYWORDS` (`content_policy`, `contentpolicy`, `content filter`, `content manage`); non-content-filter errors fall through to the generic error path with no stripping.
- Recovery stages run in fixed order: `tool_results_only` first, then `aggressive`, then (when tools were originally supplied) `no_tools`, then (when `recover_via_rephrase=True`) `rephrase`. The first stage that succeeds wins and remaining stages are skipped.
- A stage is only attempted if it actually shrinks the message list (`len(stripped) < len(messages)`) — empty strips are skipped so a fresh conversation that triggers the filter on turn one doesn't loop on identical retries.
- The `tool_results_only` strip drops every `role="tool"` message and every assistant turn whose sole purpose was emitting `tool_calls`, then sanitises orphan tool messages so no tool reply is left without its matching assistant call.
- The `aggressive` strip keeps the system prompt plus the last `recovery_keep_last_n` plain user/assistant turns (no tool messages, no tool-call assistant turns); `recovery_keep_last_n` is floored at 1.
- The `no_tools` stage only runs when tools were supplied to the original call AND at least one strip stage already ran — so an output-side filter trigger (tool-call args containing flagged content) gets a chance, but a malformed-request error is not mis-classified as content-filter.
- The `rephrase` stage issues exactly one extra LLM call (small, no tools, `max_tokens=200`, `temperature=0`) tagged with `metadata={"phase": "filter_recovery_rephrase"}` so observability can distinguish it from normal completions.
- On the streaming path, every recovery retry is preceded by a `stream_restart` event carrying `{type, reason: "content_filter", stage: <stage_name>}` so consumers can drop tokens accumulated since the previous restart marker.
- If every stage fails, the final error event is forced to `error_kind="content_filter"` and `non_retryable=True` even when the proximate exception is something else (e.g. a timeout during the rephrase retry) — so the user-visible root cause stays the real one.
- `build_user_message_for_error("content_filter", ...)` returns the actionable German guidance (recommends `/compact`, new conversation, Azure Foundry shield setting) — never the generic "etwas ging schief" line.
- The recovery cascade is identical in shape on both `complete()` and `complete_stream()`; a streaming caller and a blocking caller faced with the same content-filter error see the same number of stages run.

## Configuration surface

- `LiteLLMService(recover_via_rephrase: bool)` constructor flag (default `True`) — controls whether the final rephrase stage runs. The rephrase stage costs one extra small LLM call only on the failure path; turn it off in cost-sensitive deployments.
- `LiteLLMService(recovery_keep_last_n: int)` constructor flag (default `2`, floored at 1) — number of plain user/assistant turns retained by the `aggressive` strip.
- Per-tool `tool_result_store_threshold` and profile-level `agent.tool_result_store_threshold` (see `react-loop.md` / ADR-025) reduce the amount of freeform tool output written into the message log in the first place, which is the most effective way to keep recovery from ever needing to run.

There are no profile-YAML keys for the recovery cascade itself; it is wired by `InfrastructureBuilder` when the LLM service is constructed.

## Event stream contract

Events members of `LLMStreamEventType` in `core/domain/enums.py` (consumed by `react_loop.py`, where they get re-emitted as `EventType.LLM_STREAM_RESTART` on the agent's `StreamEvent` stream):

- `STREAM_RESTART` — `{type: "stream_restart", reason: "content_filter", stage: "tool_results_only" | "aggressive" | "no_tools" | "rephrase"}`. Emitted at the start of every recovery retry on the streaming path. Consumers MUST discard any tokens received since the previous `STREAM_RESTART` (or since stream start). The ReAct loop translates this into `EventType.LLM_STREAM_RESTART` and resets its `content_acc` / `tc_acc` accumulators; `simple_chat` renders a yellow "Antwort wegen Sicherheitsfilter neu generiert" marker.

On terminal failure, the stream's `error` event carries `error_kind="content_filter"` and `non_retryable=True`; the ReAct loop forwards this on the `ERROR` event, and `build_user_message_for_error` converts the kind into the actionable German message.

## Tests (must exist and pass)

- spec("content-filter-recovery.tool_results_only_runs_first")
- spec("content-filter-recovery.stages_run_in_order_until_success")
- spec("content-filter-recovery.empty_strip_skips_stage")
- spec("content-filter-recovery.no_tools_stage_only_when_tools_supplied")
- spec("content-filter-recovery.rephrase_stage_off_when_disabled")
- spec("content-filter-recovery.stream_restart_emitted_before_each_retry")
- spec("content-filter-recovery.final_error_forced_to_content_filter_kind")
- spec("content-filter-recovery.aggressive_strip_keeps_recovery_keep_last_n_turns")
- spec("content-filter-recovery.tool_results_only_drops_orphan_tool_call_assistants")
- spec("content-filter-recovery.complete_and_complete_stream_run_same_cascade")
- spec("content-filter-recovery.build_user_message_returns_actionable_german_guidance")

## Known gaps

- **Orphan `tool_calls` after `tool_results_only` strip.** The strip drops `role="tool"` messages and assistant turns whose only purpose was emitting tool calls, then sanitises orphans — but a mixed assistant turn that carries both `content` AND `tool_calls` is preserved as-is, which can leave dangling tool-call IDs the provider then rejects on retry. Tracked in #325.
- **Double-stripping when `tool_results_only` reduces the list to the same length as `aggressive`.** The current guard `len(aggressive) < len(stages[-1][1])` skips the aggressive stage when it doesn't shrink further, but on certain message shapes the cascade still queues two stages that send byte-identical requests. Tracked in #343.
- **Rephrase stage uses the same model that just got filtered.** It calls `litellm.acompletion(model=resolved_model, ...)` directly with no router hint, so a deployment with a single Azure model behind every alias will rephrase using the same filter profile that rejected the original. The `metadata={"phase": "filter_recovery_rephrase"}` tag is present so a future router rule can divert to a cheaper / less-filtered model, but no such rule ships today.
- **Recovery on the `complete()` (blocking) path is a two-stage cascade only** — `aggressive` and `rephrase`. The streaming path runs the full four stages (`tool_results_only` → `aggressive` → `no_tools` → `rephrase`). The blocking path predates the staged cascade and was not back-ported.
- **No `@pytest.mark.spec` markers exist yet** — the Tests section asserts the target, not current state. Spec-check will flag every marker as "asserted but missing test" on first run.

## Cross-references

- adr: ADR-025 (Tool-result context isolation + content-filter recovery)
- related_spec: llm-service.md (the cascade lives inside `complete()` / `complete_stream()`)
- related_spec: react-loop.md (consumer of `STREAM_RESTART`; re-emits as `LLM_STREAM_RESTART`)
- related_spec: context-manager.md (related: role-aware message caps that reduce filter-trigger likelihood before recovery is needed)
- docs: CLAUDE.md → "Context Engineering — Tool Results & Filter Recovery (ADR-025)"
- commit: d157af2 (ADR-025 introduced 2026-05-10)
