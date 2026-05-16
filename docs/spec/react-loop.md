---
feature: react-loop
status: shipped
since: 2026-01-02
last_verified: 2026-05-16
owner: rudi77
adr: ADR-012
---

# ReAct Loop & Planning Strategies

The engine that drives every agent execution. An agent reasons step by step
(Thought → Action → Observation), calls tools, and either answers, asks the
user, or hits a step or error limit. Profile authors choose one of four
built-in strategies (`native_react`, `plan_and_execute`, `plan_and_react`,
`spar`) and tune step limits via the profile YAML. Both blocking and
streaming execution interfaces are first-class — the streaming API is the
source of truth, and the blocking one collects from it.

## Capabilities (what the operator/profile-author can do)

- choose one of four built-in planning strategies for an agent via `agent.planning_strategy` in profile YAML
- bound total work via `agent.max_steps`
- tune per-strategy parameters (`max_step_iterations`, `max_plan_steps`, `reflect_every_step`, ...) via `agent.planning_strategy_params`
- consume execution as a stream of typed events (for UI, SSE, logging) or as a single `ExecutionResult` (for batch)
- pause execution mid-mission by emitting an `ask_user` event and resume once the answer arrives
- interrupt a running execution cooperatively from outside (web Stop button, CLI Ctrl-C, programmatic `agent.request_interrupt()`)
- distinguish terminal outcomes via `ExecutionStatus`: `completed`, `failed`, `paused`, `pending`

## Invariants (what must always be true)

- Every execution emits events in this lifecycle order: `STARTED` first, exactly one terminal event from `{FINAL_ANSWER, ASK_USER, INTERRUPTED, ERROR}`, followed by `COMPLETE`. Intermediate events (`STEP_START`, `LLM_TOKEN`, `TOOL_CALL`, `TOOL_RESULT`, `PLAN_UPDATED`, `TOKEN_USAGE`) appear between `STARTED` and the terminal event.
- A `COMPLETE` event is always the last event in the stream, regardless of success or failure.
- The loop terminates as soon as `step >= agent.max_steps`, even if the agent has not produced a final answer; the terminal event in that case is `ERROR` with a `max_steps_reached` kind, never an empty completion.
- An `ASK_USER` event pauses the execution; the loop does not advance until the answer is supplied (status becomes `paused`, not `failed`).
- An `INTERRUPTED` event is emitted on cooperative cancellation; the resulting `ExecutionResult.status` is `paused`, not `failed`, so the conversation can be resumed.
- `LLM_STREAM_RESTART` signals to consumers that all tokens received since the previous restart marker (or `STARTED`) must be discarded — they belong to a failed attempt being retried (e.g. after a content-filter block).
- Tool errors are converted to structured payloads (`{success: false, error, error_type}`), never raw exceptions reaching the LLM.
- Both `Agent.execute()` (blocking) and `Agent.execute_stream()` (streaming) must produce equivalent results for the same input — blocking is implemented by collecting from streaming, so a divergence is a bug.
- Every concrete `PlanningStrategy` implements both `execute()` and `execute_stream()` — the protocol does not allow either to be optional.
- The `native_react` strategy is the framework default when no `planning_strategy` is set.
- `TOKEN_USAGE` events are emitted at least once per execution, with the final cumulative count appearing before `COMPLETE`.

## Configuration surface (the profile keys operators rely on)

- `agent.planning_strategy: <name>` where `<name>` ∈ `{native_react, plan_and_execute, plan_and_react, spar}` (default: `native_react`)
- `agent.planning_strategy_params: dict` with strategy-specific keys:
  - `max_step_iterations: int` (default 4) — per-step LLM retry budget within `plan_and_execute` / `spar`
  - `max_plan_steps: int` (default 12) — cap on TodoList plan length
  - `reflect_every_step: bool` (default false, SPAR-only) — run reflect phase after each act
  - `generate_plan_first: bool` (default false, native_react-only) — emit an upfront plan before looping
- `agent.max_steps: int` — hard ceiling on iterations across all strategies

## Event stream contract (what callers of the streaming API must handle)

Events that any caller (UI, SSE consumer, CLI) must handle as part of the public contract:

