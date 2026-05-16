---
feature: approval-gating
status: shipped
since: 2026-05-07
last_verified: 2026-05-16
owner: rudi77
---

# Tool Approval Gating — Per-Tool Gate, Bypass Lists, Lifecycle Hooks

The agent does not run a tool flagged as risky until something — a human
on stdin, an admin clicking a REST grant, an auto-approver — says yes.
Tools self-declare risk via `requires_approval` + `ApprovalRiskLevel`;
the agent calls an installed `ApprovalServiceProtocol` before every such
tool call, with a human-readable preview the tool itself formats. Two
bypass surfaces (per-profile and tenant-wide) let operators waive the
gate for trusted tools; a per-tool trigger-origin allow-list waives it
for scheduler-fired workflows where no human is at the keyboard. The
framework ships a CLI prompt service and a no-op auto-approver; the
enterprise plugin replaces them with a REST-backed queue.

## Capabilities (what the user can do)

- mark a tool as gated by setting `requires_approval = True` on its class (or `tool_requires_approval = True` for `BaseTool` subclasses)
- declare a per-tool risk level (`LOW` / `MEDIUM` / `HIGH`) that the approval UI uses to style the prompt
- write a per-tool `get_approval_preview(**kwargs)` so the human sees what is about to happen — not just the tool name
- be prompted on stdin before each gated tool runs in `taskforce chat` / `taskforce run mission` (default CLI service)
- run gated tools without prompts in unit tests / CI by installing `AutoApproveService`
- park approval requests in an async queue and resolve them via REST in enterprise deployments (out-of-tree `ApprovalServiceProtocol` implementation)
- waive the gate for a curated set of tools at the profile level via `agent.approval_bypass_tools: [python, shell, ...]`
- waive the gate tenant-wide via the settings store `approval` section's `bypass_tools` list, edited from the Settings UI without a restart
- auto-grant for trusted trigger origins per tool via `tool_auto_approve_for_origins = frozenset({"scheduled_workflow"})` (e.g. `send_notification` runs unattended on cron)
- observe mission start / completion with `MissionLifecycleHookProtocol` for audit pipelines, independently of the approval gate

## Invariants (what must always be true)

- A tool whose `requires_approval` is False is never sent through the gate.
- With no `ApprovalServiceProtocol` installed, a gated tool still runs — the gate is opt-in and absence means "single-user CLI defaults".
- A tool short-name listed in **either** the agent's `approval_bypass_tools` set **or** the tenant-level `approval.bypass_tools` list skips the gate; the two sources combine via UNION (not intersection).
- The tenant-level bypass list is re-read on every tool call, not cached at agent construction, so a UI edit to the `approval` section takes effect on the next gated tool call without a restart.
- Parameter validation runs **before** the human prompt. A malformed tool call surfaces a validation error to the LLM immediately instead of asking the user to approve a call that would have failed anyway.
- A denied or timed-out approval returns a tool-result dict with `success: False`, `terminal_failure: True`, and an `error_kind` of `approval_denied` / `approval_timeout` / `approval_error`; the planning loop must treat this as terminal and not retry the same forbidden call.
- An exception inside the approval service surfaces as `approval_status: error` + `terminal_failure: True`, distinct from a deliberate user denial so audit logs and the LLM can tell "pipeline broke" apart from "user said no".
- An exception inside a `get_approval_preview` implementation falls back to the bare tool name as the preview — a buggy preview never aborts the gate.
- Concurrent CLI approval prompts are serialised on a module-level `asyncio.Lock` so two parallel sub-agents do not interleave their stdin questions.
- The CLI prompt writes to stderr, not stdout, so a piped/captured stdout (UI subprocess, eval harness) still surfaces the question to the operator.
- The `auto_approve_for_origins` allow-list only triggers when `get_trigger_origin()` returns a non-`None` value; interactive flows leave the ContextVar unset and always fall through to the gate.
- A `requires_approval=True` tool never runs in parallel with other tools in the same LLM turn — it is forced onto the serial path regardless of `supports_parallelism` (see [tools.md](tools.md)).
- Mission lifecycle hook errors are warned but never raised: a broken audit pipeline cannot break a running mission.

## Configuration surface (the profile keys / env vars operators rely on)

- `agent.approval_bypass_tools: [<short_name>, ...]` — profile-level list of tools that skip the approval gate. Stored as a frozenset on the agent.
- Settings store `approval` section, payload `{"bypass_tools": ["python", "shell", ...]}` — tenant-level bypass list. Hydrated into the global override on server startup and after every `PUT`/`DELETE /api/v1/settings/approval`. Empty/missing clears the override.
- Per-tool class attribute `tool_requires_approval: bool` (BaseTool) / `requires_approval` property — opts the tool into the gate.
- Per-tool class attribute `tool_approval_risk_level: ApprovalRiskLevel` (BaseTool) — `LOW` / `MEDIUM` / `HIGH`; used by approval UIs for styling.
- Per-tool class attribute `tool_auto_approve_for_origins: frozenset[str]` — trigger origins (e.g. `"scheduled_workflow"`) that auto-grant for this tool.
- Per-tool method `get_approval_preview(**kwargs) -> str` — human-readable summary shown in prompts and audit logs.

