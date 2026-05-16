---
feature: tools
status: shipped
since: 2026-01-02
last_verified: 2026-05-16
owner: rudi77
---

# Tool System — Registry, Resolution, Approval, MCP, Parallel Exec, Result Store

The agent's capability surface. A single registry maps short tool names
(e.g. `python`, `file_read`, `web_search`) to implementations that all
satisfy the same `ToolProtocol`. Tools come from three sources — the
hardcoded framework baseline, the `taskforce.tools` entry-point group
that plugins use to ship their own tools, and MCP servers discovered at
agent build time. The same contract covers parameter validation, approval
gating, parallel execution, and large-result offloading to a per-session
result store so the agent's message log stays small.

## Capabilities (what the user can do)

- list all registered tools and their schemas through the CLI or REST without instantiating tools that need runtime dependencies
- include any registered tool in a profile by short name (`tools: [python, file_read, ...]`)
- contribute new tools from an installed plugin package via the `taskforce.tools` entry-point group, overriding built-ins of the same name
- attach MCP servers (stdio or SSE) to an agent and have their tools surface alongside native ones
- be asked for approval before any tool flagged `requires_approval = true` runs, with a per-tool human-readable preview
- bypass approval for a curated list of tools at the profile level (`agent.approval_bypass_tools`) or tenant-wide via the settings store
- bypass approval automatically for trusted trigger origins per tool (`tool_auto_approve_for_origins`, e.g. `scheduled_workflow` for `send_notification`)
- run independent tool calls from one LLM turn in parallel up to `agent.max_parallel_tools` (default 4), subject to per-tool opt-in
- have large tool results stored out-of-band and replaced in the message log with a short handle reference, then fetched on demand via `fetch_result`
- clean up all stored tool results for a session in one call

## Invariants (what must always be true)

- A tool's short name resolves to at most one implementation per process. Entry-point contributions override built-ins of the same name; no two equally-named tools coexist.
- A tool returning from `execute()` always returns a dict containing `success: bool`; unexpected exceptions inside `BaseTool` subclasses are converted to a standardised error payload, never propagated to the agent.
- A tool whose `requires_approval` is true never runs in parallel with other tools in the same turn; it is forced onto the serial path.
- Parallel dispatch only happens for tools that explicitly set `supports_parallelism = true` AND have `requires_approval = false`. All other tools run serially.
- The number of concurrently-executing tool calls in one turn never exceeds `agent.max_parallel_tools`.
- Listing the tool catalog (CLI / REST) never requires constructing a tool that needs runtime dependencies (LLM service, sub-agent spawner, etc.); class-level metadata is read for `BaseTool` subclasses.
- An MCP server that fails to connect at agent build time does not abort agent creation. The agent continues without that server's tools and the failure is logged.
- An MCP tool result that is not a dict is converted into a standardised error payload — the agent never sees raw non-dict output from an MCP server.
- A tool result exceeding the active threshold (per-tool override > profile `agent.tool_result_store_threshold` > framework default) is written to the result store and only a short handle reference enters the message history.
- Tool result handles are immutable: a handle returned from `put()` refers to a single result file written once and is never rewritten by another call.
- `cleanup_session(session_id)` removes every result whose handle metadata records that `session_id`, and nothing else.
- Parameter validation rejects calls missing a `required` parameter or whose value violates the declared JSON-Schema `type` or `enum`, before the tool body runs.

## Configuration surface (the profile keys / env vars operators rely on)

- `tools: [<short_name>, ...]` — explicit allowlist for an agent. Names not in the resolved registry are dropped with a warning.
- `mcp_servers: [...]` — list of MCP server configs (`type: stdio|sse`, `command`/`args`/`env` or `url`). Per-agent.
- `agent.max_parallel_tools: <int>` (default 4) — semaphore size for parallel tool execution within a single turn.
- `agent.tool_result_store_threshold: <int>` — character threshold above which tool results are written to the store. Overrides the framework default for this agent.
- `agent.approval_bypass_tools: [<short_name>, ...]` — per-profile list of tool short names that skip the approval gate.
- Per-tool class attribute `tool_result_store_threshold: int | None` — overrides the profile default for one tool (e.g. `web_search` ships with `800`, `web_fetch` with `1500`).
- Per-tool class attribute `tool_auto_approve_for_origins: frozenset[str]` — trigger origins (e.g. `"scheduled_workflow"`) that bypass approval for that tool.

## API surface (the contract clients depend on)

- GET /api/v1/tools → 200 with `{tools: [...]}` — the deterministic native tool catalog (no MCP discovery on this endpoint).

## Extension points