- `STARTED` — execution began (always first)
- `STEP_START` — a new reasoning step begins (paired with one ore more LLM_TOKEN / TOOL_CALL / TOOL_RESULT events)
- `LLM_TOKEN` — token from the streaming LLM response (consumers may render or buffer)
- `LLM_STREAM_RESTART` — discard partial tokens since the last restart marker
- `TOOL_CALL` — the LLM decided to call a tool
- `TOOL_RESULT` — the tool returned (may be structured success or error payload)
- `PLAN_UPDATED` — plan steps were added or marked done
- `ASK_USER` — execution paused for user input (terminal until resumed)
- `FINAL_ANSWER` — agent produced the answer
- `INTERRUPTED` — execution paused by cooperative cancel
- `ERROR` — execution failed terminally (carries `error`, `error_kind`)
- `TOKEN_USAGE` — current cumulative token counts (emitted ≥ once)
- `COMPLETE` — always last; carries final `ExecutionStatus`

## Extension points

- `PlanningStrategy` protocol — implement `execute()` + `execute_stream()` and the strategy can be plugged into the agent. Custom strategies are wired via `planning_strategy_factory` in `taskforce.application` — see Known gaps below for the public-registry limitation.

## Tests (must exist and pass)

- spec("react-loop.event_order_started_to_complete")
- spec("react-loop.terminal_event_precedes_complete")
- spec("react-loop.max_steps_terminates_with_error_kind")
- spec("react-loop.ask_user_pauses_execution_with_paused_status")
- spec("react-loop.interrupted_returns_paused_not_failed")
- spec("react-loop.tool_error_returns_structured_payload")
- spec("react-loop.llm_stream_restart_emitted_on_content_filter")
- spec("react-loop.native_react_is_default_strategy")
- spec("react-loop.spar_reflect_phase_runs_when_enabled")
- spec("react-loop.plan_and_execute_steps_sequentially")
- spec("react-loop.streaming_and_blocking_yield_equivalent_results")
- spec("react-loop.token_usage_emitted_before_complete")

## Known gaps

- **`max_steps` semantics undocumented in profile reference.** Today it is unclear whether `max_steps=10` means "10 LLM calls" or "10 successful steps"; the inc/dec rules differ across strategies and across happy-path vs error-path. Tracked in #346.
- **No public registry for custom planning strategies.** Adding a strategy requires editing `planning_strategy_factory` in `application/`, which means it is not actually extensible from a plugin — only from a fork. The `PlanningStrategy` protocol is public but the wiring is closed.
- **`_stream_final_response` in `llm_interactions.py` swallows fatal errors with bare `except`** and retries on the next model hint, burning expensive reasoning tokens for auth/quota errors that will never succeed. Tracked in #326.
- **Tool errors lose `error_kind` between executor and agent dict.** The result dict the LLM sees is `{success: false, error}` only; the typed `error_kind` (transient/permanent) is logged but stripped. Tracked in #334.
- **Cooperative interrupt callback failures are caught as bare `Exception` and only logged as warning** — a broken sub-agent interrupt callback may silently fail to propagate, leaving sub-agents running while the parent thinks it cancelled. Tracked in #335.
- **No `@pytest.mark.spec` markers exist yet** — the Tests section above asserts the target, not current state. Spec-check will flag every marker as "asserted but missing test" on first run.
- **`generate_plan_first` and `plan_and_react` overlap semantically.** `plan_and_react` is documented as "alias for NativeReAct with plan", but is exposed as a separate strategy name. Either consolidate or document the difference.

## Cross-references

- adr: ADR-012 (Dynamic LLM Selection — strategies emit phase hints consumed by the LLM Router)
- adr: ADR-019 (Cooperative Agent Interruption — INTERRUPTED event lifecycle)
- adr: ADR-025 (Tool-result context isolation + content-filter recovery)
- related_spec: context-manager.md (the loop drives, the ContextManager owns the messages)
- related_spec: tools.md (tool execution semantics during `TOOL_CALL`)
- related_spec: content-filter-recovery.md (the source of LLM_STREAM_RESTART events)
- related_spec: llm-router.md (phase hints emitted by strategies)
- related_spec: interruption.md (INTERRUPTED event mechanics)
- docs: CLAUDE.md → "ReAct Loop" + "Planning Strategies" sections
- commit: e285a08 (introduced 2026-01-02)
