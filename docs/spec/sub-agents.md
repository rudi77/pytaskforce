---
feature: sub-agents
status: shipped
since: 2026-03-09
last_verified: 2026-05-16
owner: rudi77
adr: ADR-015
---

# Sub-Agent Orchestration

Any agent can delegate a mission to a specialist sub-agent through a tool
call. Sub-agents run in isolated sessions (own state, own message history,
own toolset) and return a single result payload to the parent. Three tools
expose the pattern: `call_agent` (pick a specialist at call time), a
named `SubAgentTool` (specialist fixed at config time, mission only), and
`call_agents_parallel` (batch-dispatch N missions concurrently). Parent
captures each sub-agent's final context snapshot so `/tree --sub-agents`
can inspect what the child saw.

## Capabilities (what the agent/profile-author can do)

- delegate a single mission to a specialist sub-agent via the `call_agent` tool, optionally choosing the specialist per call
- pre-bind a specialist to a named tool so the agent only supplies a mission (`type: sub_agent` in profile YAML)
- dispatch many independent missions concurrently with `call_agents_parallel`, optionally targeting a different specialist per mission
- override the sub-agent's planning strategy per call (`native_react`, `plan_and_execute`, `plan_and_react`, `spar`)
- opt a sub-agent tool out of the approval prompt with `auto_approve: true`, enabling LLM-driven parallel dispatch through the standard tool-call gate
- inspect what each sub-agent saw after completion via `/tree --sub-agents` — the parent's `ContextManager` carries the snapshot
- forward a parent's cooperative interrupt to every running sub-agent so the whole tree pauses together

## Invariants (what must always be true)

- Every sub-agent runs under a session ID derived from its parent: `<parent_session>--sub_<label>_<suffix>`. Parent and sibling sub-agents never share session state.
- A failing sub-agent never crashes the parent; the failure surfaces as a result payload with `success=false` and an `error_kind` field (e.g. `content_filter`, `spawn_failed`, `non_retryable`).
- Partial failures in `call_agents_parallel` do not cancel sibling sub-agents — every mission's result is collected, success counts are reported per batch.
- Sub-agent concurrency is bounded: `call_agents_parallel` enforces its own per-call `max_concurrency` (default 3); LLM-driven parallel calls are bounded by `agent.max_parallel_tools` (default 4).
- A parent interrupt is forwarded to every running sub-agent registered under that parent's session, including children spawned after the interrupt flag is set.
- Sub-agent resources (MCP connections, file handles) are released before the spawner returns — the agent's `close()` runs in the spawner's `finally` block whether the run succeeded, failed, or raised.
- A reused deterministic sub-agent session never replays a previous `ask_user` pause as the answer to the new mission — stale pause state is cleared before execution starts.
- A sub-agent's full context snapshot is captured before `agent.close()` runs, so the snapshot reflects what the child actually saw (not an empty post-close view).
- When a sub-agent succeeds, the result payload's `error` and `error_kind` are both `null`, even if a transient error occurred mid-run and was recovered.
- Specialist lookup never silently falls back to the parent profile when the requested specialist is unknown — the spawner raises with the searched paths instead of looping.
- A sub-agent tool with `auto_approve: false` (default) requires user approval before each spawn; the sub-agent still enforces its own tool-level approval gates regardless of the parent's setting.

## Configuration surface (the profile keys operators rely on)

- `tools: - type: sub_agent` — instantiate a `SubAgentTool`. Required: `name`. Optional: `specialist` (default = `name`), `profile` (default `dev`), `work_dir`, `max_steps`, `planning_strategy`, `auto_approve` (default `false`), `summarize_results` (default `true`), `summary_max_length` (default 2000), `description`, `tool_overrides`.
- `tools: - type: parallel_agent` — instantiate a `ParallelAgentTool`. Optional: `profile` (default `dev`), `work_dir`, `max_steps`, `default_max_concurrency` (default 3).
- `agent.max_parallel_tools: int` (default 4) — upper bound on concurrent tool calls overall; gates LLM-driven parallel `call_agent` invocations.
- Specialist lookup search order, in this order, first hit wins:
  1. `<config_dir>/custom/<specialist>.yaml`
  2. `<config_dir>/custom/<specialist>/<specialist>.yaml`
  3. `<config_dir>/<specialist>.yaml` or `<config_dir>/<specialist>.agent.md`
  4. `agents/<pkg>/configs/<specialist>.{yaml,agent.md}` and `agents/<pkg>/configs/custom/<specialist>.yaml`
  5. `<plugin>/configs/agents/<specialist>.yaml`