- `taskforce.tools` entry-point group — installed packages register tools by short name. Resolution order: entry-point contributions override the built-in baseline on name collision.
- `register_tool(name, tool_type, module, params=...)` / `unregister_tool(name)` in `taskforce.infrastructure.tools.registry` — runtime-only contributions, primarily for tests. Raises on built-in name collision.
- `BaseTool` in `taskforce.infrastructure.tools.base_tool` — convenience class. New tools subclass it and override class-level `tool_name`, `tool_description`, `tool_parameters_schema`, and the async `_execute()` method.
- `ToolProtocol` in `taskforce.core.interfaces.tools` — structural contract. Any class with the right shape works; subclassing is not required.
- `set_approval_bypass_override` in `taskforce.application.infrastructure_overrides` — tenant-wide approval bypass list resolved per request (used by `taskforce-enterprise`).

## Tests (must exist and pass)

- spec("tools.entry_point_tool_overrides_builtin")
- spec("tools.unknown_tool_name_returns_none")
- spec("tools.base_tool_exception_becomes_error_payload")
- spec("tools.validate_params_rejects_missing_required")
- spec("tools.validate_params_rejects_wrong_type")
- spec("tools.parallel_execution_respects_supports_parallelism_flag")
- spec("tools.parallel_execution_skips_tools_needing_approval")
- spec("tools.parallel_execution_capped_by_max_parallel_tools")
- spec("tools.mcp_connection_failure_is_non_fatal")
- spec("tools.mcp_non_dict_result_becomes_error_payload")
- spec("tools.tool_result_threshold_per_tool_overrides_profile")
- spec("tools.tool_result_store_returns_handle_with_size")
- spec("tools.cleanup_session_deletes_only_matching_handles")
- spec("tools.catalog_listing_does_not_require_di")
- spec("tools.approval_bypass_list_skips_gate")
- spec("tools.auto_approve_for_origin_skips_gate")

## Known gaps

- **Python tool sandbox escape**: `PythonTool` exposes `__import__` (and `open`) as builtins in its execution namespace, so any prompt-injection payload can load `os` / `subprocess` and break out of the medium-risk approval framing. Tracked in #276.
- **Shell tool dangerous-command blocklist is bypassable** with whitespace, quoting, command substitution, or `eval`. The `_DANGEROUS_PATTERNS` substring check is by design incomplete. Tracked in #277.
- **Shell/PowerShell tools mask underlying errors as empty strings** when `str(exc)` is empty (e.g. `NotImplementedError` from `asyncio.create_subprocess_exec` on Windows SelectorEventLoop). The agent sees `"powershell failed: "` and retries blindly. Tracked in #274.
- **BrowserTool can deadlock on nested calls**: the dedicated Playwright worker loop is reached via `asyncio.run_coroutine_threadsafe` + `wrap_future`. A nested chain (python tool → browser tool → tool bridge → main loop) creates a circular wait. Tracked in #308.
- **Tool result store has no TTL or LRU eviction**: every put writes a JSON file under `<store_dir>/results/`; long-running daemons grow the directory unboundedly. Tracked in #305.
- **Tool result store UUID generation runs outside the per-handle lock** (`uuid4()` is called before `_get_lock`). Statistically harmless today, but the ID/exists-check/write sequence should be atomic. Tracked in #316.
- **MCP tool-schema validation errors are silently suppressed** at debug-log level. A broken MCP server returns garbage that the LLM treats as a valid result; downstream errors are hard to root-cause. Tracked in #339.
- **`accounting_validate` and `accounting_audit` are registered in the built-in baseline but no implementation modules exist** — the accountant sub-agent profile that references them will crash on first tool resolve. Tracked in #321.
- **`SendNotificationTool` approval preview includes recipient IDs verbatim** (Telegram user-id, e-mail). These leak into approval audit logs. Tracked in #296.
- **No backend `@pytest.mark.spec` markers exist yet** — the Tests section above asserts the target, not current state. Spec-check will flag every marker as "asserted but missing test".

## Cross-references

- adr: ADR-025 (Tool result context isolation — threshold and recovery rules)
- adr: ADR-026 (Entry-point plugin discovery — `taskforce.tools` group)
- adr: ADR-027 (Generic agent daemon — moved butler-only tools into the framework registry)
- related_spec: sub-agents.md (uses the same tool infrastructure for sub-agent invocation)
- related_spec: skills.md (skills can override an agent's tool set at activation time)
- related_spec: approval-gating.md (full contract for approval lifecycle and bypass precedence)
- docs: CLAUDE.md → "Tools" + "Context Engineering — Tool Results & Filter Recovery"