## API surface (the contract clients depend on)

The framework does not ship a REST surface for approval decisions — the enterprise plugin owns
`POST /admin/approvals/{id}/grant|deny`. The framework exposes only the bypass-list section via
the Settings Store (see [settings-store.md](settings-store.md) for the full route contract):

- PUT    /api/v1/settings/approval accepts `{bypass_tools: [<short_name>, ...]}` and re-hydrates the global override before responding
- DELETE /api/v1/settings/approval clears the tenant-level bypass override
- GET    /api/v1/tools surfaces each tool's `requires_approval` flag so the UI can build the bypass-tool picker

## Extension points

- `ApprovalServiceProtocol` in `taskforce.core.interfaces.approval` — single-method contract (`request_approval`). Implementations may prompt stdin, block on a REST grant, or auto-approve.
- `set_approval_service` in `taskforce.application.infrastructure_overrides` — registers the process-wide service. Consulted on every gated tool call; absence means "no gate".
- `set_approval_bypass_override` / `get_approval_bypass_override` in `taskforce.application.infrastructure_overrides` — tenant-wide bypass list. Called by `application.settings_hydrator.hydrate_approval` on startup and after every write to the `approval` section.
- `MissionLifecycleHookProtocol` in `taskforce.core.interfaces.mission_lifecycle` — `on_mission_started` / `on_mission_completed` observers for audit pipelines.
- `set_mission_lifecycle_hook` in `taskforce.application.infrastructure_overrides` — installs a process-wide hook; `AgentExecutor` calls it around `execute_mission_streaming`. Hook failures are logged, never raised.
- `trigger_origin(origin)` context manager in `taskforce.core.domain.trigger_context` — wraps a code block so gated tools inside it see the named origin via `get_trigger_origin()`. The scheduler dispatcher wraps every `EXECUTE_WORKFLOW` run with `"scheduled_workflow"`.

## Tests (must exist and pass)

- spec("approval-gating.tool_without_requires_approval_skips_gate")
- spec("approval-gating.no_service_installed_runs_tool_anyway")
- spec("approval-gating.profile_bypass_list_skips_gate")
- spec("approval-gating.tenant_bypass_list_skips_gate")
- spec("approval-gating.bypass_sources_combine_as_union")
- spec("approval-gating.tenant_bypass_reread_on_each_call")
- spec("approval-gating.invalid_params_short_circuit_before_prompt")
- spec("approval-gating.denied_decision_returns_terminal_failure")
- spec("approval-gating.timed_out_decision_distinct_from_denied")
- spec("approval-gating.service_exception_yields_error_kind_approval_error")
- spec("approval-gating.preview_exception_falls_back_to_tool_name")
- spec("approval-gating.cli_prompts_serialised_under_concurrent_calls")
- spec("approval-gating.cli_prompt_writes_to_stderr_not_stdout")
- spec("approval-gating.auto_approve_for_origin_skips_gate")
- spec("approval-gating.gated_tool_forced_onto_serial_path")
- spec("approval-gating.mission_lifecycle_hook_errors_do_not_break_mission")

## Known gaps

- **Layer-violation in the gate**: `LeanAgent._maybe_request_approval` (core/domain) imports `get_approval_bypass_override` from `application.infrastructure_overrides`. Core importing application breaks the inward-only dependency rule. Tracked in #301.
- **`SendNotificationTool` approval preview includes recipient ids verbatim** (Telegram user-id, e-mail). These leak into approval audit logs and the stdin prompt. Tracked in #295.
- **CLI skill execution bypasses the agent's tool allowlist**: `taskforce execute_agent_skill` runs the skill's tools through a path that does not enforce the agent's resolved `tools:` list, so a skill can call a tool the agent never declared — and therefore never went through the approval-bypass review at profile-load time. Tracked in #300.
- **Approval timeout is implementation-defined**: `ApprovalServiceProtocol` documents that implementations *should* enforce a timeout, but the protocol does not require one. A buggy enterprise service can hang an agent indefinitely.
- **No backend `@pytest.mark.spec` markers exist yet** — Tests section above asserts the target, not current state.

## Cross-references

- related_spec: tools.md (`requires_approval`, `supports_parallelism`, serial-path forcing)
- related_spec: settings-store.md (the `approval` section's PUT/DELETE/hydration contract)
- docs: CLAUDE.md → "Tools" + `ApprovalRiskLevel` enum reference
- commit: d3e2e6c (initial gate + lifecycle hooks)
- commit: e8162c5 (CLI stdin lock + plugin opt-out)
- commit: 2105c19 (profile + tenant bypass lists, UI Approvals tab)
- commit: d760144 (auto-approve for scheduled-workflow origin, #177)
- commit: 41a5586 (error_kind classification, suppress retry nudge, #204)