## Tool result contract (what the parent agent sees)

Both `call_agent` and `call_agents_parallel` (per-result) return the same
shape, which the parent consumes as a tool-result message:

- `success: bool` — true iff sub-agent reached `completed` or `paused`
- `result: str` — sub-agent's final message (truncated per `summary_max_length` for `sub_agent`; persisted to disk and replaced with a file pointer above 3000 chars for `call_agents_parallel`)
- `session_id: str` — the hierarchical sub-session ID
- `status: str` — terminal `ExecutionStatus` (`completed`, `failed`, `paused`)
- `error: str | null` — non-null only when `success=false`; carries the underlying error message (preferring the structured ERROR event over `final_message`)
- `error_kind: str | null` — non-null only when `success=false`; structured failure category propagated from the LLM stream (e.g. `content_filter`)

`call_agents_parallel` additionally returns a batch envelope: `{success, total, succeeded, failed, results: [...]}`. `success` at the batch level is true iff every sub-result succeeded.

## Extension points

- `SubAgentSpawnerProtocol` in `taskforce.core.interfaces.sub_agents` — replace the spawner to change how sub-agent processes are created (e.g. remote workers, sandboxed runners). Wired via the orchestration tool constructors.
- `taskforce.application.infrastructure_overrides.set_sub_agent_result_dir_override` — let an enterprise overlay route oversized `call_agents_parallel` results to a per-(tenant, user) directory. Resolved at write-time, not at tool construction, so a process-wide tool instance can still be tenant-scoped.

## Tests (must exist and pass)

- spec("sub-agents.session_id_is_hierarchical")
- spec("sub-agents.sub_agent_failure_does_not_crash_parent")
- spec("sub-agents.parallel_partial_failure_keeps_siblings_running")
- spec("sub-agents.parallel_respects_max_concurrency")
- spec("sub-agents.parent_interrupt_propagates_to_children")
- spec("sub-agents.late_child_spawn_after_interrupt_is_signalled")
- spec("sub-agents.context_snapshot_captured_before_close")
- spec("sub-agents.stale_ask_user_state_cleared_on_reuse")
- spec("sub-agents.unknown_specialist_raises_not_falls_back_to_parent")
- spec("sub-agents.success_result_clears_error_and_error_kind")
- spec("sub-agents.auto_approve_disables_parent_approval_only")
- spec("sub-agents.oversized_parallel_result_persisted_with_pointer")

## Known gaps

- **`SubAgentSpawner` memory leak path on spawn exceptions.** `_register_child` is called inside the try-block, so a failure in `_create_agent` is harmless today — but registration and deregistration are not paired as a context manager, so a future refactor that registers earlier would leak `_ACTIVE_CHILDREN` entries and leave the parent permanently flagged as interrupted. Tracked in #328.
- **Interrupt-callback failures are silently swallowed.** `LeanAgent` wraps interrupt callbacks in bare `except Exception` and logs only a warning (no traceback); a broken sub-agent interrupt callback (`TypeError`, `AttributeError`) can leave children running while the parent thinks the cancel went through. Tracked in #335.
- **No timeout for sub-agent execution.** A runaway sub-agent only stops at `max_steps` or via a cooperative interrupt; there is no wall-clock deadline.
- **Parallel sub-agents share the filesystem.** Two workers writing to the same path will collide. The planner is responsible for assigning non-overlapping files; the framework does not arbitrate.
- **No `@pytest.mark.spec` markers exist yet** — the Tests section above asserts the target, not current state. Spec-check will flag every marker as "asserted but missing test" on first run.

## Cross-references

- adr: ADR-015 (Parallel Sub-Agent Execution — `auto_approve` + `call_agents_parallel`)
- adr: ADR-004 (Multi-Agent Runtime — original session-isolation model)
- adr: ADR-019 (Cooperative Agent Interruption — parent interrupt propagation)
- related_spec: react-loop.md (the engine each sub-agent runs)
- related_spec: tools.md (tool registry, approval gating, parallel execution gate)
- related_spec: context-manager.md (sub-agent snapshot registration + `/tree`)
- related_spec: interruption.md (cooperative interrupt propagation)
- related_spec: agent-coding.md (heaviest consumer — planner/worker/judge pipeline)
- docs: docs/features/sub-agent-orchestration.md (user guide, in German)
- docs: CLAUDE.md → "Sub-Agent Spawning" section
